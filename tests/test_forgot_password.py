"""Functional tests for the forgot-password / reset-password flow."""

import pathlib
import sqlite3

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

import flask_db
from database.connection import connect
from database.schema import ensure_schema
from services import user_service

OLD_PW = 'OldPass!123'
NEW_PW = 'NewPass!456'
USERNAME = 'testteacher'
EMAIL = 'testteacher@zuwaratc.edu.ly'


def _mkdb(dirname):
    p = pathlib.Path(dirname)
    p.mkdir(parents=True, exist_ok=True)
    db_path = p / 'forgot.db'
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.execute(
        "INSERT OR IGNORE INTO users (username,password,role,label,email) VALUES (?,?,?,?,?)",
        (USERNAME, generate_password_hash(OLD_PW), 'teacher', 'عضو هيئة تدريس', EMAIL),
    )
    conn.commit()
    conn.close()
    return str(db_path)


@pytest.fixture
def setup(tmp_path, monkeypatch, app_fx):
    db_path = _mkdb(tmp_path / 'a')
    monkeypatch.setattr(flask_db, 'DATABASE', db_path)
    c = app_fx.test_client()
    with c.session_transaction() as s:
        s['_csrf_token'] = 't'
    return c, db_path


def _post(c, url, data, **kw):
    data['_csrf_token'] = 't'
    return c.post(url, data=data, **kw)


def _token_count(db_path):
    conn = sqlite3.connect(db_path)
    row = conn.execute('SELECT COUNT(*) FROM password_resets').fetchone()
    conn.close()
    return row[0]


def _active_token(db_path):
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        'SELECT token FROM password_resets WHERE used = 0 ORDER BY id DESC LIMIT 1'
    ).fetchone()
    conn.close()
    return row[0] if row else None


def _password(db_path):
    conn = sqlite3.connect(db_path)
    row = conn.execute('SELECT password FROM users WHERE username=?', (USERNAME,)).fetchone()
    conn.close()
    return row[0] if row else None


def _noop_email(*args, **kwargs):
    return False


def _create_token(db_path, username=USERNAME):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return user_service.create_password_reset(conn, username)
    finally:
        conn.close()


def test_forgot_password_get_renders(setup):
    c, _ = setup
    r = c.get('/forgot-password')
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'id="recoveryForm"' in body
    assert 'إرسال رابط الاستعادة' in body
    assert 'العودة لصفحة تسجيل الدخول' in body


def test_forgot_password_unknown_user_generic_message(setup):
    c, db_path = setup
    r = _post(c, '/forgot-password', {'username': 'ghost-user'}, follow_redirects=True)
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'إذا كان الحساب موجوداً' in body
    assert _token_count(db_path) == 0


def test_forgot_password_creates_token_and_shows_link(setup, monkeypatch):
    monkeypatch.setattr('services.email_service.send_reset_email', _noop_email)
    monkeypatch.setenv('RESET_LINK_FALLBACK', '1')
    c, db_path = setup
    r = _post(c, '/forgot-password', {'username': USERNAME})
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    token = _active_token(db_path)
    assert token
    assert token in body
    assert '/reset-password/' in body


def test_forgot_password_hides_reset_link_by_default(setup, monkeypatch):
    """CWE-200: without the dev flag the reset URL is never disclosed."""
    monkeypatch.setattr('services.email_service.send_reset_email', _noop_email)
    c, db_path = setup
    r = _post(c, '/forgot-password', {'username': USERNAME}, follow_redirects=True)
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    token = _active_token(db_path)
    assert token
    assert '/reset-password/' not in body
    assert token not in body
    assert 'إذا كان الحساب موجوداً' in body


def test_forgot_password_identical_response_for_known_and_unknown(setup, monkeypatch):
    """CWE-204: found and missing accounts produce the same redirect."""
    monkeypatch.setattr('services.email_service.send_reset_email', _noop_email)
    c, _ = setup
    known = _post(c, '/forgot-password', {'username': USERNAME}, follow_redirects=False)
    unknown = _post(c, '/forgot-password', {'username': 'ghost-user'}, follow_redirects=False)
    assert known.status_code == 302
    assert unknown.status_code == 302
    assert known.headers.get('Location') == unknown.headers.get('Location')


