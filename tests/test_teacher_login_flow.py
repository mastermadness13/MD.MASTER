"""Teacher login flow under the enforced credential-management design.

  * username + temporary initial code are chosen/set ONLY at member creation
    (``/teachers/create``); the edit flow refuses credential fields (403).
  * the first successful login with a temporary code forces a mandatory
    password change before normal application access.
  * faculty affairs can regenerate a code via ``/teachers/reset-password``,
    which releases a stuck/expired code by issuing a fresh one.
"""

import re
import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema

_PASSWORD = 'NewSecurePass123!'
_CODE_RE = re.compile(r'رمز الدخول المؤقت:\s*([A-Za-z0-9_-]+)')


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


@pytest.fixture
def captured_emails(monkeypatch):
    """Capture initial-code emails instead of attempting a real SMTP send."""
    sent = []

    def _fake_send(to_email, username, code, expiry_days, *, renewed=False):
        sent.append({
            'email': to_email,
            'username': username,
            'code': code,
            'renewed': bool(renewed),
        })
        return True

    monkeypatch.setattr(
        'services.email_service.send_initial_login_code', _fake_send
    )
    return sent


def _office_client(app_fx):
    client = app_fx.test_client()
    with client.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
        sess['user_id'] = 1
        sess['role'] = 'faculty_affairs'
        sess['username'] = 'office_manager'
    return client


def _flash(client):
    with client.session_transaction() as sess:
        return sess.get('_flashes', [])


def _code_from_flash(flashes):
    for _, msg in flashes:
        m = _CODE_RE.search(msg)
        if m:
            return m.group(1)
    raise AssertionError(f'رمز الدخول المؤقت غير موجود في الرسائل: {flashes}')


# ── Backend denial: the edit flow must refuse credential fields ─────────

def test_edit_rejects_username_and_password_fields(app_fx, db_fx):
    """Admin can no longer change credentials on /teachers/edit/<id>: the
    fields are blocked with an explicit 403 message."""
    client = _office_client(app_fx)
    r = client.post('/teachers/edit/1', data={
        'name': 'أستاذ مستورد',
        'username': 'imported_t1',
        'new_password': 'SecurePass123!',
        'department_ids[]': '1',
        'position': '',
        '_csrf_token': 'test-token',
    })
    assert r.status_code == 403
    assert 'إدارة بيانات الدخول متاحة عند إنشاء العضو فقط' in r.get_data(as_text=True)


def test_edit_rejects_username_field_even_when_empty(app_fx, db_fx):
    """Any presence of the username field (even an empty value) is refused."""
    client = _office_client(app_fx)
    r = client.post('/teachers/edit/1', data={
        'name': 'أستاذ مستورد',
        'username': '',
        'department_ids[]': '1',
        'position': '',
        '_csrf_token': 'test-token',
    })
    assert r.status_code == 403


# ── Creation sets username + a temporary code with forced first change ───

def test_create_with_username_then_login_forces_password_change(app_fx, db_fx):
    """A member created with a username gets a temporary code, the first login
    with it forces a mandatory password change, the old code dies and the new
    password logs in straight to the dashboard afterwards."""
    client = _office_client(app_fx)
    r1 = client.post('/teachers/create', data={
        'name': 'أستاذ مستورد',
        'username': 'imported_t1',
        'department_ids[]': '1',
        'position': '',
        '_csrf_token': 'test-token',
    })
    assert r1.status_code == 302
    flashes = _flash(client)
    assert any('تم إضافة عضو هيئة التدريس' in m for _, m in flashes), flashes
    code = _code_from_flash(flashes)

    conn = sqlite3.connect(db_fx)
    conn.row_factory = sqlite3.Row
    user = conn.execute(
        'SELECT * FROM users WHERE username=?', ('imported_t1',)
    ).fetchone()
    conn.close()
    assert user['force_password_change'] == 1
    assert user['initial_login_code_used'] == 0
    assert user['initial_login_code_hash']

    login = app_fx.test_client()
    with login.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r2 = login.post('/login', data={
        'username': 'imported_t1',
        'password': code,
        '_csrf_token': 'test-token',
    })
    assert r2.status_code == 302
    assert 'change-password' in r2.headers.get('Location', '')

    # the mandatory first change: temporary code as the current password
    r3 = login.post('/change-password', data={
        'current_password': code,
        'new_password': _PASSWORD,
        'confirm_password': _PASSWORD,
        '_csrf_token': 'test-token',
    })
    assert r3.status_code == 302  # forced change lands on the dashboard

    conn = sqlite3.connect(db_fx)
    conn.row_factory = sqlite3.Row
    user = conn.execute(
        'SELECT * FROM users WHERE username=?', ('imported_t1',)
    ).fetchone()
    conn.close()
    assert user['force_password_change'] == 0
    assert user['initial_login_code_hash'] is None
    assert user['initial_login_code_used'] == 1

    # the temporary code is dead after the change
    fresh = app_fx.test_client()
    with fresh.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r4 = fresh.post('/login', data={
        'username': 'imported_t1',
        'password': code,
        '_csrf_token': 'test-token',
    })
    assert r4.status_code == 200
    assert 'اسم المستخدم أو كلمة المرور غير صحيحة' in r4.get_data(as_text=True)

    # the new password logs in without any further forced change
    fresh2 = app_fx.test_client()
    with fresh2.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r5 = fresh2.post('/login', data={
        'username': 'imported_t1',
        'password': _PASSWORD,
        '_csrf_token': 'test-token',
    })
    assert r5.status_code == 302
    assert r5.headers.get('Location') != '/login'
    assert 'change-password' not in r5.headers.get('Location', '')


