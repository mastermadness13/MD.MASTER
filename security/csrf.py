"""Session-based CSRF protection.

A per-session token is generated once, injected into templates via
``csrf_token()``, and validated on every state-changing request through two
layers:

1. **Framework layer** — ``app.before_request`` rejects POST/PUT/PATCH/DELETE
   without a valid token unless the endpoint is explicitly ``csrf_exempt``.
2. **Per-view layer** — the ``csrf_required`` decorator (legacy/defense in
   depth) repeats the same check.

The token may arrive via the ``_csrf_token`` form field, the JSON body, or the
``X-CSRFToken`` header (checked in that order).
"""

from __future__ import annotations

import secrets
from functools import wraps

from flask import flash, jsonify, request, session

from utils.redirects import redirect_back

# /     /     >---- الطرق التي تتطلب حماية CSRF (طرق تغيير الحالة)
STATE_CHANGING_METHODS = ('POST', 'PUT', 'PATCH', 'DELETE')

# ─────────────────────────────────────────────

# /     /     >---- نصنع رمز الحماية CSRF مرة وحدة لكل جلسة
def generate_csrf_token() -> str:
    """Generate a per-session CSRF token and store it in the session."""
    # /     /     >---- إذا ما فيه رمز في الجلسة نصنع رمز عشوائي جديد
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']

# ─────────────────────────────────────────────

# /     /     >---- نقارن استخراج التوكن من أي مصدر متوقع
def _accept_token() -> bool:
    """True when a valid CSRF token is present for the current request."""
    token = request.form.get('_csrf_token', '')
    if not token:
        # /     /     >---- نجرّبه في جسم JSON
        data = request.get_json(silent=True) or {}
        token = data.get('_csrf_token', '')
    if not token:
        # /     /     >---- وأخيراً من الهيدر X-CSRFToken
        token = request.headers.get('X-CSRFToken', '')
    return bool(token) and token == session.get('_csrf_token', '')

# ─────────────────────────────────────────────

def is_request_protected() -> bool:
    """Framework-level enforcement check.

    Returns *False* only when a state-changing request lacks a valid token and
    the endpoint is not explicitly exempt. Safe to call for every request.
    """
    from flask import current_app
    view_func = current_app.view_functions.get(request.endpoint)
    if view_func is not None and getattr(view_func, '_csrf_exempt', False):
        return True
    if request.method in STATE_CHANGING_METHODS:
        return _accept_token()
    return True


# /     /     >---- استجابة الفشل (نفسها في الطبقتين: JSON لأجاكس، وإلا توجيه)
def csrf_failure_response():
    """The browser and API responses used when CSRF validation fails."""
    # /     /     >---- إذا طلب AJAX نرجع JSON بخطأ
    if (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.headers.get('Accept') == 'application/json'
    ):
        return jsonify({'ok': False, 'message': 'خطأ في التحقق الأمني (CSRF)'}), 403
    # /     /     >---- وإلا نعرض رسالة ونرجع للمستخدم
    flash('خطأ في التحقق الأمني (CSRF)', 'error')
    return redirect_back()


# /     /     >---- وسم إعفاء: يعلّم أن المسار لا يحتاج رمز CSRF
def csrf_exempt(f):
    """Mark a view as exempt from CSRF validation (explicit opt-out)."""
    f._csrf_exempt = True
    return f

# ─────────────────────────────────────────────

# /     /     >---- ديكوريتور يتأكد من رمز CSRF في كل طلب تغيير حالة
def csrf_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # /     /     >---- نتحقق فقط من طلبات التعدي (POST, PUT, PATCH, DELETE)
        if request.method in STATE_CHANGING_METHODS and not _accept_token():
            return csrf_failure_response()
        return f(*args, **kwargs)

    return decorated