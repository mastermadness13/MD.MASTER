"""HOD replies to a teacher's request.

The reply path used to mix two different message schemas. Requests live in
``teacher_requests`` (``teacher_pages.teacher_messages`` writes there), but the
reply called ``add_message_reply`` and ``resolve_message``, which both target the
legacy ``message_replies`` / ``teacher_messages`` tables. ``message_replies.
message_id`` is a foreign key to ``teacher_messages(id)``, and nothing in the
codebase has ever inserted into ``teacher_messages`` — so with
``PRAGMA foreign_keys = ON`` (``database/connection.py``) the first statement
raised ``sqlite3.IntegrityError`` on *every* reply, the request was never
resolved, the reply text was never stored, and the teacher was never notified.
The HOD saw a 500 page.

These tests pin the fixed behaviour, including the department scoping that was
missing entirely: ``dept_id`` was read but never applied to the POST, so any
department head could resolve another department's request by guessing a
sequential id.
"""

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema

OWN_DEPT_NAME = 'قسم الحاسوب'
OTHER_DEPT_NAME = 'قسم \u0622\u062e\u0631'


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'hod_reply.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)

    conn.execute(
        "INSERT INTO users (username, password, role, label) "
        "VALUES ('hod_reply_user', 'x', 'head_of_department', 'أ. رئيس القسم')"
    )
    hod_uid = conn.execute(
        "SELECT id FROM users WHERE username='hod_reply_user'"
    ).fetchone()['id']

    conn.execute(
        "INSERT INTO users (username, password, role, label) "
        "VALUES ('teacher_one', 'x', 'teacher', 'أ. معلم')"
    )
    teacher_uid = conn.execute(
        "SELECT id FROM users WHERE username='teacher_one'"
    ).fetchone()['id']

    # Two departments: the HOD heads one, the other exists only so we can prove
    # the scoping rejects a request that is not theirs.
    for dept_name in (OWN_DEPT_NAME, OTHER_DEPT_NAME):
        conn.execute(
            "INSERT INTO departments (name, semesters, majors, hidden, "
            "has_sections, type) VALUES (?, 8, 8, 0, 1, 'academic')",
            (dept_name,),
        )
    own_dept = conn.execute(
        'SELECT id FROM departments WHERE name = ?', (OWN_DEPT_NAME,)
    ).fetchone()['id']
    other_dept = conn.execute(
        'SELECT id FROM departments WHERE name = ?', (OTHER_DEPT_NAME,)
    ).fetchone()['id']

    other_dept = conn.execute(
        "SELECT id FROM departments WHERE name='قسم آخر'"
    ).fetchone()['id']

    conn.execute(
        "INSERT INTO teachers (name, academic_number, department_id) "
        "VALUES ('أ. معلم واحد', 'AN-1', ?)",
        (own_dept,),
    )
    teacher_id = conn.execute(
        "SELECT id FROM teachers WHERE academic_number='AN-1'"
    ).fetchone()['id']

    # One pending request in the HOD's own department, one in another.
    conn.execute(
        'INSERT INTO teacher_requests (teacher_id, user_id, department_id, '
        "request_type, subject, message, status) "
        "VALUES (?, ?, ?, 'general', ?, ?, 'pending')",
        (teacher_id, teacher_uid, own_dept, 'طلب اعتماد', 'نص الطلب'),
    )
    own_request = conn.execute(
        "SELECT id FROM teacher_requests WHERE department_id = ?", (own_dept,)
    ).fetchone()['id']

    conn.execute(
        'INSERT INTO teacher_requests (teacher_id, user_id, department_id, '
        "request_type, subject, message, status) "
        "VALUES (?, ?, ?, 'general', ?, ?, 'pending')",
        (teacher_id, teacher_uid, other_dept, 'طلب قسم آخر', 'نص آخر'),
    )
    foreign_request = conn.execute(
        "SELECT id FROM teacher_requests WHERE department_id = ?", (other_dept,)
    ).fetchone()['id']

    conn.commit()
    conn.close()
    return {
        'path': str(db_path),
        'hod_uid': hod_uid,
        'teacher_uid': teacher_uid,
        'own_dept': own_dept,
        'other_dept': other_dept,
        'own_request': own_request,
        'foreign_request': foreign_request,
    }