def test_create_username_only_sets_initial_code_then_wrong_password_rejected(app_fx, db_fx):
    """A username-only creation still produces a temporary code account: a
    typed guess is rejected even though the username exists, while the real
    code works and triggers the forced change."""
    client = _office_client(app_fx)
    r1 = client.post('/teachers/create', data={
        'name': 'أستاذ مستورد',
        'username': 'imported_t2',
        'department_ids[]': '1',
        'position': '',
        '_csrf_token': 'test-token',
    })
    assert r1.status_code == 302
    code = _code_from_flash(_flash(client))

    conn = sqlite3.connect(db_fx)
    conn.row_factory = sqlite3.Row
    user = conn.execute(
        "SELECT u.* FROM users u JOIN teachers t ON t.user_id = u.id "
        "WHERE u.username = ?", ('imported_t2',),
    ).fetchone()
    conn.close()
    assert user['force_password_change'] == 1
    assert user['initial_login_code_used'] == 0
    assert user['initial_login_code_hash']

    login = app_fx.test_client()
    with login.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r2 = login.post('/login', data={
        'username': 'imported_t2', 'password': 'SomethingElse!',
        '_csrf_token': 'test-token',
    })
    assert r2.status_code == 200
    assert 'اسم المستخدم أو كلمة المرور غير صحيحة' in r2.get_data(as_text=True)

    r3 = login.post('/login', data={
        'username': 'imported_t2', 'password': code,
        '_csrf_token': 'test-token',
    })
    assert r3.status_code == 302
    assert 'change-password' in r3.headers.get('Location', '')


# ── Username validation errors on the create form ────────────────────────

def test_create_short_username_shows_arabic_error(app_fx, db_fx):
    client = _office_client(app_fx)
    r = client.post('/teachers/create', data={
        'name': 'أستاذ قصير',
        'username': 'x',
        'department_ids[]': '1',
        'position': '',
        '_csrf_token': 'test-token',
    })
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'نيك نيم الدخول قصير جداً' in body
    assert 'value="x"' in body  # the typed nickname is preserved


def test_create_duplicate_username_shows_arabic_error(app_fx, db_fx):
    client = _office_client(app_fx)
    r = client.post('/teachers/create', data={
        'name': 'أستاذ مكرر',
        'username': 'office_manager',
        'department_ids[]': '1',
        'position': '',
        '_csrf_token': 'test-token',
    })
    assert r.status_code == 200
    assert 'نيك نيم الدخول مستخدم مسبقاً' in r.get_data(as_text=True)


# ── Initial code lifecycle (service-level creation) ──────────────────────

