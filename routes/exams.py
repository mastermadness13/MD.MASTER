from collections import OrderedDict

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from flask_db import get_db
from security import current_user, login_required, permission_required
from services import exam_service

from core.constants.seasons import season_label

bp = Blueprint('exams', __name__, url_prefix='/exams')


@bp.route('')
@login_required
@permission_required('exams.view')
def exams():
    """Single exam workspace — one role-aware exam matrix.

    Data is served by the REST API in ``api/exams.py`` and rendered
    client-side; the API re-enforces every action.
    """
    role = session.get('role', '')
    db = get_db()
    period = exam_service.resolve_academic_period(db)
    return render_template(
        'exams/workspace.html',
        user=current_user(),
        role=role,
        period_year=period.get('yearLabel', ''),
        season_word=period.get('seasonWord', ''),
    )


