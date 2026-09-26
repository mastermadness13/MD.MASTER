# -*- coding: utf-8 -*-
"""Area 4 (data isolation and business logic) — cross-department guards.

Area 4 asked one question: *can a principal reach another department's or
another owner's records?*  The audit found the isolation to be sound on every
surface it could reach, so this file does not fix a defect — it **pins the
decisions** that were verified, so a later change that drops one fails loudly
instead of silently re-opening the boundary.

The guide's core discipline drives the shape of these tests: a ``department_id``
column on a row is not isolation.  Isolation only exists where a query, a
session-derived identity, or a lifecycle predicate is bound on *every* read and
write path.  So each test drives the real request path with two dummy
departments and asserts the boundary holds — anonymous, same-department, and
cross-department principals compared against each other, never real user data.

The three boundaries pinned here:

1. **Head-of-department scope** — a HOD reaches only their own department's
   materials, on both the read (download) and the write (delete) path.  A
   by-id ``WHERE id = ?`` without the department predicate is the exact
   regression that would re-open this.
2. **Owner scope on course content** — a teacher reaches only their own
   submission, and the public library only ever serves ``published`` rows.
   Deletion and publication are lifecycle contracts: an unpublished sheet is
   internal state, not public data.
3. **Lifecycle authority** — resurrecting or permanently destroying a
   soft-deleted teacher is gated by ``teachers.manage`` (write), never by the
   read-only ``teachers.view`` that HOD holds.  A read permission must never be
   the only guard on a mutation.
"""

import pathlib
import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema

ROOT = pathlib.Path(__file__).resolve().parent.parent

DEPT_A = 'قسم ألف'
DEPT_B = 'قسم باء'


def _seed(tmp_path, monkeypatch):
    """Two dummy departments, a HOD for A, and one teacher + material each."""
    db_path = tmp_path / 'area4_isolation.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))

    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())

    ids = {}
    for key, name in (('a', DEPT_A), ('b', DEPT_B)):
        conn.execute(
            "INSERT INTO departments (name, type) VALUES (?, 'academic')", (name,)
        )
        ids[f'dept_{key}'] = conn.execute(
            'SELECT id FROM departments WHERE name = ?', (name,)
        ).fetchone()['id']

    def _user(username, role):
        conn.execute(
            "INSERT INTO users (username, password, role, label) "
            "VALUES (?, 'x', ?, '|area4|')",
            (username, role),
        )
        uid = conn.execute(
            'SELECT id FROM users WHERE username = ?', (username,)
        ).fetchone()['id']
        conn.execute(
            'INSERT INTO user_roles (user_id, role) VALUES (?, ?)', (uid, role)
        )
        return uid

    # The HOD of department A.  Linked to a teacher row by user_id because
    # that is the canonical user->teacher link authenticate() resolves.
    ids['hod_uid'] = _user('a4_hod', 'head_of_department')
    conn.execute(
        'INSERT INTO teachers (name, user_id, hod_department_id) VALUES (?, ?, ?)',
        ('ر试用س قسم ألف', ids['hod_uid'], ids['dept_a']),
    )
    ids['hod_teacher'] = conn.execute(
        "SELECT id FROM teachers WHERE name = 'ر试用س قسم ألف'"
    ).fetchone()['id']

    for key, dept in (('a', 'dept_a'), ('b', 'dept_b')):
        uid = _user(f'a4_teacher_{key}', 'teacher')
        conn.execute(
            'INSERT INTO teachers (name, user_id, department_id) VALUES (?, ?, ?)',
            (f'أستاذ {key}', uid, ids[dept]),
        )
        tid = conn.execute(
            'SELECT id FROM teachers WHERE name = ?', (f'أستاذ {key}',)
        ).fetchone()['id']
        ids[f'teacher_{key}_uid'] = uid
        ids[f'teacher_{key}'] = tid
        conn.execute(
            'INSERT INTO teacher_materials '
            '(teacher_id, user_id, department_id, title, filename, '
            ' original_filename, file_type) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (tid, uid, ids[dept], f'مادة {key}', f'{key}.pdf', f'{key}.pdf', 'material'),
        )
        ids[f'material_{key}'] = conn.execute(
            'SELECT id FROM teacher_materials WHERE title = ?', (f'مادة {key}',)
        ).fetchone()['id']

    conn.commit()
    ensure_schema(conn)
    conn.commit()
    conn.close()
    return db_path, ids


def _login(client, user_id, role, **extra):
    with client.session_transaction() as sess:
        sess['_csrf_token'] = 't'
        sess['user_id'] = user_id
        sess['role'] = role
        sess['roles'] = [role]
        sess['username'] = f'a4_{role}'
        for k, v in extra.items():
            sess[k] = v


@pytest.fixture
def world(tmp_path, monkeypatch):
    db_path, ids = _seed(tmp_path, monkeypatch)
    return db_path, ids


