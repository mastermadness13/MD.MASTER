from flask import Blueprint, session, request, render_template

from flask_db import get_db
from security import login_required, permission_required
from security import current_user
from services import history_service
from services.search import highlight_text

bp = Blueprint('history', __name__, url_prefix='/history')


@bp.route('')
@login_required
@permission_required('history.view')
def history_list():
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    db = get_db()
    rows, total, page, per_page = history_service.list_history(db, search, page)

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if is_ajax:
        return render_template('audit/list_table.html', records=rows, total=total,
                               page=page, per_page=per_page, search=search,
                               user=current_user(), highlight=highlight_text)

    return render_template('audit/list.html', records=rows, total=total, page=page,
                          per_page=per_page, search=search,
                          user=current_user())


@bp.route('/<int:id>')
@login_required
@permission_required('history.view')
def history_detail(id):
    db = get_db()
    record = history_service.get_history_detail(db, id)
    return render_template('audit/detail.html', record=dict(record) if record else None,
                          user=current_user())
