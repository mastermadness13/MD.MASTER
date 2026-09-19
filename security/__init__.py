"""Security package — authentication, authorization, and CSRF.

Modules:
  auth.py          session → user resolution (get_user / current_user)
  authorization.py permission checks + login/permission decorators + nav
  csrf.py          CSRF token generation and validation

Everything is re-exported here for a single import site:
    from security import login_required, permission_required, csrf_required
"""

# /     /     >---- حزمة الأمان: تسجيل الدخول + الصلاحيات + الحماية من CSRF

# ── استيراد دالة المستخدم ──────────────────────────────────────
from security.auth import current_user, get_user

# ── استيراد دوال الصلاحيات والديكوريتورات ──────────────────────
from security.authorization import (
    get_granted_roles,
    get_header_messages_url,
    get_nav_items,
    get_user_permissions,
    has_permission,
    highest_priority_role,
    inject_navigation,
    login_required,
    permission_required,
    role_required,
    any_role_required,
)

# ── استيراد دوال CSRF ──────────────────────────────────────────
from security.csrf import csrf_required, generate_csrf_token

# ─────────────────────────────────────────────

# /     /     >---- نتأكد قوة كلمة المرور ونرجع رسالة خطأ بالعربي إذا ضعيفة
def validate_password(password: str) -> str | None:
    """Return an Arabic error message if *password* is too weak, else ``None``.

    Rules: ≥ 8 chars, at least one uppercase, one lowercase, one digit.
    """
    # /     /     >---- 8 أحرف أو أكثر
    if len(password) < 8:
        return 'كلمة المرور يجب أن تكون 8 أحرف على الأقل'
    # /     /     >---- حرف كبير على الأقل
    if not any(c.isupper() for c in password):
        return 'كلمة المرور يجب أن تحتوي على حرف كبير واحد على الأقل'
    # /     /     >---- حرف صغير على الأقل
    if not any(c.islower() for c in password):
        return 'كلمة المرور يجب أن تحتوي على حرف صغير واحد على الأقل'
    # /     /     >---- رقم على الأقل
    if not any(c.isdigit() for c in password):
        return 'كلمة المرور يجب أن تحتوي على رقم واحد على الأقل'
    return None

# ─────────────────────────────────────────────

__all__ = [
    'get_user',
    'current_user',
    'get_user_permissions',
    'has_permission',
    'login_required',
    'permission_required',
    'role_required',
    'any_role_required',
    'get_granted_roles',
    'highest_priority_role',
    'get_nav_items',
    'get_header_messages_url',
    'inject_navigation',
    'generate_csrf_token',
    'csrf_required',
    'validate_password',
]