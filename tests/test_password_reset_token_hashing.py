"""Password-reset tokens must never be recoverable from the database.

The token is a 48-byte ``secrets.token_urlsafe`` value, so a plain SHA-256 is
sufficient: there is no low-entropy secret to brute-force. What matters is that
a leaked database or backup cannot be replayed into an account takeover.
"""

import pytest

from database.repositories.user_repository import _hash_reset_token


def test_hash_is_stable_and_not_the_token():
    token = 'a' * 64
    digest = _hash_reset_token(token)
    assert digest == _hash_reset_token(token)
    assert token not in digest
    assert len(digest) == 64


def test_hash_differs_per_token():
    assert _hash_reset_token('token-one') != _hash_reset_token('token-two')


def test_create_password_reset_stores_only_the_hash(app_fx):
    from flask_db import get_db
    from database.repositories.user_repository import UserRepository

    with app_fx.app_context():
        db = get_db()
        db.execute(
            'INSERT INTO users (username, password, role, is_active) '
            "VALUES ('reset_probe', 'x', 'teacher', 1)"
        )
        db.commit()
        user_id = db.execute(
            "SELECT id FROM users WHERE username = 'reset_probe'"
        ).fetchone()['id']

        repo = UserRepository(db)
        token = 'plaintext-secret-token'
        repo.create_password_reset(user_id, token, '2099-01-01 00:00:00')

        stored = db.execute(
            'SELECT token FROM password_resets WHERE user_id = ?', (user_id,)
        ).fetchall()
        assert stored, 'expected a reset row'
        for row in stored:
            assert row['token'] != token
            assert row['token'] == _hash_reset_token(token)

        # The plaintext token still resolves, because lookup hashes first.
        found = repo.find_valid_reset_token(token)
        assert found is not None
        assert found['user_id'] == user_id

        # A wrong token does not resolve.
        assert repo.find_valid_reset_token('not-the-token') is None

        repo.mark_reset_used(found['id'])

        # Single use, and the secret is gone from the row.
        assert repo.find_valid_reset_token(token) is None
        after = db.execute(
            'SELECT token, used FROM password_resets WHERE id = ?', (found['id'],)
        ).fetchone()
        assert after['used'] == 1
        assert token not in after['token']

        db.execute('DELETE FROM password_resets WHERE user_id = ?', (user_id,))
        db.execute('DELETE FROM users WHERE id = ?', (user_id,))
        db.commit()
