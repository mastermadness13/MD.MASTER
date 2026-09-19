"""Functional tests for the change-password flow (form + SPA/JSON)."""

import json
import pathlib
import sqlite3

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

import flask_db
from database.connection import connect
from database.schema import ensure_schema

OLD_PW = 'OldPass!123'
NEW_PW = 'NewPass!456'
WEAK_PW = 'short1'


def _mkdb(dirname):
    p = pathlib.Path(dirname)
    p.mkdir(parents=True, exist_ok=True)
    db_path = p / 'func.db'
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.execute(
        "INSERT OR IGNORE INTO users (username,password,role,label) VALUES (?,?,?,?)",
        ('superadmin', generate_password_hash(OLD_PW), 'super_admin', 'مدير'),
    )
    conn.execute(
        "UPDATE users SET password=?, role='super_admin', label='مدير' WHERE username='superadmin'",
        (generate_password_hash(OLD_PW),),
    )
    conn.commit()
    conn.close()
    return str(db_path)


def _password(path, user_id=1):
    conn = sqlite3.connect(path)
    row = conn.execute('SELECT password FROM users WHERE id=?', (user_id,)).fetchone()
    conn.close()
    return row[0] if row else None


@pytest.fixture
def setup(tmp_path, monkeypatch, app_fx):
    db_path = _mkdb(tmp_path / 'a')
    monkeypatch.setattr(flask_db, 'DATABASE', db_path)
    c = app_fx.test_client()
    with c.session_transaction() as s:
        s['user_id'] = 1
        s['role'] = 'super_admin'
        s['username'] = 'superadmin'
        s['department_id'] = None
        s['_csrf_token'] = 't'
    return c, db_path


def _post_form(c, data):
    data['_csrf_token'] = 't'
    return c.post('/change-password', data=data, follow_redirects=True)


def test_get_renders_page(setup):
    c, _ = setup
    r = c.get('/change-password')
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'auth-layout' in body
    assert 'id="current_password"' in body
    assert 'id="new_password"' in body
    assert 'id="confirm_password"' in body
    assert 'auth_passwords.js' in body


def test_form_success_changes_password(setup):
    c, db_path = setup
    r = _post_form(c, {
        'current_password': OLD_PW,
        'new_password': NEW_PW,
        'confirm_password': NEW_PW,
    })
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'تم التغيير بنجاح' in body
    assert check_password_hash(_password(db_path), NEW_PW)
    assert not check_password_hash(_password(db_path), OLD_PW)


def test_form_wrong_current(setup):
    c, _ = setup
    r = _post_form(c, {
        'current_password': 'WrongPass!1',
        'new_password': NEW_PW,
        'confirm_password': NEW_PW,
    })
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'كلمة المرور الحالية غير صحيحة' in body


def test_form_confirm_mismatch(setup):
    c, _ = setup
    r = _post_form(c, {
        'current_password': OLD_PW,
        'new_password': NEW_PW,
        'confirm_password': NEW_PW + 'X',
    })
    body = r.get_data(as_text=True)
    assert 'كلمة المرور الجديدة وتأكيدها غير متطابقين' in body


def test_form_weak_password(setup):
    c, _ = setup
    r = _post_form(c, {
        'current_password': OLD_PW,
        'new_password': WEAK_PW,
        'confirm_password': WEAK_PW,
    })
    body = r.get_data(as_text=True)
    assert 'كلمة المرور يجب أن تكون 8 أحرف على الأقل' in body


def test_form_same_as_current(setup):
    c, _ = setup
    r = _post_form(c, {
        'current_password': OLD_PW,
        'new_password': OLD_PW,
        'confirm_password': OLD_PW,
    })
    body = r.get_data(as_text=True)
    assert 'يجب أن تختلف' in body


def _post_json(c, payload):
    return c.post(
        '/change-password',
        data=json.dumps(payload),
        content_type='application/json',
        headers={'X-CSRFToken': 't', 'X-Requested-With': 'XMLHttpRequest'},
    )


def test_json_success_changes_password(setup):
    c, db_path = setup
    r = _post_json(c, {
        'current_password': OLD_PW,
        'new_password': NEW_PW,
        'confirm_password': NEW_PW,
    })
    data = r.get_json()
    assert r.status_code == 200
    assert data['ok'] is True
    assert check_password_hash(_password(db_path), NEW_PW)


def test_json_wrong_current(setup):
    c, _ = setup
    r = _post_json(c, {
        'current_password': 'WrongPass!1',
        'new_password': NEW_PW,
        'confirm_password': NEW_PW,
    })
    data = r.get_json()
    assert r.status_code == 400
    assert data['ok'] is False
    assert 'كلمة المرور الحالية غير صحيحة' in data['message']