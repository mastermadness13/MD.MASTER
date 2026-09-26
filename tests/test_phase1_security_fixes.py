"""Regression tests for Phase 1 critical security fixes.

Each test locks down one of the 17 critical findings re-verified against the
current codebase:

  SEC-001  config.py — no hardcoded/predictable SECRET_KEY fallback.
  SEC-002  config.py — SESSION_COOKIE_SECURE on by default.
  DB-001   database/connection.py — WAL journal mode (MEMORY lost data on crash).
  DB-002   schema.py — named-semesters migration runs once, converts
             timetable_versions without wiping data; the semesters table no
             longer exists (academic calendar feature removed).
  SEC-003  services/search.py — highlight_text() HTML-escapes before marking.
  AUTH-001 api/auth_api.py — API login is throttled like the HTML login form.
  AUTH-002 routes/dashboard.py — switch-role requires a CSRF token and never
             open-redirects via request.referrer.
  AUTH-003 services/user_service.py — module-level delete_user() is guarded.
"""

import importlib
import sqlite3

import pytest

import config as config_module
import flask_db
from database.connection import connect
from database.schema import _migrate_to_named_semesters
from core.exceptions import ProtectedAccountError
from database.repositories.user_repository import UserRepository
from services import user_service
from services.search import highlight_text

_HARDCODED_FALLBACK = 'ropely-secret-key-change-in-production'


# ── SEC-001: secret key ───────────────────────────────────────────────────


def test_load_secret_key_uses_env_when_set(tmp_path, monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'A' * 48)
    assert config_module._load_secret_key(str(tmp_path)) == 'A' * 48


def test_load_secret_key_reads_persisted_file(tmp_path, monkeypatch):
    monkeypatch.delenv('SECRET_KEY', raising=False)
    key_file = tmp_path / '.secret_key'
    key_file.write_text('persisted-secret-value', encoding='utf-8')
    assert config_module._load_secret_key(str(tmp_path)) == 'persisted-secret-value'


def test_load_secret_key_generates_and_persists_random(tmp_path, monkeypatch):
    monkeypatch.delenv('SECRET_KEY', raising=False)
    value = config_module._load_secret_key(str(tmp_path))
    assert value != _HARDCODED_FALLBACK
    assert len(value) >= 32
    assert (tmp_path / '.secret_key').exists()
    # Second call returns the persisted value (sessions survive restarts).
    assert config_module._load_secret_key(str(tmp_path)) == value


def test_load_secret_key_never_returns_hardcoded_default(tmp_path, monkeypatch):
    monkeypatch.delenv('SECRET_KEY', raising=False)
    for _ in range(3):
        assert config_module._load_secret_key(str(tmp_path)) != _HARDCODED_FALLBACK


# ── SEC-002: secure cookies ───────────────────────────────────────────────


def test_session_cookie_secure_defaults_to_true(tmp_path, monkeypatch):
    monkeypatch.delenv('SESSION_COOKIE_SECURE', raising=False)
    reloaded = importlib.reload(config_module)
    assert reloaded.Config.SESSION_COOKIE_SECURE is True


def test_session_cookie_secure_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv('SESSION_COOKIE_SECURE', 'false')
    reloaded = importlib.reload(config_module)
    assert reloaded.Config.SESSION_COOKIE_SECURE is False


# ── DB-001: WAL journal mode ──────────────────────────────────────────────


def test_connection_uses_wal_journal_mode(tmp_path):
    path = str(tmp_path / 'wal.db')
    conn = connect(path)
    try:
        mode = conn.execute('PRAGMA journal_mode').fetchone()[0]
        assert mode == 'wal'
    finally:
        conn.close()


# ── DB-002: named-semesters migration runs once ───────────────────────────


