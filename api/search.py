"""Search API — suggestions for list pages (SPA + courses list)."""

from __future__ import annotations

from flask import Blueprint, request, session

from api.helpers import api_permission_required, ok
from services.search_service import SearchService

bp = Blueprint('api_search', __name__, url_prefix='/api/search')


@bp.route('/courses')
@api_permission_required('courses.view')
def search_courses():
    """Autocomplete suggestions for the courses list — raw ``c.*`` rows."""
    q = request.args.get('q', '').strip()
    limit = request.args.get('limit', 8, type=int)
    dept_filter = request.args.get('dept_id', '').strip()

    role = session.get('role', '')
    user_dept_id = ((session.get('hod_department_id') or session.get('department_id'))
                    if role == 'head_of_department' else None)

    rows = SearchService().suggest(
        'courses', search=q, dept_filter=dept_filter,
        user_dept_id=user_dept_id, limit=limit,
    )
    return ok({'items': rows})