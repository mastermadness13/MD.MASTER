"""Auth API — login, logout, and session bootstrap.

The SPA calls ``GET /api/auth/me`` on load to decide between the login screen
and the app shell.  Login accepts JSON (``{username, password, remember}``)
or form-encoded data.
"""

from __future__ import annotations

from flask import Blueprint, request, session, url_for

from api_routes.helpers import body, err, ok, public_user
from core.auth_limits import (
    is_login_blocked,
    record_login_failure,
    reset_login,
)
from core.constants import ROLE_NAMES
from flask_db import get_db
from security import (
    get_header_messages_url,
    get_user_permissions,
)
from core.constants.navigation import get_nav_for_permissions
from security import current_user
from security.csrf import csrf_required
from services import user_service

bp = Blueprint('api_auth', __name__, url_prefix='/api/auth')


def _session_payload():
    from security.authorization import get_granted_roles
    roles = get_granted_roles()
    dept_id = session.get('department_id')
    user = public_user(current_user())
    perms = get_user_permissions(roles, dept_id)
    nav_items = get_nav_for_permissions(perms)
    for item in nav_items:
        try:
            item['url'] = url_for(item['endpoint'])
        except Exception:  # noqa: BLE001 — endpoint may not be resolvable here
            item['url'] = None
    return {
        'user': user,
        'role': session.get('role', ''),
        'role_label': ROLE_NAMES.get(session.get('role', ''), ''),
        'permissions': sorted(perms),
        'nav_items': nav_items,
        'header_messages_url': get_header_messages_url(roles),
        'csrf_token': session.get('_csrf_token', ''),
    }


@bp.route('/login', methods=['POST'])
@csrf_required
def api_login():
    data = body()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    remember = bool(data.get('remember'))
    if not username or not password:
        return err('اسم المستخدم وكلمة المرور مطلوبان', 422)

    client_ip = request.remote_addr or 'unknown'
    if is_login_blocked(client_ip, username):
        return err('تم تجاوز الحد المسموح لمحاولات الدخول، يرجى المحاولة لاحقاً', 429)

    db = get_db()
    success, user = user_service.authenticate(db, username, password, remember, session)
    if not success:
        record_login_failure(client_ip, username)
        if user is not None and user.get('auth_error') == 'initial_code_expired':
            return err(
                'انتهت صلاحية رمز الدخول الأولي ولم يُستعمل، '
                'يرجى مراجعة مدير المكتب لإعادة إرسال رمز جديد',
                401,
            )
        return err('اسم المستخدم أو كلمة المرور غير صحيحة', 401)
    reset_login(client_ip, username)
    return ok(_session_payload())


@bp.route('/logout', methods=['POST'])
@csrf_required
def api_logout():
    if 'user_id' not in session:
        return ok(True)
    session.clear()
    return ok(True)


@bp.route('/me')
def api_me():
    if 'user_id' not in session:
        return err('غير مسجل الدخول', 401)
    return ok(_session_payload())