@pytest.fixture
def hod_client(app_fx, db_fx):
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = db_fx['hod_uid']
        sess['role'] = 'head_of_department'
        sess['username'] = 'hod_reply_user'
        sess['department_id'] = db_fx['own_dept']
        sess['hod_department_id'] = db_fx['own_dept']
        sess['session_version'] = 1
        sess['_csrf_token'] = 't'
    c.ctx = db_fx
    return c


def _reply(hod_client, request_id, reply='تمت الموافقة'):
    """POST the HOD reply form. The CSRF token must ride along or the framework
    hook redirects with 302 before the view ever runs."""
    data = {'reply': reply, '_csrf_token': 't'}
    if request_id is not None:
        data['request_id'] = str(request_id)
    return hod_client.post('/hod/messages', data=data)


def _row(ctx, request_id):
    conn = connect(ctx['path'])
    try:
        return dict(conn.execute(
            'SELECT * FROM teacher_requests WHERE id = ?', (request_id,)
        ).fetchone())
    finally:
        conn.close()


def _notification_count(ctx, user_id):
    conn = connect(ctx['path'])
    try:
        return conn.execute(
            'SELECT COUNT(*) AS c FROM notifications WHERE user_id = ?', (user_id,)
        ).fetchone()['c']
    finally:
        conn.close()


def test_reply_does_not_500(hod_client):
    """The regression: every reply raised IntegrityError on the FK to the
    never-written ``teacher_messages`` table."""
    resp = _reply(hod_client, hod_client.ctx['own_request'])
    assert resp.status_code == 302, (
        'the reply must redirect, not 500 — the foreign key to teacher_messages '
        'is still being written'
    )


def test_reply_is_stored_and_request_resolved(hod_client):
    ctx = hod_client.ctx
    _reply(hod_client, ctx['own_request'])
    row = _row(ctx, ctx['own_request'])
    assert row['admin_reply'] == 'تمت الموافقة'
    assert row['status'] == 'resolved'
    assert row['reviewed_by'] == ctx['hod_uid']
    assert row['reviewed_at'] is not None


def test_teacher_is_notified(hod_client):
    ctx = hod_client.ctx
    before = _notification_count(ctx, ctx['teacher_uid'])
    _reply(hod_client, ctx['own_request'])
    assert _notification_count(ctx, ctx['teacher_uid']) == before + 1


def test_cannot_reply_to_another_departments_request(hod_client):
    """IDOR: the POST never checked ``hod_department_id``, so any HOD could
    resolve another department's request by walking sequential ids."""
    ctx = hod_client.ctx
    resp = _reply(hod_client, ctx['foreign_request'], reply='تعدٍ')
    assert resp.status_code == 404
    row = _row(ctx, ctx['foreign_request'])
    assert row['status'] == 'pending', 'a foreign request must stay untouched'
    assert row['admin_reply'] == ''
    assert row['reviewed_by'] is None


def test_missing_request_id_is_a_400_not_a_500(hod_client):
    """``request.form.get('request_id', type=int)`` yields None, which used to
    reach the INSERT and raise a NOT NULL violation."""
    resp = _reply(hod_client, None, reply='بلا معرف')
    assert resp.status_code == 400


def test_empty_reply_does_not_resolve(hod_client):
    ctx = hod_client.ctx
    resp = _reply(hod_client, ctx['own_request'], reply='   ')
    assert resp.status_code == 302
    assert _row(ctx, ctx['own_request'])['status'] == 'pending'


def test_legacy_reply_tables_are_never_written(hod_client):
    """``teacher_messages`` / ``message_replies`` are legacy: nothing should
    insert into them any more, and the FK from message_replies is the trap."""
    ctx = hod_client.ctx
    _reply(hod_client, ctx['own_request'])
    conn = connect(ctx['path'])
    try:
        assert conn.execute(
            'SELECT COUNT(*) AS c FROM message_replies'
        ).fetchone()['c'] == 0
        assert conn.execute(
            'SELECT COUNT(*) AS c FROM teacher_messages'
        ).fetchone()['c'] == 0
    finally:
        conn.close()
