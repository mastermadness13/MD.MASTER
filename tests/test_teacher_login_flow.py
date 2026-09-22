"""End-to-end login flow for teachers without a linked account.

Reproduces the office-manager workflow: a teacher that entered the system
without a login account (e.g. imported from the schedule) gets username +
password set in the edit form, then must be able to log in with them.
"""

import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'teacher_login.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))

    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) "
        "VALUES ('office_manager', 'x', 'faculty_affairs', 'مدير مكتب أعضاء هيئة التدريس')"
    )
    conn.execute(
        "INSERT INTO departments (name, semesters, majors, hidden, has_sections, type) "
        "VALUES ('قسم الحاسوب', 7, 8, 0, 1, 'academic')"
    )
    dept_id = conn.execute(
        "SELECT id FROM departments WHERE name='قسم الحاسوب'"
    ).fetchone()['id']
    # Imported-style teacher: NO linked login account (teachers.user_id is NULL)
    conn.execute(
        "INSERT INTO teachers (name, department_id) VALUES ('أستاذ مستورد', ?)",
        (dept_id,),
    )
    conn.commit()
    conn.close()
    return str(db_path)


def _office_client(app_fx):
    client = app_fx.test_client()
    with client.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
        sess['user_id'] = 1
        sess['role'] = 'faculty_affairs'
        sess['username'] = 'office_manager'
    return client


def test_edit_sets_credentials_then_login_succeeds(app_fx, db_fx):
    """Setting username+password on an unlinked teacher creates the account and
    the same credentials log in afterwards."""
    client = _office_client(app_fx)
    r1 = client.post('/teachers/edit/1', data={
        'name': 'أستاذ مستورد',
        'username': 'imported_t1',
        'new_password': 'SecurePass123!',
        'department_ids[]': '1',
        'position': '',
        '_csrf_token': 'test-token',
    })
    assert r1.status_code == 302
    with client.session_transaction() as sess:
        flashes = sess.get('_flashes', [])
    assert any('تم تحديث بيانات الدخول بنجاح' in m for _, m in flashes), flashes

    # Now a completely fresh browser logs in with those credentials.
    login = app_fx.test_client()
    with login.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r2 = login.post('/login', data={
        'username': 'imported_t1',
        'password': 'SecurePass123!',
        '_csrf_token': 'test-token',
    })
    assert r2.status_code == 302
    assert r2.headers.get('Location') != '/login'

    conn = sqlite3.connect(db_fx)
    conn.row_factory = sqlite3.Row
    user = conn.execute(
        'SELECT * FROM users WHERE username=?', ('imported_t1',)
    ).fetchone()
    conn.close()
    # Direct password means immediate login: no pending activation code.
    assert user['force_password_change'] == 0
    assert user['initial_login_code_used'] == 1
    assert user['initial_login_code_hash'] is None


def test_office_set_password_login_not_forced_to_change(app_fx, db_fx):
    """An account created with an office-set password logs in straight to the
    dashboard — it must NOT be sent to the forced change-password page."""
    client = _office_client(app_fx)
    assert client.post('/teachers/edit/1', data={
        'name': 'أستاذ مستورد',
        'username': 'off_pass_t',
        'new_password': 'OfficePass123!',
        'department_ids[]': '1',
        'position': '',
        '_csrf_token': 'test-token',
    }).status_code == 302

    login = app_fx.test_client()
    with login.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r = login.post('/login', data={
        'username': 'off_pass_t',
        'password': 'OfficePass123!',
        '_csrf_token': 'test-token',
    })
    assert r.status_code == 302
    assert 'change-password' not in r.headers.get('Location', '')


