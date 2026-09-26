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
# create_teacher() now takes an office-assigned username and initial password
# instead of generating them.
_INITIAL_PASSWORD = 'OfficeInit123!'
_CODE_RE = re.compile(r'رمز الدخول المؤقت:\s*([A-Za-z0-9_-]+)')
# Password reset issues a *recovery* code, which is a separate channel from the
# initial login code, with its own flash label.
_RECOVERY_CODE_RE = re.compile(r'رمز الاسترجاع المؤقت:\s*([A-Za-z0-9_-]+)')


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


def _recovery_code_from_flash(flashes):
    for _, msg in flashes:
        m = _RECOVERY_CODE_RE.search(msg)
        if m:
            return m.group(1)
    raise AssertionError(f'رمز الاسترجاع المؤقت غير موجود في الرسائل: {flashes}')


# ── Credential fields are not handled by the edit form ──────────────────

def test_edit_ignores_credential_fields(app_fx, db_fx):
    """/teachers/edit/<id> no longer manages credentials at all.

    Username and password changes moved to the dedicated, audited and
    CSRF-protected routes (/teachers/reset-password/<id> and
    /teachers/register-username/<id>). The edit form must therefore ignore
    those fields rather than applying them: a teacher without a linked account
    must stay without one after posting a username and a password.
    """
    client = _office_client(app_fx)
    r = client.post('/teachers/edit/1', data={
        'name': 'أستاذ مستورد',
        'username': 'imported_t1',
        'password': 'SecurePass123!',
        'department_ids[]': '1',
        'position': '',
        '_csrf_token': 'test-token',
    })
    assert r.status_code == 302

    conn = sqlite3.connect(db_fx)
    conn.row_factory = sqlite3.Row
    teacher = conn.execute('SELECT user_id FROM teachers WHERE id = 1').fetchone()
    leaked = conn.execute(
        "SELECT COUNT(*) AS c FROM users WHERE username = 'imported_t1'"
    ).fetchone()['c']
    conn.close()
    assert teacher['user_id'] is None, 'edit must not create a login account'
    assert leaked == 0, 'edit must not create the posted username'


def test_edit_ignores_empty_credential_fields(app_fx, db_fx):
    """Even empty credential fields leave the account untouched."""
    client = _office_client(app_fx)
    r = client.post('/teachers/edit/1', data={
        'name': 'أستاذ مستورد',
        'username': '',
        'password': '',
        'department_ids[]': '1',
        'position': '',
        '_csrf_token': 'test-token',
    })
    assert r.status_code == 302

    conn = sqlite3.connect(db_fx)
    conn.row_factory = sqlite3.Row
    assert conn.execute('SELECT user_id FROM teachers WHERE id = 1').fetchone()['user_id'] is None
    conn.close()


# ── Creation sets an office-assigned username + password ────────────────

def test_create_with_office_password_forces_first_change(app_fx, db_fx):
    """The office assigns both a username and an initial password.

    That password is a temporary first credential: create_teacher() always sets
    force_password_change, so the member's first login lands on the mandatory
    change-password page and the office password stops working afterwards.
    """
    client = _office_client(app_fx)
    r1 = client.post('/teachers/create', data={
        'name': 'أستاذ مستورد',
        'username': 'imported_t1',
        'password': _PASSWORD,
        'department_ids[]': '1',
        'position': '',
        '_csrf_token': 'test-token',
    })
    assert r1.status_code == 302
    assert any('تم إضافة عضو هيئة التدريس' in m for _, m in _flash(client)), _flash(client)

    conn = sqlite3.connect(db_fx)
    conn.row_factory = sqlite3.Row
    user = conn.execute(
        'SELECT * FROM users WHERE username=?', ('imported_t1',)
    ).fetchone()
    conn.close()
    assert user['force_password_change'] == 1

    # First login with the office password is forced to change it.
    login = app_fx.test_client()
    with login.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r2 = login.post('/login', data={
        'username': 'imported_t1',
        'password': _PASSWORD,
        '_csrf_token': 'test-token',
    })
    assert r2.status_code == 302
    assert 'change-password' in r2.headers.get('Location', '')

    new_password = 'MemberChosen456!'
    r3 = login.post('/change-password', data={
        'current_password': _PASSWORD,
        'new_password': new_password,
        'confirm_password': new_password,
        '_csrf_token': 'test-token',
    })
    assert r3.status_code == 302

    conn = sqlite3.connect(db_fx)
    conn.row_factory = sqlite3.Row
    user = conn.execute(
        'SELECT * FROM users WHERE username=?', ('imported_t1',)
    ).fetchone()
    conn.close()
    assert user['force_password_change'] == 0

    # The member's own password now works without another forced change...
    fresh = app_fx.test_client()
    with fresh.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r4 = fresh.post('/login', data={
        'username': 'imported_t1',
        'password': new_password,
        '_csrf_token': 'test-token',
    })
    assert r4.status_code == 302
    assert 'change-password' not in r4.headers.get('Location', '')

    # ...and the office password is dead.
    fresh2 = app_fx.test_client()
    with fresh2.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r5 = fresh2.post('/login', data={
        'username': 'imported_t1',
        'password': _PASSWORD,
        '_csrf_token': 'test-token',
    })
    assert r5.status_code == 200
    assert 'اسم المستخدم أو كلمة المرور غير صحيحة' in r5.get_data(as_text=True)



