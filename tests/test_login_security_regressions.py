"""Regression tests for login injection, enumeration, and session handling."""

import sqlite3

from tests.harness import CSRF_TOKEN, ROLE_PASSWORD


def _post_api_login(client, username, password):
    return client.post('/api/auth/login', json={
        'username': username,
        'password': password,
        '_csrf_token': CSRF_TOKEN,
    })


def test_sql_injection_login_input_does_not_authenticate_or_create_user(
    app_fx, db_path, seeded
):
    conn = sqlite3.connect(db_path)
    before = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    conn.close()

    client = app_fx.test_client()
    with client.session_transaction() as session:
        session['_csrf_token'] = CSRF_TOKEN
    response = _post_api_login(client, "' OR 1=1 --", 'anything')

    assert response.status_code == 401
    assert response.get_json()['ok'] is False
    with client.session_transaction() as session:
        assert 'user_id' not in session

    conn = sqlite3.connect(db_path)
    after = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    conn.close()
    assert after == before


def test_html_login_uses_same_failure_message_for_unknown_and_wrong_password(
    app_fx, db_path, seeded
):
    responses = []
    for username, password in (
        ('teacher_user', 'incorrect-password'),
        ('unknown-user', 'incorrect-password'),
    ):
        client = app_fx.test_client()
        with client.session_transaction() as session:
            session['_csrf_token'] = CSRF_TOKEN
        response = client.post('/login', data={
            'username': username,
            'password': password,
            '_csrf_token': CSRF_TOKEN,
        })
        responses.append((response.status_code, response.get_data(as_text=True)))

    assert responses[0][0] == responses[1][0] == 200
    message = 'اسم المستخدم أو كلمة المرور غير صحيحة'
    assert message in responses[0][1]
    assert message in responses[1][1]


def test_html_login_with_wrong_username_and_valid_password_preserves_data(
    app_fx, db_path, seeded
):
    conn = sqlite3.connect(db_path)
    users_before = conn.execute(
        'SELECT id, username, password, role FROM users ORDER BY id'
    ).fetchall()
    teachers_before = conn.execute(
        'SELECT id, name, user_id FROM teachers ORDER BY id'
    ).fetchall()
    conn.close()

    client = app_fx.test_client()
    with client.session_transaction() as session:
        session['_csrf_token'] = CSRF_TOKEN
    response = client.post('/login', data={
        'username': 'unknown-user',
        'password': ROLE_PASSWORD,
        '_csrf_token': CSRF_TOKEN,
    })

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'اسم المستخدم أو كلمة المرور غير صحيحة' in body
    assert 'id="loginForm"' in body
    with client.session_transaction() as session:
        assert 'user_id' not in session

    conn = sqlite3.connect(db_path)
    users_after = conn.execute(
        'SELECT id, username, password, role FROM users ORDER BY id'
    ).fetchall()
    teachers_after = conn.execute(
        'SELECT id, name, user_id FROM teachers ORDER BY id'
    ).fetchall()
    conn.close()
    assert users_after == users_before
    assert teachers_after == teachers_before


def test_api_login_uses_same_failure_response_for_unknown_and_wrong_password(
    app_fx, db_path, seeded
):
    responses = []
    for username, password in (
        ('teacher_user', 'incorrect-password'),
        ('unknown-user', 'incorrect-password'),
    ):
        client = app_fx.test_client()
        with client.session_transaction() as session:
            session['_csrf_token'] = CSRF_TOKEN
        response = _post_api_login(client, username, password)
        responses.append((response.status_code, response.get_json()))

    assert responses[0] == responses[1]
    assert responses[0][0] == 401
    assert responses[0][1]['message'] == 'اسم المستخدم أو كلمة المرور غير صحيحة'


def test_successful_login_rebuilds_session_from_authenticated_user(
    app_fx, db_path, seeded
):
    client = app_fx.test_client()
    with client.session_transaction() as session:
        session['_csrf_token'] = CSRF_TOKEN
        session['user_id'] = seeded['users']['dean']
        session['username'] = 'forged-admin'
        session['role'] = 'dean'
        session['roles'] = ['dean']
        session['untrusted_marker'] = 'must-not-survive'

    response = _post_api_login(client, 'teacher_user', ROLE_PASSWORD)

    assert response.status_code == 200
    assert response.get_json()['ok'] is True
    with client.session_transaction() as session:
        assert session['username'] == 'teacher_user'
        assert session['role'] == 'teacher'
        assert session['roles'] == ['teacher']
        assert 'untrusted_marker' not in session
        assert session['_csrf_token'] == CSRF_TOKEN


def test_logout_invalidates_the_session_for_later_requests(
    app_fx, db_path, seeded
):
    client = app_fx.test_client()
    with client.session_transaction() as session:
        session['_csrf_token'] = CSRF_TOKEN

    login = _post_api_login(client, 'teacher_user', ROLE_PASSWORD)
    assert login.status_code == 200
    assert client.get('/api/auth/me').status_code == 200

    logout = client.post(
        '/api/auth/logout',
        headers={'X-CSRFToken': CSRF_TOKEN},
    )
    assert logout.status_code == 200
    assert logout.get_json()['ok'] is True
    assert client.get('/api/auth/me').status_code == 401
