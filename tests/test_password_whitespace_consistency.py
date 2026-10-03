"""Password storage must stay consistent with the login surfaces.

Both login handlers trim the submitted password before hashing it, so any
password accepted by a change/reset/profile/admin form must also survive that
trim. Otherwise the application stores a credential its own login forms can
never reproduce, locking the account out (CWE-620 / CWE-521).

Regression coverage for the confirmed self-lockout: ``/change-password``
accepted a password with a trailing space, stored it verbatim, and then both
``/login`` and ``/api/auth/login`` rejected it forever.
"""

import sqlite3

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from security import validate_password

OLD_PW = 'OldPass123'
PADDED = 'NewPass123 '


def _hash(db_path, username='teacher_user'):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute('SELECT password FROM users WHERE username = ?',
                            (username,)).fetchone()[0]
    finally:
        conn.close()


def _set(db_path, value, username='teacher_user'):
    conn = sqlite3.connect(db_path)
    conn.execute('UPDATE users SET password = ? WHERE username = ?',
                 (generate_password_hash(value), username))
    conn.commit()
    conn.close()


@pytest.mark.parametrize('value', [
    'NewPass123 ', ' NewPass123', ' NewPass123 ', '\tNewPass123\n',
])
def test_validate_password_rejects_surrounding_whitespace(value):
    error = validate_password(value)
    assert error is not None, 'a padded password must never be accepted'
    assert 'مسافات' in error


def test_validate_password_still_accepts_internal_whitespace():
    assert validate_password('New Pass 123') is None


def test_change_password_round_trips_through_the_login_form(app_fx, db_path, seeded):
    """A password set via /change-password must be usable afterwards."""
    _set(db_path, OLD_PW)
    c = app_fx.test_client()
    with c.session_transaction() as s:
        s['_csrf_token'] = 'tok'
    assert c.post('/login', data={'username': 'teacher_user', 'password': OLD_PW,
                                  '_csrf_token': 'tok'}).status_code == 302

    with c.session_transaction() as s:
        s['_csrf_token'] = 'tok'
    r = c.post('/change-password', data={
        'current_password': OLD_PW, 'new_password': PADDED,
        'confirm_password': PADDED, '_csrf_token': 'tok'})
    assert r.status_code == 200
    assert check_password_hash(_hash(db_path), 'NewPass123'), \
        'the padded value must be normalised to the trimmed password'

    # both login surfaces must accept what was just stored
    c2 = app_fx.test_client()
    with c2.session_transaction() as s:
        s['_csrf_token'] = 'tok'
    assert c2.post('/login', data={'username': 'teacher_user',
                                   'password': 'NewPass123',
                                   '_csrf_token': 'tok'}).status_code == 302

    c3 = app_fx.test_client()
    with c3.session_transaction() as s:
        s['_csrf_token'] = 'tok'
    api = c3.post('/api/auth/login', json={'username': 'teacher_user',
                                           'password': 'NewPass123',
                                           '_csrf_token': 'tok'})
    assert api.status_code == 200
    assert api.get_json()['data']['user']['username'] == 'teacher_user'


def test_padded_input_is_normalised_not_stored_verbatim(app_fx, db_path, seeded):
    """If a padded value reaches the handler it is trimmed before hashing."""
    _set(db_path, OLD_PW)
    c = app_fx.test_client()
    with c.session_transaction() as s:
        s['_csrf_token'] = 'tok'
    assert c.post('/login', data={'username': 'teacher_user', 'password': OLD_PW,
                                  '_csrf_token': 'tok'}).status_code == 302
    with c.session_transaction() as s:
        s['_csrf_token'] = 'tok'
    c.post('/change-password', data={
        'current_password': ' OldPass123 ',
        'new_password': '  Trimmed123  ',
        'confirm_password': 'Trimmed123', '_csrf_token': 'tok'})
    # stored value must be the trimmed one, matching what login will hash
    assert check_password_hash(_hash(db_path), 'Trimmed123')
