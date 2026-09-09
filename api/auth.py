"""Auth API — login, logout, and session bootstrap.

The SPA calls ``GET /api/auth/me`` on load to decide between the login screen
and the app shell.  Login accepts JSON (``{username, password, remember}``)
or form-encoded data.
"""

from __future__ import annotations

from flask import Blueprint, request, session, url_for

from api.helpers import body, err, ok, public_user
from core.constants import ROLE_NAMES
from core.rate_limiter import RateLimiter
from flask_db import get_db
from security import (
    get_header_messages_url,
    get_nav_items,
    get_user_permissions,
)
from security import current_user
from security.csrf import csrf_required
from services import user_service

bp = Blueprint('api_auth', __name__, url_prefix='/api/auth')

# Same throttle as the HTML login form (routes/auth.py) so the API endpoint
# cannot be used to brute-force credentials.
_api_login_limiter = RateLimiter(max_requests=5, window_seconds=60)


def _session_payload():
    role = session.get('role', '')
    dept_id = session.get('department_id')
    user = public_user(current_user())
    nav_items = get_nav_items(role, dept_id)
    for item in nav_items:
        try:
            item['url'] = url_for(item['endpoint'])
        except Exception:  # noqa: BLE001 — endpoint may not be resolvable here
            item['url'] = None
    return {
        'user': user,
        'role': role,
        'role_label': ROLE_NAMES.get(role, role),
        'permissions': sorted(get_user_permissions(role, dept_id)),
        'nav_items': nav_items,
        'header_messages_url': get_header_messages_url(role),
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
    if _api_login_limiter.is_limited(client_ip):
        return err('تم تجاوز الحد المسموح لمحاولات الدخول، يرجى المحاولة لاحقاً', 429)
    _api_login_limiter.record(client_ip)

    db = get_db()
    success, user = user_service.authenticate(db, username, password, remember, session)
    if not success:
        return err('اسم المستخدم أو كلمة المرور غير صحيحة', 401)
    _api_login_limiter.reset(client_ip)
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