def test_create_requires_an_initial_password(app_fx, db_fx):
    """A username alone is not enough any more: the office must issue a
    password that satisfies the shared policy."""
    client = _office_client(app_fx)
    r = client.post('/teachers/create', data={
        'name': 'أستاذ بلا كلمة مرور',
        'username': 'nopass_user',
        'department_ids[]': '1',
        'position': '',
        '_csrf_token': 'test-token',
    })
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'كلمة المرور' in body

    conn = sqlite3.connect(db_fx)
    conn.row_factory = sqlite3.Row
    assert conn.execute(
        "SELECT COUNT(*) AS c FROM users WHERE username = 'nopass_user'"
    ).fetchone()['c'] == 0
    conn.close()


def test_create_rejects_password_below_policy(app_fx, db_fx):
    """The create form applies the same 8-char complexity policy as the
    service, so a weak password is refused before anything is written."""
    client = _office_client(app_fx)
    r = client.post('/teachers/create', data={
        'name': 'أستاذ ضعيف',
        'username': 'weakpw_user',
        'password': 'abc',
        'department_ids[]': '1',
        'position': '',
        '_csrf_token': 'test-token',
    })
    assert r.status_code == 200
    assert 'كلمة المرور' in r.get_data(as_text=True)

    conn = sqlite3.connect(db_fx)
    conn.row_factory = sqlite3.Row
    assert conn.execute(
        "SELECT COUNT(*) AS c FROM users WHERE username = 'weakpw_user'"
    ).fetchone()['c'] == 0
    conn.close()


# ── Username validation errors on the create form ────────────────────────

def test_create_short_username_shows_arabic_error(app_fx, db_fx):
    client = _office_client(app_fx)
    r = client.post('/teachers/create', data={
        'name': 'أستاذ قصير',
        'username': 'x',
        'password': _PASSWORD,
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
        'password': _PASSWORD,
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
        'academic_number': 'AN-CODEX', 'username': 'codex_user',
        'qualification_id': None, 'rank_id': None,
        'classification_id': None, 'national_id': '', 'contract_date': '', 'tasks': '',
    }, department_ids=[1], additional_roles=None, initial_password=_INITIAL_PASSWORD)
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
        'department_id': 1,         'academic_number': 'AN-STUCK2', 'username': 'stuck_user',
        'qualification_id': None, 'rank_id': None, 'classification_id': None,
        'national_id': '', 'contract_date': '', 'tasks': '',
    }, department_ids=[1], additional_roles=None, initial_password=_INITIAL_PASSWORD)
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
    new_code = _recovery_code_from_flash(on_screen)

    conn = sqlite3.connect(db_fx)
    conn.row_factory = sqlite3.Row
    user = conn.execute(
        'SELECT * FROM users WHERE username=?', (creds['username'],)
    ).fetchone()
    conn.close()
    # The recovery code is stored hashed and is a separate channel: it does not
    # renew the (still expired) initial login code.
    assert user['recovery_code_hash']
    assert user['recovery_code_hash'] != new_code
    assert user['recovery_code_expires_at']
    assert user['recovery_code_attempts'] == 0
    assert user['force_password_change'] == 1
    assert user['initial_login_code_expires'] == '2000-01-01 00:00:00'

    # The office password alone still cannot get in: the account stays blocked
    # by the expired initial code, so only the recovery code releases it.
    login2 = app_fx.test_client()
    with login2.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r2 = login2.post('/login', data={
        'username': creds['username'], 'password': creds['password'],
        '_csrf_token': 'test-token',
    })
    assert r2.status_code == 200
    assert 'انتهت صلاحية رمز الدخول الأولي' in r2.get_data(as_text=True)

    # the recovery code logs in and forces the password change
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
        'academic_number': 'AN-EXPD', 'username': 'expd_user', 'qualification_id': None, 'rank_id': None,
        'classification_id': None, 'national_id': '', 'contract_date': '', 'tasks': '',
    }, department_ids=[1], additional_roles=None, initial_password=_INITIAL_PASSWORD)
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
        'academic_number': 'AN-WRONGPW', 'username': 'wrongpw_user', 'qualification_id': None, 'rank_id': None,
        'classification_id': None, 'national_id': '', 'contract_date': '', 'tasks': '',
    }, department_ids=[1], additional_roles=None, initial_password=_INITIAL_PASSWORD)
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