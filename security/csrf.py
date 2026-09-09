"""Session-based CSRF protection.

A per-session token is generated once, injected into templates via
``csrf_token()``, and validated by ``csrf_required`` on every POST from
either the ``_csrf_token`` form field, the JSON body, or the
``X-CSRFToken`` header (checked in that order).
"""

from __future__ import annotations

import secrets
from functools import wraps

from flask import flash, jsonify, request, session

from utils.redirects import redirect_back


def generate_csrf_token() -> str:
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


def csrf_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            token = request.form.get('_csrf_token', '')
            if not token:
                data = request.get_json(silent=True) or {}
                token = data.get('_csrf_token', '')
            if not token:
                token = request.headers.get('X-CSRFToken', '')
            if not token or token != session.get('_csrf_token', ''):
                if (
                    request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                    or request.headers.get('Accept') == 'application/json'
                ):
                    return jsonify({'ok': False, 'message': 'خطأ في التحقق الأمني (CSRF)'}), 403
                flash('خطأ في التحقق الأمني (CSRF)', 'error')
                return redirect_back()
        return f(*args, **kwargs)

    return decorated