def test_initial_code_login_forces_change_then_accepts_new_password(app_fx, db_fx):
    """Service-created initial-code account: first login goes straight to the
    mandatory change-password page, the code is invalidated by that login and
    the new password is accepted afterwards."""
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
    assert 'change-password' in r.headers.get('Location', '')

    r2 = client.post('/change-password', data={
        'current_password': creds['password'],
        'new_password': _PASSWORD,
        'confirm_password': _PASSWORD,
        '_csrf_token': 'test-token',
    })
    assert r2.status_code == 302  # forced change lands on the dashboard

    # the old code is dead; the new password works without forcing again
    login2 = app_fx.test_client()
    with login2.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r3 = login2.post('/login', data={
        'username': creds['username'], 'password': creds['password'],
        '_csrf_token': 'test-token',
    })
    assert r3.status_code == 200
    assert 'اسم المستخدم أو كلمة المرور غير صحيحة' in r3.get_data(as_text=True)
    r4 = login2.post('/login', data={
        'username': creds['username'], 'password': _PASSWORD,
        '_csrf_token': 'test-token',
    })
    assert r4.status_code == 302
    assert 'change-password' not in r4.headers.get('Location', '')


def test_reset_password_releases_stuck_expired_code(app_fx, db_fx, captured_emails):
    """A code that expired unused locks the account at login; the office's
    reset-password flow issues a fresh code that releases it."""
    import sqlite3 as _s
    conn = _s.connect(db_fx)
    conn.row_factory = _s.Row
    from database.repositories.teacher_repository import TeacherRepository
    from database.repositories.user_repository import UserRepository
    from services.teacher_service import TeacherService
    svc = TeacherService(conn, TeacherRepository(conn), UserRepository(conn))
    creds = svc.create_teacher({
        'name': 'عضو عالق بالرمز', 'email': 'stuck@example.com', 'phone': '',
        'department_id': 1, 'academic_number': 'AN-STUCK2',
        'qualification_id': None, 'rank_id': None, 'classification_id': None,
        'national_id': '', 'contract_date': '', 'tasks': '',
    }, department_ids=[1], additional_roles=None)
    # expire the unused code so the login becomes locked
    conn.execute(
        'UPDATE users SET initial_login_code_expires = ? WHERE username = ?',
        ('2000-01-01 00:00:00', creds['username']),
    )
    conn.commit()
    conn.close()

    # locked: correct password but an expired initial code
    login = app_fx.test_client()
    with login.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r = login.post('/login', data={
        'username': creds['username'], 'password': creds['password'],
        '_csrf_token': 'test-token',
    })
    assert r.status_code == 200
    assert 'انتهت صلاحية رمز الدخول الأولي' in r.get_data(as_text=True)

    # office manager regenerates the code
    tid = sqlite3.connect(db_fx).execute(
        "SELECT t.id FROM teachers t JOIN users u ON u.id = t.user_id "
        "WHERE u.username = ?", (creds['username'],),
    ).fetchone()[0]
    office = _office_client(app_fx)
    rr = office.post(f'/teachers/reset-password/{tid}', data={
        '_csrf_token': 'test-token',
    })
    assert rr.status_code == 302
    flashes = _flash(office)
    assert any('تم إنشاء رمز دخول جديد' in m for _, m in flashes), flashes
    assert any(creds['username'] in m for _, m in flashes), flashes
    # the renewed code is shown on-screen in the success message so the office
    # can hand it over directly (no personal email needed) — this is the flow
    # Hanan's case relies on
    on_screen = [(c, m) for c, m in flashes if 'تم إنشاء رمز دخول جديد' in m]
    assert on_screen
    new_code = _code_from_flash(on_screen)

    conn = sqlite3.connect(db_fx)
    conn.row_factory = sqlite3.Row
    user = conn.execute(
        'SELECT * FROM users WHERE username=?', (creds['username'],)
    ).fetchone()
    conn.close()
    assert user['force_password_change'] == 1
    assert user['initial_login_code_used'] == 0
    assert user['initial_login_code_hash']
    assert user['initial_login_code_expires'] > '2000-01-01 00:00:00'

    # the old code is dead afterwards
    login2 = app_fx.test_client()
    with login2.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r2 = login2.post('/login', data={
        'username': creds['username'], 'password': creds['password'],
        '_csrf_token': 'test-token',
    })
    assert r2.status_code == 200
    assert 'اسم المستخدم أو كلمة المرور غير صحيحة' in r2.get_data(as_text=True)

    # the renewed code logs in and triggers the forced change
    r3 = login2.post('/login', data={
        'username': creds['username'], 'password': new_code,
        '_csrf_token': 'test-token',
    })
    assert r3.status_code == 302
    assert 'change-password' in r3.headers.get('Location', '')


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