"""Session state — resolve the logged-in user from the session."""

from __future__ import annotations

from typing import Any, Optional

from flask import session

from flask_db import get_db

# ─────────────────────────────────────────────

# /     /     >---- نجيب بيانات المستخدم المسجل حالياً من قاعدة البيانات
def get_user() -> Optional[dict]:
    """Return the logged-in user row (as a dict) or None."""
    # /     /     >---- إذا فيه مستخدم في الجلسة نستعلم عنه
    if 'user_id' in session:
        db = get_db()
        # /     /     >---- نجيبه مع اسم قسمه
        user = db.execute(
            'SELECT u.*, d.name AS department_name FROM users u '
            'LEFT JOIN departments d ON u.department_id = d.id WHERE u.id = ?',
            (session['user_id'],),
        ).fetchone()
        return dict(user) if user else None
    return None

# ─────────────────────────────────────────────

# /     /     >---- نفس دالة get_user (اسم مختصر للاستخدام في القوالب)
def current_user() -> Optional[dict]:
    return get_user()