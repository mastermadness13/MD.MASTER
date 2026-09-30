"""Shared test harness: real per-role users, a seeded database, and factories.

Why this exists
---------------
Most of the pre-existing suite injects a session by hand and assumes
``session['user_id'] == 1`` is the account it wants.  It is not:
``ensure_schema`` seeds the bootstrap ``office_manager`` account as id 1, so a
test that writes ``user_id=1, role='exam'`` is really authenticated as the
office manager while the app resolves permissions from the *granted roles* in
``user_roles``.  That mismatch is the single largest source of failures in this
repository.

This module builds the real thing instead: one real ``users`` row per role, the
matching ``user_roles`` row, a session whose ``user_id`` is resolved from the
username, and ``session['roles']`` set exactly the way login sets it.  Tests
that use :func:`login_as` therefore exercise the same authorization path a real
browser does.
"""

from __future__ import annotations

import os
import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema

# ─────────────────────────────────────────────
# Roles and the fixtures that back them
# ─────────────────────────────────────────────

ALL_ROLES = (
    'dean',
    'research_development',
    'faculty_affairs',
    'exam',
    'head_of_department',
    'teacher',
    'visitor',
)

#: ``role -> (username, label)``.  Usernames are unique per role so a session
#: can always be resolved back to the account that actually holds the role.
ROLE_ACCOUNTS = {
    'dean': ('dean_user', 'العميد'),
    'research_development': ('rnd_user', 'قسم البحث والتطوير والمناهج'),
    'faculty_affairs': ('office_user', 'مكتب إدارة أعضاء هيئة التدريس'),
    'exam': ('exam_user', 'قسم الدراسة والامتحانات'),
    'head_of_department': ('hod_user', 'رئيس القسم العلمي'),
    'teacher': ('teacher_user', 'عضو هيئة تدريس'),
    'visitor': ('visitor_user', 'الزائر العام'),
}

ROLE_PASSWORD = 'HarnessPass123!'


# ─────────────────────────────────────────────
# Schema helpers
# ─────────────────────────────────────────────

def build_schema(db_path: str) -> sqlite3.Connection:
    """Create a fresh database at *db_path* from schema.sql + migrations."""
    conn = connect(db_path)
    with open('database/schema.sql', encoding='utf-8') as handle:
        conn.executescript(handle.read())
    ensure_schema(conn)
    conn.commit()
    return conn


