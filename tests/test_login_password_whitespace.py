"""Login ignores surrounding password whitespace but preserves internal spaces."""

import sqlite3

import pytest
from werkzeug.security import generate_password_hash


def test_login_trims_surrounding_password_whitespace_only(
    app_fx, db_path, seeded
):
    conn = sqlite3.connect(db_path)
    conn.execute(
        'UPDATE users SET password = ? WHERE username = ?',
        (generate_password_hash('pass word'), 'teacher_user'),
    )
    conn.commit()
    conn.close()

    client = app_fx.test_client()
    with client.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'

    response = client.post('/login', data={
        'username': 'teacher_user',
        'password': '  pass word  ',
        '_csrf_token': 'test-token',
    })
    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get('username') == 'teacher_user'

    incorrect_client = app_fx.test_client()
    with incorrect_client.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    response = incorrect_client.post('/login', data={
        'username': 'teacher_user',
        'password': '  password  ',
        '_csrf_token': 'test-token',
    })
    assert response.status_code == 200
    assert 'اسم المستخدم أو كلمة المرور غير صحيحة' in response.get_data(as_text=True)

    api_client = app_fx.test_client()
    with api_client.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    response = api_client.post('/api/auth/login', json={
        'username': 'teacher_user',
        'password': '  pass word  ',
        '_csrf_token': 'test-token',
    })
    assert response.status_code == 200
    assert response.get_json()['ok'] is True
    assert response.get_json()['data']['user']['username'] == 'teacher_user'


@pytest.mark.parametrize('field,value', [
    ('username', None),
    ('username', 123),
    ('password', None),
    ('password', ['not', 'a', 'string']),
])
def test_api_login_rejects_non_string_credentials(app_fx, field, value):
    client = app_fx.test_client()
    with client.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    response = client.post('/api/auth/login', json={
        'username': 'teacher_user',
        'password': 'irrelevant',
        field: value,
        '_csrf_token': 'test-token',
    })
    assert response.status_code == 422
    assert response.get_json()['ok'] is False
