"""Short-lived recovery codes that do not replace a user's real password."""

from __future__ import annotations

import secrets
import re
from datetime import datetime, timedelta, timezone
from enum import Enum

from werkzeug.security import check_password_hash, generate_password_hash

CODE_VALID_MINUTES = 60
MAX_ATTEMPTS = 5
USERNAME_PATTERN = re.compile(r'^[A-Za-z][A-Za-z0-9_]{2,31}$')


class RecoveryCodeResult(str, Enum):
    VALID = 'valid'
    INVALID = 'invalid'
    LOCKED = 'locked'
    EXPIRED = 'expired'
    NONE_ISSUED = 'none_issued'


def _now() -> datetime:
    return datetime.now(timezone.utc)


def generate_recovery_code() -> str:
    return ''.join(secrets.choice('0123456789') for _ in range(6))


def validate_username(username: str) -> str | None:
    if not USERNAME_PATTERN.fullmatch(username or ''):
        return (
            'اسم المستخدم يجب أن يكون باللغة الإنجليزية فقط، بدون مسافات أو رموز '
            'ويبدأ بحرف، ويسمح بالأرقام والشرطة السفلية _'
        )
    return None


def issue_recovery_code(db, *, user_id: int, issued_by: int) -> str:
    """Issue a code without changing password or session_version."""
    code = generate_recovery_code()
    expires = (_now() + timedelta(minutes=CODE_VALID_MINUTES)).isoformat()
    db.execute(
        'UPDATE users SET recovery_code_hash = ?, '
        'recovery_code_expires_at = ?, recovery_code_attempts = 0, '
        'recovery_code_issued_at = ?, recovery_code_issued_by = ? WHERE id = ?',
        (generate_password_hash(code), expires, _now().isoformat(), issued_by, user_id),
    )
    db.commit()
    return code


def verify_recovery_code(db, user: dict, submitted: str) -> RecoveryCodeResult:
    code_hash = user.get('recovery_code_hash')
    expires_raw = user.get('recovery_code_expires_at')
    if not code_hash or not expires_raw:
        return RecoveryCodeResult.NONE_ISSUED
    try:
        expires = datetime.fromisoformat(expires_raw)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        _clear(db, user['id'])
        return RecoveryCodeResult.EXPIRED
    if _now() > expires:
        _clear(db, user['id'])
        return RecoveryCodeResult.EXPIRED

    attempts = int(user.get('recovery_code_attempts') or 0)
    if attempts >= MAX_ATTEMPTS:
        _clear(db, user['id'])
        return RecoveryCodeResult.LOCKED
    if check_password_hash(code_hash, submitted):
        _clear(db, user['id'])
        return RecoveryCodeResult.VALID

    attempts += 1
    if attempts >= MAX_ATTEMPTS:
        _clear(db, user['id'])
        return RecoveryCodeResult.LOCKED
    db.execute(
        'UPDATE users SET recovery_code_attempts = ? WHERE id = ?',
        (attempts, user['id']),
    )
    db.commit()
    return RecoveryCodeResult.INVALID


def _clear(db, user_id: int) -> None:
    db.execute(
        'UPDATE users SET recovery_code_hash = NULL, '
        'recovery_code_expires_at = NULL, recovery_code_attempts = 0, '
        'recovery_code_issued_at = NULL, recovery_code_issued_by = NULL '
        'WHERE id = ?',
        (user_id,),
    )
    db.commit()
