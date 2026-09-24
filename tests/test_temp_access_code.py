import sqlite3
from datetime import datetime, timedelta, timezone

from services.temp_access_code import (
    RecoveryCodeResult,
    issue_recovery_code,
    verify_recovery_code,
)
from werkzeug.security import generate_password_hash


def _db():
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute(
        'CREATE TABLE users ('
        'id INTEGER PRIMARY KEY, password TEXT, session_version INTEGER, '
        'recovery_code_hash TEXT, recovery_code_expires_at TEXT, '
        'recovery_code_attempts INTEGER DEFAULT 0, recovery_code_issued_at TEXT, '
        'recovery_code_issued_by INTEGER)'
    )
    db.execute(
        'INSERT INTO users (id, password, session_version) VALUES (1, ?, 7)',
        (generate_password_hash('permanent-password'),),
    )
    db.commit()
    return db


def test_issue_does_not_replace_password_or_session():
    db = _db()
    before = db.execute('SELECT password, session_version FROM users WHERE id = 1').fetchone()
    code = issue_recovery_code(db, user_id=1, issued_by=99)
    after = db.execute('SELECT * FROM users WHERE id = 1').fetchone()

    assert len(code) == 6
    assert code.isdigit()
    assert after['password'] == before['password']
    assert after['session_version'] == before['session_version']
    assert verify_recovery_code(db, dict(after), code) == RecoveryCodeResult.VALID


def test_wrong_code_is_limited_and_expired_codes_are_rejected():
    db = _db()
    issue_recovery_code(db, user_id=1, issued_by=99)
    for _ in range(4):
        user = dict(db.execute('SELECT * FROM users WHERE id = 1').fetchone())
        assert verify_recovery_code(db, user, '000000') == RecoveryCodeResult.INVALID
    user = dict(db.execute('SELECT * FROM users WHERE id = 1').fetchone())
    assert verify_recovery_code(db, user, '000000') == RecoveryCodeResult.LOCKED

    issue_recovery_code(db, user_id=1, issued_by=99)
    db.execute(
        'UPDATE users SET recovery_code_expires_at = ? WHERE id = 1',
        ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),),
    )
    db.commit()
    user = dict(db.execute('SELECT * FROM users WHERE id = 1').fetchone())
    assert verify_recovery_code(db, user, '000000') == RecoveryCodeResult.EXPIRED