def read_rows(db_path: str, sql: str, params=()):
    """Run *sql* against *db_path* and return a list of plain dicts."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def read_row(db_path: str, sql: str, params=()):
    """Run *sql* and return the first row as a dict, or ``None``."""
    rows = read_rows(db_path, sql, params)
    return rows[0] if rows else None


def scalar(db_path: str, sql: str, params=()):
    """Return the first column of the first row."""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def run_sql(db_path: str, sql: str, params=()) -> None:
    """Execute a write statement against *db_path*."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Core fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """A migrated, seeded-by-migration database wired into ``flask_db``.

    ``flask_db.DATABASE`` is what ``get_db()`` reads on every request, so
    monkeypatching it is what makes a test client talk to *this* file.
    """
    path = tmp_path / 'harness.db'
    conn = build_schema(str(path))
    conn.close()
    monkeypatch.setattr(flask_db, 'DATABASE', str(path))
    return str(path)


@pytest.fixture
def raw_db(db_path):
    """A live connection to :func:`db_path` for direct service-level assertions."""
    conn = connect(db_path)
    yield conn
    conn.close()


# ─────────────────────────────────────────────
# Reference data
# ─────────────────────────────────────────────

def seed_departments(conn) -> dict:
    """Insert a small department set and return ``{name: id}``."""
    rows = [
        ('القسم العام', 1, 1, 'academic'),
        ('قسم الحاسوب', 8, 8, 'academic'),
        ('قسم المدنية', 5, 6, 'academic'),
        ('إدارة الكلية', 4, 4, 'administrative'),
    ]
    for name, semesters, majors, dtype in rows:
        conn.execute(
            'INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, '
            'has_sections, type) VALUES (?, ?, ?, 0, 1, ?)',
            (name, semesters, majors, dtype),
        )
    conn.commit()
    return {
        name: conn.execute(
            'SELECT id FROM departments WHERE name = ?', (name,)
        ).fetchone()['id']
        for name, _s, _m, _t in rows
    }


def seed_users(conn, department_id=None) -> dict:
    """Create one real account per role. Returns ``{role: user_id}``.

    Both ``users.role`` (the landing role) and ``user_roles`` (the granted set)
    are written, exactly as the login path expects to find them.
    """
    from werkzeug.security import generate_password_hash

    ids = {}
    for role in ALL_ROLES:
        username, label = ROLE_ACCOUNTS[role]
        row = conn.execute(
            'SELECT id FROM users WHERE username = ?', (username,)
        ).fetchone()
        if row:
            user_id = row['id']
        else:
            cur = conn.execute(
                'INSERT INTO users (username, password, role, label, '
                'department_id, session_version, is_active) '
                'VALUES (?, ?, ?, ?, ?, 1, 1)',
                (username, generate_password_hash(ROLE_PASSWORD), role, label,
                 department_id),
            )
            user_id = cur.lastrowid
        conn.execute(
            'INSERT OR IGNORE INTO user_roles (user_id, role) VALUES (?, ?)',
            (user_id, role),
        )
        ids[role] = user_id
    conn.commit()
    return ids


def seed_teacher(conn, department_id, *, name='أستاذ الاختبار', user_id=None,
                 hod_department_id=None, academic_number='AN-1'):
    """Insert a teacher row and return its id."""
    cur = conn.execute(
        'INSERT INTO teachers (name, department_id, hod_department_id, '
        'academic_number, user_id) VALUES (?, ?, ?, ?, ?)',
        (name, department_id, hod_department_id, academic_number, user_id),
    )
    conn.commit()
    return cur.lastrowid


def seed_course(conn, department_id, *, code='CS101', name='مقرر', year=1,
                semester=1, theoretical=2, practical=2):
    """Insert a course row and return its id."""
    cur = conn.execute(
        'INSERT INTO courses (code, name, department_id, year, semester, '
        'theoretical_hours, practical_hours, total_hours) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (code, name, department_id, year, semester, theoretical, practical,
         theoretical + practical),
    )
    conn.commit()
    return cur.lastrowid


def seed_room(conn, *, name='قاعة 101', code='R101', capacity=40,
              department_id=None):
    """Insert a room row and return its id."""
    cur = conn.execute(
        'INSERT INTO rooms (name, code, capacity, department_id) VALUES (?, ?, ?, ?)',
        (name, code, capacity, department_id),
    )
    conn.commit()
    return cur.lastrowid


# ─────────────────────────────────────────────
# The populated fixture most tests want
# ─────────────────────────────────────────────

def _seed_all(conn, db_path) -> dict:
    """Seed departments, users, teacher, course and room; return the id dict."""
    departments = seed_departments(conn)
    users = seed_users(conn, department_id=departments['قسم الحاسوب'])

    # Give the HOD account the department it heads, so department-scoped views
    # have something to scope to.
    run_sql(
        db_path,
        'UPDATE users SET department_id = ? WHERE id = ?',
        (departments['قسم الحاسوب'], users['head_of_department']),
    )

    teacher_id = seed_teacher(
        conn, departments['قسم الحاسوب'],
        name='أ.د. أحمد المعلم', user_id=users['teacher'],
        hod_department_id=departments['قسم الحاسوب'],
    )
    course_id = seed_course(conn, departments['قسم الحاسوب'])
    room_id = seed_room(conn, department_id=departments['قسم الحاسوب'])

    return {
        'db_path': db_path,
        'departments': departments,
        'users': users,
        'teacher_id': teacher_id,
        'course_id': course_id,
        'room_id': room_id,
        'hod_department_id': departments['قسم الحاسوب'],
    }


@pytest.fixture
def seeded(raw_db, db_path):
    """Database with departments, one user per role, a teacher, a course, a room.

    Returns a dict with the ids tests assert against.  ``users`` maps a role to
    its real ``users.id``; every session built from this fixture resolves to a
    row that actually holds that role.
    """
    return _seed_all(raw_db, db_path)


@pytest.fixture(scope='session')
def matrix_db(tmp_path_factory):
    """One read-mostly database shared by the permission-matrix sweeps.

    Sweeping every route x role produces ~2500 tests; giving each one a fresh
    ``build_schema`` made the sweeps take minutes, so they share this single
    seeded file instead.  Only the stateful session-lifecycle tests should use
    the per-test :func:`db_path` / :func:`seeded` fixtures.
    """
    path = str(tmp_path_factory.mktemp('matrix') / 'matrix.db')
    conn = build_schema(path)
    ids = _seed_all(conn, path)
    conn.close()

    original = flask_db.DATABASE
    flask_db.DATABASE = path
    yield ids
    flask_db.DATABASE = original


# ─────────────────────────────────────────────
# Sessions
# ─────────────────────────────────────────────

def login_as(app, db_path, role, *, extra_roles=(), active_role=None,
             department_id=None, force_password_change=False):
    """Return a test client holding a *real* session for *role*.

    The session is populated the way :func:`login` populates it: the user's real
    id, the granted role set, and the active role.  ``session['session_version']``
    is read from the row so the ``enforce_session_version`` hook is satisfied
    exactly as it is in production.
    """
    username, _label = ROLE_ACCOUNTS[role]
    user = read_row(
        db_path, 'SELECT id, session_version, is_active FROM users WHERE username = ?',
        (username,),
    )
    assert user is not None, f'no harness user for role {role!r}'
    assert user['is_active'] == 1, f'harness user for {role!r} is not active'

    granted = [role, *extra_roles]
    active = active_role or role

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = user['id']
        sess['username'] = username
        sess['role'] = active
        sess['roles'] = granted
        sess['session_version'] = user['session_version']
        sess['_csrf_token'] = CSRF_TOKEN
        if department_id is not None:
            sess['department_id'] = department_id
        if force_password_change:
            sess['force_password_change'] = True
    return client


CSRF_TOKEN = 'harness-csrf-token'


def session_for(client, db_path, username, *, active_role=None, extra_roles=(),
                department_id=None, force_password_change=False,
                csrf_token=CSRF_TOKEN, extra=None):
    """Populate ``client``'s session for the *real* users row named *username*.

    The fix for the ``user_id = 1`` trap described in the module docstring:
    resolve the id from ``users.username`` and mirror ``session_version`` and
    ``session['roles']`` exactly the way :func:`login` does, so
    ``enforce_session_version`` agrees with the injected session instead of
    silently re-syncing it to the bootstrap account.

    Returns the resolved ``users.id``.
    """
    row = read_row(
        db_path, 'SELECT id, role, session_version, is_active FROM users WHERE username = ?',
        (username,),
    )
    assert row is not None, f'no users row named {username!r}'
    assert row['is_active'] == 1, f'user {username!r} is not active'

    granted = [
        r['role'] for r in read_rows(
            db_path, 'SELECT DISTINCT role FROM user_roles WHERE user_id = ? ORDER BY role',
            (row['id'],),
        )
    ] or [row['role']]
    roles = sorted({*granted, *extra_roles})
    with client.session_transaction() as sess:
        sess['user_id'] = row['id']
        sess['username'] = username
        sess['role'] = active_role or row['role']
        sess['roles'] = roles
        sess['session_version'] = row['session_version']
        if csrf_token is not None:
            sess['_csrf_token'] = csrf_token
        if department_id is not None:
            sess['department_id'] = department_id
        if force_password_change:
            sess['force_password_change'] = True
        for key, value in (extra or {}).items():
            sess[key] = value
    return row['id']


def csrf(client=None) -> dict:
    """A CSRF payload matching :data:`CSRF_TOKEN`."""
    return {'_csrf_token': CSRF_TOKEN}


def json_headers(**extra):
    """Headers that make the app answer with JSON instead of an HTML redirect."""
    headers = {'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'}
    headers.update(extra)
    return headers


def body_of(response) -> str:
    """Response body as text, regardless of how the client streamed it."""
    return response.get_data(as_text=True)


def json_of(response):
    """Parse a JSON body, returning ``None`` when the body is not JSON."""
    try:
        return response.get_json(silent=True)
    except Exception:
        return None


# ─────────────────────────────────────────────
# The one application instance
# ─────────────────────────────────────────────

_APP_CACHE = {'app': None}


def get_app():
    """Create the Flask app exactly once and return the shared instance.

    ``create_app()`` registers the blueprints, and calling it a second time in
    the same process raises
    ``AssertionError: setup method 'errorhandler' can no longer be called``.
    Both the session-scoped ``app_fx`` fixture and any test module that needs
    the ``url_map`` at collection time (for ``pytest.mark.parametrize``) must
    therefore hand out *the same* app.  This function is that cache.
    """
    if _APP_CACHE['app'] is None:
        from app import create_app
        app = create_app()
        app.config['TESTING'] = True
        _APP_CACHE['app'] = app
    return _APP_CACHE['app']


# ─────────────────────────────────────────────
# Endpoint inventory (drives the blanket matrix tests)
# ─────────────────────────────────────────────

def iter_rules(app):
    """Yield ``(rule, endpoint, methods)`` for every real application route."""
    for rule in app.url_map.iter_rules():
        if rule.endpoint == 'static':
            continue
        methods = tuple(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
        if not methods:
            continue
        yield rule.rule, rule.endpoint, methods


def concrete_path(rule: str) -> str:
    """Replace ``<int:x>``/``<x>`` converters with a value that always exists."""
    import re

    path = re.sub(r'<int:\w+>', '1', rule)
    path = re.sub(r'<[^>]*:(\w+)>', r'1', path)
    path = re.sub(r'<(?!/)([^<>]+)>', r'1', path)
    return path


def required_permission(app, endpoint):
    """Return the permission a view declares, or ``None``."""
    view = app.view_functions.get(endpoint)
    return getattr(view, '_required_permission', None) if view else None


def required_roles(app, endpoint):
    """Return ``('all', roles)`` / ``('any', roles)`` / ``None`` for a view."""
    view = app.view_functions.get(endpoint)
    if view is None:
        return None
    if getattr(view, '_required_roles', None):
        return ('all', view._required_roles)
    if getattr(view, '_required_any_roles', None):
        return ('any', view._required_any_roles)
    return None


def has_permission_for(role, permission) -> bool:
    """Pure role→permission check (no request context involved)."""
    from core.constants import ROLE_PERMISSIONS

    return permission in ROLE_PERMISSIONS.get(role, set())


__all__ = [
    'ALL_ROLES',
    'ROLE_ACCOUNTS',
    'ROLE_PASSWORD',
    'CSRF_TOKEN',
    'build_schema',
    'concrete_path',
    'csrf',
    'has_permission_for',
    'iter_rules',
    'json_headers',
    'json_of',
    'login_as',
    'read_row',
    'read_rows',
    'required_permission',
    'required_roles',
    'run_sql',
    'scalar',
    'session_for',
    'seed_course',
    'seed_departments',
    'seed_room',
    'seed_teacher',
    'seed_users',
    'get_app',
    'body_of',
    'db_path',
    'matrix_db',
    'raw_db',
    'seeded',
]