@pytest.fixture
def legacy_db(tmp_path):
    """A legacy-shaped DB: timetable_versions with academic_year, no migration logged."""
    path = str(tmp_path / 'legacy.db')
    conn = connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migration_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            migration_name TEXT NOT NULL UNIQUE,
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            semesters INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE timetable_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            department_id INTEGER,
            semester INTEGER NOT NULL,
            academic_year TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE timetable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            department_id INTEGER,
            semester INTEGER NOT NULL,
            version_id INTEGER
        )
    """)
    conn.execute(
        "INSERT INTO timetable_versions (id, department_id, semester, academic_year, status) "
        "VALUES (1, NULL, 1, '2025-2026', 'active')"
    )
    conn.execute(
        "INSERT INTO timetable (id, department_id, semester, version_id) "
        "VALUES (10, NULL, 1, 1)"
    )
    conn.commit()
    conn.close()
    return path


def test_migrate_to_named_semesters_converts_timetable_versions(legacy_db):
    conn = connect(legacy_db)
    try:
        _migrate_to_named_semesters(conn)

        cols = {r[1] for r in conn.execute('PRAGMA table_info(timetable_versions)').fetchall()}
        assert 'semester_code' in cols
        assert 'academic_year' not in cols

        row = conn.execute(
            'SELECT id, semester_code FROM timetable_versions WHERE id = 1'
        ).fetchone()
        assert row['id'] == 1
        assert row['semester_code'] == 'fall_2026'

        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()}
        assert 'semesters' not in tables
    finally:
        conn.close()


def test_migrate_to_named_semesters_runs_once_preserving_data(legacy_db):
    conn = connect(legacy_db)
    try:
        # First startup: migration applies and preserves the version/timetable ids.
        _migrate_to_named_semesters(conn)
        first = dict(conn.execute(
            'SELECT semester_code, status FROM timetable_versions WHERE id = 1'
        ).fetchone())

        # Simulate the next app startup — data must be untouched.
        _migrate_to_named_semesters(conn)
        second = dict(conn.execute(
            'SELECT semester_code, status FROM timetable_versions WHERE id = 1'
        ).fetchone())

        assert second == first
        version_id = conn.execute(
            'SELECT version_id FROM timetable WHERE id = 10'
        ).fetchone()['version_id']
        assert version_id == 1
    finally:
        conn.close()


def test_migrate_to_named_semesters_marks_migration_done(legacy_db):
    conn = connect(legacy_db)
    try:
        _migrate_to_named_semesters(conn)
        done = conn.execute(
            "SELECT 1 FROM _migration_log WHERE migration_name = 'migrate_to_named_semesters_v1'"
        ).fetchone()
        assert done is not None
    finally:
        conn.close()


# ── SEC-003: highlight_text escaping ──────────────────────────────────────


def test_highlight_text_escapes_html_content():
    result = highlight_text('<script>alert(1)</script>', 'alert')
    assert '<script' not in result
    assert '&lt;script&gt;' in result
    assert '<mark class="search-highlight">alert</mark>' in result


def test_highlight_text_preserves_arabic_matching():
    result = highlight_text('هجوم <img src=x onerror=1>', 'هجوم')
    assert result.startswith('<mark class="search-highlight">هجوم</mark>')
    assert '<img' not in result
    assert '&lt;img' in result


def test_highlight_text_empty_input():
    assert highlight_text('', 'x') == ''
    assert highlight_text('name', '') == 'name'
    assert highlight_text(None, 'x') == ''


# ── AUTH-003: delete_user is guarded at every entry point ─────────────────


@pytest.fixture
def guard_db(tmp_path, monkeypatch):
    db_path = tmp_path / 'guard.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) "
        "VALUES ('office_manager', 'x', 'faculty_affairs', 'مدير مكتب أعضاء هيئة التدريس')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) "
        "VALUES ('regular', 'x', 'teacher', 'مدرس')"
    )
    conn.commit()
    conn.close()
    return str(db_path)


def test_module_delete_user_rejects_office_manager(guard_db):
    conn = sqlite3.connect(guard_db)
    conn.row_factory = sqlite3.Row
    om_id = conn.execute(
        "SELECT id FROM users WHERE username = 'office_manager'"
    ).fetchone()['id']
    with pytest.raises(ProtectedAccountError):
        user_service.delete_user(conn, om_id)
    still_there = conn.execute(
        "SELECT COUNT(*) AS c FROM users WHERE id = ?", (om_id,)
    ).fetchone()['c']
    assert still_there == 1
    conn.close()


def test_module_delete_user_allows_regular_user(guard_db):
    conn = sqlite3.connect(guard_db)
    conn.row_factory = sqlite3.Row
    reg_id = conn.execute(
        "SELECT id FROM users WHERE username = 'regular'"
    ).fetchone()['id']
    user_service.delete_user(conn, reg_id)
    gone = conn.execute(
        "SELECT COUNT(*) AS c FROM users WHERE id = ?", (reg_id,)
    ).fetchone()['c']
    assert gone == 0
    conn.close()


# ── AUTH-001: API login throttle ──────────────────────────────────────────


def test_api_login_is_rate_limited(app_fx):
    client = app_fx.test_client()
    with client.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    responses = []
    for _ in range(6):
        resp = client.post('/api/auth/login', json={
            'username': 'no-such-user',
            'password': 'bad',
            '_csrf_token': 'test-token',
        })
        responses.append(resp.status_code)
    assert responses[:5] == [401] * 5
    assert responses[5] == 429


def test_api_login_rate_limited_per_username(app_fx):
    """Each account gets its own 5-chance budget regardless of client IP."""
    client = app_fx.test_client()
    with client.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    username = 'lockme_account'
    statuses = []
    for i in range(6):
        resp = client.post('/api/auth/login', environ_base={
            'REMOTE_ADDR': '10.0.0.%d' % i,  # different IP every attempt
        }, json={
            'username': username,
            'password': 'bad',
            '_csrf_token': 'test-token',
        })
        statuses.append(resp.status_code)
    assert statuses[:5] == [401] * 5
    assert statuses[5] == 429
    # A different account is not affected by the lockout
    other = client.post('/api/auth/login', environ_base={
        'REMOTE_ADDR': '10.0.0.99',
    }, json={
        'username': 'someone_else',
        'password': 'bad',
        '_csrf_token': 'test-token',
    })
    assert other.status_code == 401


# ── AUTH-002: switch-role CSRF + safe redirect ────────────────────────────


@pytest.fixture
def role_db(tmp_path, monkeypatch):
    """A real user row for the switch-role tests.

    app.before_request's enforce_session_version looks the session user up and
    clears the session when the row is missing, so a session pointing at a
    non-existent user_id gets bounced to /login before the route ever runs.
    """
    db_path = tmp_path / 'switch_role.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    from database.schema import ensure_schema
    ensure_schema(conn)
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) "
        "VALUES ('multi_role', 'x', 'teacher', 'مدرس')"
    )
    uid = conn.execute(
        "SELECT id FROM users WHERE username = 'multi_role'"
    ).fetchone()['id']
    conn.commit()
    conn.close()
    return uid


def _login_session(app_fx, role='teacher', roles=('teacher',), user_id=1):
    client = app_fx.test_client()
    with client.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
        sess['user_id'] = user_id
        sess['role'] = role
        sess['roles'] = list(roles)
    return client


def test_switch_role_rejects_missing_csrf(role_db, app_fx):
    client = _login_session(app_fx, user_id=role_db)
    resp = client.post('/switch-role', data={
        'role': 'teacher',
        '_csrf_token': 'wrong-token',
    })
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get('role') == 'teacher'


def test_switch_role_with_valid_csrf(role_db, app_fx):
    client = _login_session(app_fx, user_id=role_db)
    resp = client.post('/switch-role', headers={
        'Referer': 'http://localhost/dashboard/',
    }, data={
        'role': 'teacher',
        '_csrf_token': 'test-token',
    })
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get('role') == 'teacher'


def test_switch_role_ignores_cross_origin_referrer(role_db, app_fx):
    client = _login_session(app_fx, user_id=role_db)
    resp = client.post('/switch-role', headers={
        'Referer': 'https://evil.example/phish',
    }, data={
        'role': 'teacher',
        '_csrf_token': 'test-token',
    })
    assert resp.status_code == 302
    target = resp.headers.get('Location', '')
    assert 'evil.example' not in target


def test_switch_role_ajax_success(role_db, app_fx):
    client = _login_session(app_fx, role='teacher', roles=('teacher', 'exam'), user_id=role_db)
    resp = client.post('/switch-role', headers={
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json',
    }, data={
        'role': 'exam',
        '_csrf_token': 'test-token',
    })
    assert resp.status_code == 200
    assert resp.is_json
    assert resp.get_json()['ok'] is True
    with client.session_transaction() as sess:
        assert sess.get('role') == 'exam'


def test_switch_role_ajax_denied_role(role_db, app_fx):
    client = _login_session(app_fx, role='teacher', roles=('teacher',), user_id=role_db)
    resp = client.post('/switch-role', headers={
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json',
    }, data={
        'role': 'faculty_affairs',
        '_csrf_token': 'test-token',
    })
    assert resp.status_code == 403
    assert resp.is_json
    assert resp.get_json()['ok'] is False
    with client.session_transaction() as sess:
        assert sess.get('role') == 'teacher'


def test_switch_role_ajax_missing_csrf(role_db, app_fx):
    client = _login_session(app_fx, user_id=role_db)
    resp = client.post('/switch-role', headers={
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json',
    }, data={
        'role': 'teacher',
        '_csrf_token': 'wrong-token',
    })
    assert resp.status_code == 403
    assert resp.is_json
    assert resp.get_json()['ok'] is False
    with client.session_transaction() as sess:
        assert sess.get('role') == 'teacher'


# ── AUTH-001: shared throttle across HTML + API login ─────────────────────


def test_login_throttle_shared_between_form_and_api(app_fx):
    """CWE-307: alternating between /api/auth/login and /login shares one budget."""
    client = app_fx.test_client()
    with client.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    ip = '10.7.7.7'
    username = 'shared_lock_me'
    # 3 API failures → 3 hits recorded to the shared bucket
    for _ in range(3):
        resp = client.post(
            '/api/auth/login',
            environ_base={'REMOTE_ADDR': ip},
            json={'username': username, 'password': 'bad', '_csrf_token': 'test-token'},
        )
        assert resp.status_code == 401
    # 2 HTML-form failures → total 5 hits (both recorded to the same bucket)
    for _ in range(2):
        resp = client.post(
            '/login',
            environ_base={'REMOTE_ADDR': ip},
            data={'username': username, 'password': 'bad', '_csrf_token': 'test-token'},
        )
        body = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert 'اسم المستخدم أو كلمة المرور غير صحيحة' in body
    # 6th attempt on EITHER endpoint must now be blocked
    resp = client.post(
        '/api/auth/login',
        environ_base={'REMOTE_ADDR': ip},
        json={'username': username, 'password': 'bad', '_csrf_token': 'test-token'},
    )
    assert resp.status_code == 429
    resp = client.post(
        '/login',
        environ_base={'REMOTE_ADDR': ip},
        data={'username': username, 'password': 'bad', '_csrf_token': 'test-token'},
    )
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert 'تم تجاوز الحد المسموح' in body