def test_office_set_password_clears_stuck_code_mode(app_fx, db_fx):
    """An account stuck in initial-code mode (code never deliverable) is
    released by an office-set password: login no longer forces change-password."""
    import sqlite3 as _s
    conn = _s.connect(db_fx)
    conn.row_factory = _s.Row
    from database.repositories.teacher_repository import TeacherRepository
    from database.repositories.user_repository import UserRepository
    from services.teacher_service import TeacherService
    svc = TeacherService(conn, TeacherRepository(conn), UserRepository(conn))
    creds = svc.create_teacher({
        'name': 'عضو عالق بالرمز', 'email': '', 'phone': '', 'department_id': 1,
        'academic_number': 'AN-STUCK', 'qualification_id': None, 'rank_id': None,
        'classification_id': None, 'national_id': '', 'contract_date': '', 'tasks': '',
    }, department_ids=[1], additional_roles=None)
    conn.close()

    # office manager: set username + direct password on the now-unlinked? no — linked account
    tid = sqlite3.connect(db_fx).execute(
        "SELECT t.id FROM teachers t JOIN users u ON u.id=t.user_id WHERE u.username=?",
        (creds['username'],),
    ).fetchone()[0]
    client = _office_client(app_fx)
    assert client.post(f'/teachers/edit/{tid}', data={
        'name': 'عضو عالق بالرمز',
        'username': creds['username'],
        'new_password': 'ReleasePass123!',
        'department_ids[]': '1',
        'position': '',
        '_csrf_token': 'test-token',
    }).status_code == 302

    login = app_fx.test_client()
    with login.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r = login.post('/login', data={
        'username': creds['username'], 'password': 'ReleasePass123!',
        '_csrf_token': 'test-token',
    })
    assert r.status_code == 302
    assert 'change-password' not in r.headers.get('Location', '')

    conn = sqlite3.connect(db_fx)
    conn.row_factory = sqlite3.Row
    user = conn.execute('SELECT * FROM users WHERE username=?', (creds['username'],)).fetchone()
    conn.close()
    assert user['force_password_change'] == 0
    assert user['initial_login_code_hash'] is None


def test_initial_code_login_enters_then_voluntary_change(app_fx, db_fx):
    """Initial-code account: login enters the app immediately (no forced
    change-password), the code is invalidated by that first login, and the user
    can change the password voluntarily via /change-password using the code as
    the current password."""
    import sqlite3 as _s
    conn = _s.connect(db_fx)
    conn.row_factory = _s.Row
    from database.repositories.teacher_repository import TeacherRepository
    from database.repositories.user_repository import UserRepository
    from services.teacher_service import TeacherService
    svc = TeacherService(conn, TeacherRepository(conn), UserRepository(conn))
    creds = svc.create_teacher({
        'name': 'عضو برمز أولي', 'email': '', 'phone': '', 'department_id': 1,
        'academic_number': 'AN-CODEX', 'qualification_id': None, 'rank_id': None,
        'classification_id': None, 'national_id': '', 'contract_date': '', 'tasks': '',
    }, department_ids=[1], additional_roles=None)
    conn.close()

    client = app_fx.test_client()
    with client.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r = client.post('/login', data={
        'username': creds['username'], 'password': creds['password'],
        '_csrf_token': 'test-token',
    })
    assert r.status_code == 302
    assert 'change-password' not in r.headers.get('Location', '')

    # first login invalidated the emailed code → voluntary change uses it as current
    with client.session_transaction() as sess:
        token = sess['_csrf_token']
    r2 = client.post('/change-password', data={
        'current_password': creds['password'],
        'new_password': 'NewSecurePass123!',
        'confirm_password': 'NewSecurePass123!',
        '_csrf_token': token,
    })
    assert r2.status_code == 200

    # old code is now dead; the new password works
    login2 = app_fx.test_client()
    with login2.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r3 = login2.post('/login', data={
        'username': creds['username'], 'password': creds['password'],
        '_csrf_token': 'test-token',
    })
    assert r3.status_code == 200
    r4 = login2.post('/login', data={
        'username': creds['username'], 'password': 'NewSecurePass123!',
        '_csrf_token': 'test-token',
    })
    assert r4.status_code == 302
    assert 'change-password' not in r4.headers.get('Location', '')