def test_forgot_password_rate_limited(setup):
    """CWE-307: forgot-password requests are throttled per IP + username."""
    c, _ = setup
    ip = '10.9.9.9'
    for _ in range(5):
        r = c.post(
            '/forgot-password',
            data={'username': 'rate-me', '_csrf_token': 't'},
            environ_base={'REMOTE_ADDR': ip},
        )
        assert r.status_code == 302
    r = c.post(
        '/forgot-password',
        data={'username': 'rate-me', '_csrf_token': 't'},
        environ_base={'REMOTE_ADDR': ip},
    )
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'تم تجاوز الحد الأقصى لمحاولات الاستعادة' in body


def test_reset_password_get_renders_valid_token(setup):
    _, db_path = setup
    token, _ = _create_token(db_path)
    c, _ = setup
    r = c.get('/reset-password/%s' % token)
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'id="password"' in body
    assert 'id="confirm-password"' in body


def test_reset_password_invalid_token_redirects(setup):
    c, _ = setup
    r = c.get('/reset-password/not-a-real-token', follow_redirects=False)
    assert r.status_code == 302
    location = r.headers.get('Location', '')
    assert '/login' in location


def test_reset_password_success_updates_password(setup):
    _, db_path = setup
    token, _ = _create_token(db_path)
    c, _ = setup
    r = _post(c, '/reset-password/%s' % token, {
        'password': NEW_PW,
        'confirm-password': NEW_PW,
    })
    assert r.status_code == 302
    assert check_password_hash(_password(db_path), NEW_PW)
    assert not check_password_hash(_password(db_path), OLD_PW)


def test_reset_password_mismatch(setup):
    _, db_path = setup
    token, _ = _create_token(db_path)
    c, _ = setup
    r = _post(c, '/reset-password/%s' % token, {
        'password': NEW_PW,
        'confirm-password': NEW_PW + 'X',
    })
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'كلمة المرور غير متطابقة' in body
    assert check_password_hash(_password(db_path), OLD_PW)


def test_reset_password_weak_password(setup):
    _, db_path = setup
    token, _ = _create_token(db_path)
    c, _ = setup
    r = _post(c, '/reset-password/%s' % token, {
        'password': 'short1',
        'confirm-password': 'short1',
    })
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'كلمة المرور يجب أن تكون 8 أحرف على الأقل' in body
    assert check_password_hash(_password(db_path), OLD_PW)


def test_reset_password_rejects_current_password(setup):
    """CWE-620: reusing the same password is rejected."""
    _, db_path = setup
    token, _ = _create_token(db_path)
    c, _ = setup
    r = _post(c, '/reset-password/%s' % token, {
        'password': OLD_PW,
        'confirm-password': OLD_PW,
    })
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'يجب أن تختلف' in body
    assert check_password_hash(_password(db_path), OLD_PW)


def test_reset_password_rate_limited(setup):
    """CWE-307: reset-password POSTs are throttled per IP + token."""
    _, db_path = setup
    token, _ = _create_token(db_path)
    c, _ = setup
    ip = '10.8.8.8'
    for _ in range(5):
        r = c.post(
            '/reset-password/%s' % token,
            data={'password': NEW_PW, 'confirm-password': NEW_PW + 'X', '_csrf_token': 't'},
            environ_base={'REMOTE_ADDR': ip},
        )
        assert r.status_code == 200
    # 6th attempt blocked even with valid matching passwords
    r = c.post(
        '/reset-password/%s' % token,
        data={'password': NEW_PW, 'confirm-password': NEW_PW, '_csrf_token': 't'},
        environ_base={'REMOTE_ADDR': ip},
    )
    assert r.status_code == 302
    assert '/login' in r.headers.get('Location', '')
    assert not check_password_hash(_password(db_path), NEW_PW)
