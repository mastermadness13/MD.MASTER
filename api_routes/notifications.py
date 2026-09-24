"""Notifications API."""

from __future__ import annotations

from flask import Blueprint, session

from api_routes.helpers import api_login_required, api_permission_required, ok
from flask_db import get_db
from security import csrf_required
from services import notification_service

bp = Blueprint('api_notifications', __name__, url_prefix='/api/notifications')


@bp.route('')
@api_login_required
@api_permission_required('dashboard.view')
def api_notifications():
    db = get_db()
    uid = session['user_id']
    return ok({
        'notifications': notification_service.get_user_notifications(db, uid),
        'unread_count': notification_service.get_unread_count(db, uid),
    })


@bp.route('/unread-count')
@api_login_required
@api_permission_required('dashboard.view')
def api_notifications_unread_count():
    db = get_db()
    return ok({'unread_count': notification_service.get_unread_count(db, session['user_id'])})


@bp.route('/read', methods=['POST'])
@api_login_required
@api_permission_required('dashboard.view')
@csrf_required
def api_notifications_read():
    db = get_db()
    notification_service.mark_all_read(db, session['user_id'])
    return ok(True)
