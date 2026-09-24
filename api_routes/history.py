"""History API."""

from __future__ import annotations

from flask import Blueprint

from api_routes.helpers import api_permission_required, err, ok, pagination
from flask_db import get_db
from services import history_service

bp = Blueprint('api_history', __name__, url_prefix='/api/history')


@bp.route('')
@api_permission_required('history.view')
def api_history_list():
    db = get_db()
    page, per_page, search = pagination()
    rows, total, pg, pp = history_service.list_history(db, search, page)
    return ok({
        'items': rows,
        'total': total,
        'page': pg,
        'per_page': pp,
    })


@bp.route('/<int:history_id>')
@api_permission_required('history.view')
def api_history_detail(history_id):
    db = get_db()
    row = history_service.get_history_detail(db, history_id)
    if not row:
        return err('السجل غير موجود', 404)
    return ok({'history': dict(row)})