def _conn(db_path):
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    return c


# ── 1. head-of-department scope ──────────────────────────────────────────


def test_hod_cannot_download_another_departments_material(app_fx, world):
    """A HOD must not pull a file belonging to a department they do not head."""
    db_path, ids = world
    c = app_fx.test_client()
    _login(c, ids['hod_uid'], 'head_of_department',
           hod_department_id=ids['dept_a'])

    own = c.get(f"/hod/materials/download/{ids['material_a']}")
    assert own.status_code in (200, 404), 'own-department baseline drifted'

    foreign = c.get(f"/hod/materials/download/{ids['material_b']}")
    assert foreign.status_code == 404, (
        'HOD of department A was served department B material '
        f'(status {foreign.status_code})'
    )


def test_hod_download_of_another_department_leaves_the_counter_untouched(
    app_fx, world
):
    """The refusal must happen *before* the counter write, not after."""
    db_path, ids = world
    c = app_fx.test_client()
    _login(c, ids['hod_uid'], 'head_of_department',
           hod_department_id=ids['dept_a'])

    c.get(f"/hod/materials/download/{ids['material_b']}")

    conn = _conn(db_path)
    try:
        row = conn.execute(
            'SELECT download_count FROM teacher_materials WHERE id = ?',
            (ids['material_b'],),
        ).fetchone()
    finally:
        conn.close()
    assert (row['download_count'] or 0) == 0


def test_hod_cannot_delete_another_departments_material(app_fx, world):
    """The write path matters more than the read path: deletion is destructive."""
    db_path, ids = world
    c = app_fx.test_client()
    _login(c, ids['hod_uid'], 'head_of_department',
           hod_department_id=ids['dept_a'])

    response = c.post(
        f"/hod/materials/delete/{ids['material_b']}",
        data={'_csrf_token': 't'},
    )
    assert response.status_code in (302, 404)

    conn = _conn(db_path)
    try:
        still_there = conn.execute(
            'SELECT COUNT(*) FROM teacher_materials WHERE id = ?',
            (ids['material_b'],),
        ).fetchone()[0]
    finally:
        conn.close()
    assert still_there == 1, 'a HOD deleted another department\'s material'


# ── 2. owner scope + lifecycle masking on course content ─────────────────


def test_teacher_cannot_read_another_teachers_course_content(app_fx, world):
    """Owner scope on the course-content read path.

    Uses a *real* submission owned by teacher B so that removing the
    ``AND teacher_id`` predicate genuinely exposes it — a made-up id would 404
    either way and the test could never fail.
    """
    db_path, ids = world
    conn = _conn(db_path)
    try:
        conn.execute(
            'INSERT INTO course_content_submissions '
            '(user_id, department_id, course_name, course_code, status, '
            ' teacher_id) VALUES (?, ?, ?, ?, ?, ?)',
            (ids['teacher_b_uid'], ids['dept_b'], 'مقرر سرّي', 'SEC1',
             'published', ids['teacher_b']),
        )
        sub_id = conn.execute(
            "SELECT id FROM course_content_submissions WHERE course_code = 'SEC1'"
        ).fetchone()['id']
        conn.commit()
    finally:
        conn.close()

    c = app_fx.test_client()
    _login(c, ids['teacher_a_uid'], 'teacher')
    response = c.get(f'/teacher/course-content/{sub_id}/form')
    assert response.status_code == 404, (
        'teacher A read teacher B\'s course-content sheet '
        f'(status {response.status_code})'
    )


def test_public_library_hides_an_unpublished_submission(app_fx, world):
    """A draft sheet is internal state.  Only ``published`` may be served."""
    db_path, ids = world
    conn = _conn(db_path)
    try:
        for status in ('draft', 'in_review', 'rejected', 'archived'):
            conn.execute(
                'INSERT INTO course_content_submissions '
                '(user_id, department_id, course_name, course_code, status) '
                'VALUES (?, ?, ?, ?, ?)',
                (ids['teacher_a_uid'], ids['dept_a'], f'مقرر {status}', 'C1',
                 status),
            )
        sub_id = conn.execute(
            "SELECT id FROM course_content_submissions WHERE status = 'draft' "
            'ORDER BY id DESC LIMIT 1'
        ).fetchone()['id']
        conn.commit()
    finally:
        conn.close()

    anon = app_fx.test_client()
    response = anon.get(f'/library/file/{sub_id}')
    assert response.status_code == 404, (
        f'an anonymous visitor was served a {response.status_code} '
        'unpublished submission'
    )


