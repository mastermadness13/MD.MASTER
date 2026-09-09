"""Dashboard API — role-specific home data as JSON."""

from __future__ import annotations

from flask import Blueprint, request, session

from api.helpers import api_login_required, ok
from flask_db import get_db
from services import dashboard_service
from services.dashboard_service import get_dashboard_stats

bp = Blueprint('api_dashboard', __name__, url_prefix='/api')


@bp.route('/dashboard')
@api_login_required
def api_dashboard():
    role = session.get('role', '')
    show = request.args.get('show', 5, type=int)
    db = get_db()

    payload = {'stats': get_dashboard_stats(role, show)}

    if role == 'head_of_department':
        payload['hod'] = dashboard_service.get_hod_dashboard_data(
            db, session.get('hod_department_id') or session.get('department_id')
        )
    elif role == 'teacher':
        payload['teacher'] = dashboard_service.get_teacher_dashboard_data(
            db, session['user_id']
        )
    elif role == 'exam':
        payload['exam'] = dashboard_service.get_exam_dept_dashboard_data(db)
    elif role == 'research_development':
        payload['rnd'] = dashboard_service.get_rnd_dept_dashboard_data(db)

    return ok(payload)