def test_edit_username_only_sets_initial_code_not_logged_in_yet(app_fx, db_fx):
    """Username-only update still creates the account but in initial-code mode:
    a random password must come from the email, so the typed one is rejected."""
    client = _office_client(app_fx)
    r1 = client.post('/teachers/edit/1', data={
        'name': 'أستاذ مستورد',
        'username': 'imported_t2',
        'new_password': '',
        'department_ids[]': '1',
        'position': '',
        '_csrf_token': 'test-token',
    })
    assert r1.status_code == 302

    conn = sqlite3.connect(db_fx)
    conn.row_factory = sqlite3.Row
    user = conn.execute(
        'SELECT * FROM users JOIN teachers t ON t.user_id = users.id WHERE t.id = 1'
    ).fetchone()
    conn.close()
    assert user['username'] == 'imported_t2'
    assert user['force_password_change'] == 1
    assert user['initial_login_code_hash']

    login = app_fx.test_client()
    with login.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r2 = login.post('/login', data={
        'username': 'imported_t2',
        'password': 'SomethingElse!',
        '_csrf_token': 'test-token',
    })
    assert r2.status_code == 200
    assert 'اسم المستخدم أو كلمة المرور غير صحيحة' in r2.get_data(as_text=True)


def test_expired_unused_code_shows_distinct_login_message(app_fx, db_fx):
    """An account whose initial code expired unused is refused login, but the
    user (who typed the correct password) sees a clear recovery message instead
    of the misleading generic failure."""
    import sqlite3 as _s
    conn = _s.connect(db_fx)
    conn.row_factory = _s.Row
    from database.repositories.teacher_repository import TeacherRepository
    from database.repositories.user_repository import UserRepository
    from services.teacher_service import TeacherService
    svc = TeacherService(conn, TeacherRepository(conn), UserRepository(conn))
    creds = svc.create_teacher({
        'name': 'عضو رمز منتهي', 'email': '', 'phone': '', 'department_id': 1,
        'academic_number': 'AN-EXPD', 'qualification_id': None, 'rank_id': None,
        'classification_id': None, 'national_id': '', 'contract_date': '', 'tasks': '',
    }, department_ids=[1], additional_roles=None)
    conn.execute(
        'UPDATE users SET initial_login_code_expires = ? WHERE username = ?',
        ('2000-01-01 00:00:00', creds['username']),
    )
    conn.commit()
    conn.close()

    login = app_fx.test_client()
    with login.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r = login.post('/login', data={
        'username': creds['username'], 'password': creds['password'],
        '_csrf_token': 'test-token',
    })
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'اسم المستخدم أو كلمة المرور غير صحيحة' not in body
    assert 'انتهت صلاحية رمز الدخول الأولي' in body


def test_wrong_password_keeps_generic_login_message(app_fx, db_fx):
    """A wrong password (even for an existing username) must keep the generic
    message so account existence is never disclosed."""
    import sqlite3 as _s
    conn = _s.connect(db_fx)
    conn.row_factory = _s.Row
    from database.repositories.teacher_repository import TeacherRepository
    from database.repositories.user_repository import UserRepository
    from services.teacher_service import TeacherService
    svc = TeacherService(conn, TeacherRepository(conn), UserRepository(conn))
    creds = svc.create_teacher({
        'name': 'عضو كلمة خاطئة', 'email': '', 'phone': '', 'department_id': 1,
        'academic_number': 'AN-WRONGPW', 'qualification_id': None, 'rank_id': None,
        'classification_id': None, 'national_id': '', 'contract_date': '', 'tasks': '',
    }, department_ids=[1], additional_roles=None)
    conn.close()

    login = app_fx.test_client()
    with login.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r = login.post('/login', data={
        'username': creds['username'], 'password': 'TotallyWrong!',
        '_csrf_token': 'test-token',
    })
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'اسم المستخدم أو كلمة المرور غير صحيحة' in body
    assert 'انتهت صلاحية رمز الدخول الأولي' not in body