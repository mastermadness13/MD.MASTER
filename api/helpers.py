"""Shared helpers for the REST API.

Every endpoint returns a JSON envelope:
  success → {"ok": true, "data": {...}}
  failure → {"ok": false, "message": "...", "errors": {...}?}

Authentication/authorization use the same session as the HTML routes, so the
SPA works with the browser's existing session cookie (same origin).
"""

from __future__ import annotations

import json
from functools import wraps
from sqlite3 import Row

from flask import jsonify, request, session

from security import has_permission


def _clean(value):
    """Recursively convert sqlite3.Row and other non-JSON values."""
    if isinstance(value, Row):
        return _clean(dict(value))
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


def ok(data=None, status=200, **extra):
    payload = {'ok': True, 'data': _clean(data)}
    payload.update(extra)
    return jsonify(payload), status


def err(message, status=400, errors=None):
    payload = {'ok': False, 'message': message}
    if errors:
        payload['errors'] = errors
    return jsonify(payload), status


def pagination(default_per_page=20, max_per_page=100):
    """Read page/per_page/search from query args."""
    page = request.args.get('page', 1, type=int) or 1
    per_page = request.args.get('per_page', default_per_page, type=int)
    per_page = min(max(per_page, 1), max_per_page)
    search = request.args.get('search', '').strip()
    return page, per_page, search


def body():
    """Return the parsed JSON body (or {})."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def public_user(user):
    """Strip sensitive fields (password hash, tokens) from a user dict."""
    if not user:
        return None
    return {k: v for k, v in user.items()
            if 'password' not in k.lower() and 'token' not in k.lower()}


def log_history(db, action, entity_type, entity_id, message):
    """Record a history entry for the current session user."""
    from database.history import add_history
    add_history(
        db, action, entity_type, entity_id,
        session.get('user_id'), session.get('username', ''),
        message,
    )


def install_error_handlers(bp):
    """Register JSON error handlers on an API blueprint (idempotent).

    ``create_app()`` may legitimately run more than once in a process (tests,
    DB migration checks). Flask raises ``AssertionError`` when ``errorhandler``
    is called on a blueprint that was already registered, so each handler set
    is installed exactly once per blueprint.
    """
    if getattr(bp, '_api_json_error_handlers_installed', False):
        return
    bp._api_json_error_handlers_installed = True

    @bp.errorhandler(401)
    def _unauthorized(e):
        return err('يرجى تسجيل الدخول أولاً', 401)

    @bp.errorhandler(403)
    def _forbidden(e):
        return err('ليس لديك صلاحية للوصول', 403)

    @bp.errorhandler(404)
    def _not_found(e):
        return err('الموارد غير موجودة', 404)

    @bp.errorhandler(Exception)
    def _generic(e):
        import logging
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return e
        logging.getLogger('api').exception('API error')
        return err('حدث خطأ غير متوقع', 500)


def api_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return err('يرجى تسجيل الدخول أولاً', 401)
        return f(*args, **kwargs)
    return decorated


def api_permission_required(permission):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                return err('يرجى تسجيل الدخول أولاً', 401)
            role = session.get('role', '')
            dept_id = session.get('department_id')
            if not has_permission(role, permission, dept_id):
                return err('ليس لديك صلاحية للوصول', 403)
            return f(*args, **kwargs)
        # Store required permission for deny-by-default before_request hook
        decorated._required_permission = permission
        return decorated
    return decorator