def test_public_course_content_page_requires_published(app_fx, world):
    db_path, ids = world
    conn = _conn(db_path)
    try:
        conn.execute(
            'INSERT INTO course_content_submissions '
            '(user_id, department_id, course_name, course_code, status) '
            "VALUES (?, ?, 'مقرر مسودة', 'C2', 'draft')",
            (ids['teacher_a_uid'], ids['dept_a']),
        )
        sub_id = conn.execute(
            "SELECT id FROM course_content_submissions WHERE status = 'draft' "
            'ORDER BY id DESC LIMIT 1'
        ).fetchone()['id']
        conn.commit()
    finally:
        conn.close()

    anon = app_fx.test_client()
    assert anon.get(f'/course-content/{sub_id}').status_code == 404


# ── 3. lifecycle authority: read permission never guards a write ────────


def test_soft_deleted_teacher_restore_requires_write_permission(app_fx, world):
    """``teachers.view`` is held by HOD.  It must not resurrect a deleted row.

    Asserted on the *effect* — the tombstone survives — rather than on a status
    code, because the API guard answers a refusal with a redirect rather than a
    403.  A refusal that still mutated the row would pass a status-code-only
    test, which is exactly the regression worth catching.
    """
    db_path, ids = world
    conn = _conn(db_path)
    try:
        conn.execute(
            'UPDATE teachers SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?',
            (ids['teacher_b'],),
        )
        conn.commit()
    finally:
        conn.close()

    c = app_fx.test_client()
    _login(c, ids['hod_uid'], 'head_of_department',
           hod_department_id=ids['dept_a'])

    response = c.post(
        f"/api/teachers/{ids['teacher_b']}/restore",
        headers={'X-CSRFToken': 't'},
    )
    assert response.status_code in (302, 403, 404), (
        'the restore call was not refused '
        f'(status {response.status_code})'
    )

    conn = _conn(db_path)
    try:
        still_deleted = conn.execute(
            'SELECT deleted_at FROM teachers WHERE id = ?', (ids['teacher_b'],)
        ).fetchone()['deleted_at']
    finally:
        conn.close()
    assert still_deleted is not None, (
        'a read-only role resurrected a soft-deleted teacher'
    )


def test_teacher_update_requires_write_permission(app_fx, world):
    """Same boundary on the ordinary update path (PUT), asserted on effect."""
    db_path, ids = world
    c = app_fx.test_client()
    _login(c, ids['hod_uid'], 'head_of_department',
           hod_department_id=ids['dept_a'])

    original = 'أستاذ b'
    response = c.put(
        f"/api/teachers/{ids['teacher_b']}",
        json={'name': 'مُعدَّل'},
        headers={'X-CSRFToken': 't'},
    )
    assert response.status_code in (302, 403, 404), (
        f'the update was not refused (status {response.status_code})'
    )

    conn = _conn(db_path)
    try:
        name = conn.execute(
            'SELECT name FROM teachers WHERE id = ?', (ids['teacher_b'],)
        ).fetchone()['name']
    finally:
        conn.close()
    assert name == original, (
        'a read-only role rewrote a teacher record'
    )


# ── durable guards against reintroducing the decision ────────────────────


def test_hod_material_routes_pin_the_department_predicate():
    """The scoping is asserted on the source, not inferred from a passing test.

    A test that only proves today's behaviour cannot tell a deliberate
    relaxation from an accident.  These pin the *decision* in the two HOD
    material handlers so removing the department predicate is a test failure.
    """
    src = (ROOT / 'page_routes' / 'hod_pages.py').read_text(encoding='utf-8')
    for fn in ('hod_material_delete', 'hod_material_download'):
        start = src.index(f'def {fn}(')
        body = src[start:start + 1200]
        assert 'department_id' in body, (
            f'{fn} no longer binds the department — a HOD could reach '
            'another department\'s materials'
        )
        assert '_hod_department_id' in body, (
            f'{fn} no longer derives the scope from the session'
        )


def test_public_file_service_pins_the_published_gate():
    """The legacy public download must keep its lifecycle mask."""
    src = (ROOT / 'services' / 'download_service.py').read_text(encoding='utf-8')
    start = src.index('def serve_submission_file(')
    body = src[start:src.index('\ndef ', start + 10)]
    assert "'published'" in body, (
        'serve_submission_file lost its published-only gate — unpublished '
        'course files would become world-readable'
    )


def test_restore_and_permanent_delete_stay_behind_manage():
    """Resurrecting or destroying a tombstone is a write, by definition."""
    src = (ROOT / 'api_routes' / 'teachers.py').read_text(encoding='utf-8')
    for fn, decorator in (
        ('api_teacher_restore', "api_permission_required('teachers.manage')"),
        ('api_teacher_hard_delete', "api_permission_required('teachers.manage')"),
        ('api_teacher_update', "api_permission_required('teachers.manage')"),
        ('api_teacher_delete', "api_permission_required('teachers.manage')"),
    ):
        start = src.index(f'def {fn}(')
        window = src[max(0, start - 400):start]
        assert decorator in window, (
            f'{fn} is no longer guarded by teachers.manage'
        )
