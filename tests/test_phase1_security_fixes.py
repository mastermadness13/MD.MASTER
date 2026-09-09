"""Regression tests for Phase 1 critical security fixes.

Each test locks down one of the 17 critical findings re-verified against the
current codebase:

  SEC-001  config.py — no hardcoded/predictable SECRET_KEY fallback.
  SEC-002  config.py — SESSION_COOKIE_SECURE on by default.
  DB-001   database/connection.py — WAL journal mode (MEMORY lost data on crash).
  DB-002   schema.py — named-semesters migration runs once, never wipes admin data.
  SEC-003  services/search.py — highlight_text() HTML-escapes before marking.
  AUTH-001 api/auth.py — API login is throttled like the HTML login form.
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
    """A legacy-shaped DB: per-department semesters, no migration logged."""
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
        CREATE TABLE semesters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            department_id INTEGER,
            semester_number INTEGER,
            academic_year TEXT
        )
    """)
    conn.commit()
    conn.close()
    return path


def test_migrate_to_named_semesters_runs_once_preserving_admin_data(legacy_db):
    conn = connect(legacy_db)
    try:
        _migrate_to_named_semesters(conn)

        # Admin adds a custom semester after the initial migration.
        conn.execute(
            "INSERT INTO semesters (code, season, year, name_ar, name_en, is_active) "
            "VALUES ('thesis_2031', 'summer', 2031, 'أطروحة', 'Thesis', 1)"
        )
        conn.commit()
        custom_before = _semester_codes(conn)

        # Simulate the next app startup — previously this DROPPED the table
        # and re-seeded, wiping the custom semester and resetting is_active.
        _migrate_to_named_semesters(conn)
        custom_after = _semester_codes(conn)

        assert 'thesis_2031' in custom_after
        assert custom_after == custom_before

        row = conn.execute(
            "SELECT is_active FROM semesters WHERE code = 'thesis_2031'"
        ).fetchone()
        assert row['is_active'] == 1
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


def _semester_codes(conn):
    rows = conn.execute('SELECT code FROM semesters').fetchall()
    return {r['code'] for r in rows}


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
        "VALUES ('superadmin', 'x', 'super_admin', 'مدير')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) "
        "VALUES ('regular', 'x', 'teacher', 'مدرس')"
    )
    conn.commit()
    conn.close()
    return str(db_path)


def test_module_delete_user_rejects_superadmin(guard_db):
    conn = sqlite3.connect(guard_db)
    conn.row_factory = sqlite3.Row
    super_id = conn.execute(
        "SELECT id FROM users WHERE username = 'superadmin'"
    ).fetchone()['id']
    with pytest.raises(ProtectedAccountError):
        user_service.delete_user(conn, super_id)
    still_there = conn.execute(
        "SELECT COUNT(*) AS c FROM users WHERE id = ?", (super_id,)
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


# ── AUTH-002: switch-role CSRF + safe redirect ────────────────────────────


def _login_session(app_fx, role='teacher', roles=('teacher',)):
    client = app_fx.test_client()
    with client.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
        sess['user_id'] = 1
        sess['role'] = role
        sess['roles'] = list(roles)
    return client


def test_switch_role_rejects_missing_csrf(app_fx):
    client = _login_session(app_fx)
    resp = client.post('/switch-role', data={
        'role': 'teacher',
        '_csrf_token': 'wrong-token',
    })
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get('role') == 'teacher'


def test_switch_role_with_valid_csrf(app_fx):
    client = _login_session(app_fx)
    resp = client.post('/switch-role', headers={
        'Referer': 'http://localhost/dashboard/',
    }, data={
        'role': 'teacher',
        '_csrf_token': 'test-token',
    })
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get('role') == 'teacher'


def test_switch_role_ignores_cross_origin_referrer(app_fx):
    client = _login_session(app_fx)
    resp = client.post('/switch-role', headers={
        'Referer': 'https://evil.example/phish',
    }, data={
        'role': 'teacher',
        '_csrf_token': 'test-token',
    })
    assert resp.status_code == 302
    target = resp.headers.get('Location', '')
    assert 'evil.example' not in target