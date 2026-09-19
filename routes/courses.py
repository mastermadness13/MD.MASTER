from flask import (Blueprint, session, request, render_template,
                   redirect, url_for, flash, jsonify)
from utils.redirects import redirect_back

from flask_db import get_db
from database.history import add_history
from security import csrf_required, login_required, permission_required
from security import current_user
from services import course_service

bp = Blueprint('courses', __name__, url_prefix='/courses')


def _build_placements(form):
    """Build per-department placements from a form submission.

    Prefers the ``placements`` JSON field (list of {department_id, semester}).
    Falls back to ``department_ids`` plus a parallel ``dept_semester[]`` array.
    Returns a list of placement dicts, or a plain list of department IDs when
    no semester info is provided (backward compatible).
    """
    placements_json = (form.get('placements') or '').strip()
    if placements_json:
        try:
            import json as _json
            parsed = _json.loads(placements_json)
            placements = []
            for p in parsed:
                if not isinstance(p, dict):
                    continue
                did = p.get('department_id') or p.get('dept_id')
                if not did:
                    continue
                placements.append({
                    'department_id': int(did),
                    'semester': int(p.get('semester') or 1),
                })
            if placements:
                return placements
        except (ValueError, TypeError):
            pass

    department_ids = form.getlist('department_ids')
    semesters = form.getlist('dept_semester')
    placements = []
    for i, did in enumerate(department_ids):
        if not did.strip().isdigit():
            continue
        sem = 1
        if i < len(semesters) and semesters[i].strip().isdigit():
            sem = int(semesters[i])
        placements.append({'department_id': int(did), 'semester': sem})
    if placements:
        return placements
    return [int(d) for d in department_ids if d.strip().isdigit()]


@bp.route('')
@login_required
@permission_required('courses.view')
def courses_list():
    role = session.get('role', '')
    user_data = current_user()
    db = get_db()

    user_dept_id = None
    if role == 'head_of_department' and user_data:
        user_dept_id = session.get('hod_department_id')

    dept_plans = []
    if role == 'head_of_department':
        if user_dept_id:
            data = course_service.get_department_course_tables(db, user_dept_id)
            if data.get('department'):
                dept_plans = [course_service.dept_plan_with_icon(data)]
    else:
        dept_plans = course_service.build_dept_plans(db)

    payload = course_service.build_list_payload(db)

    return render_template('courses/list.html', dept_plans=dept_plans, payload=payload,
                          user=user_data,
                          _view=request.args.get('view', 'list'),
                          _page=request.args.get('page', 1, type=int))


@bp.route('/api/move', methods=['POST'])
@login_required
@permission_required('courses.manage')
@csrf_required
def courses_api_move():
    from api.courses import api_courses_move
    return api_courses_move()


@bp.route('/api/sync-from-timetable', methods=['POST'])
@login_required
@permission_required('courses.manage')
@csrf_required
def courses_api_sync_from_timetable():
    from api.courses import api_courses_sync_from_timetable
    return api_courses_sync_from_timetable()


@bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('courses.manage')
@csrf_required
def courses_create():
    db = get_db()
    departments, courses, course_dept_map = course_service.get_create_form_data(db)
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        name = request.form.get('name', '').strip()
        placements = _build_placements(request.form)
        department_ids = [p['department_id'] for p in placements] \
            if placements and isinstance(placements[0], dict) else placements
        form = {
            'code': code, 'name': name,
            'theoretical_hours': request.form.get('theoretical_hours', 0, type=int),
            'practical_hours': request.form.get('practical_hours', 0, type=int),
            'total_hours': request.form.get('total_hours', 0, type=int),
            'icon': (request.form.get('icon', '📖').strip() or '📖'),
            'notes': request.form.get('notes', '').strip(),
            'year': request.form.get('year', type=int),
            'semester': request.form.get('semester', type=int),
        }
        prerequisite_id = request.form.get('prerequisite_id', type=int)
        year = request.form.get('year', type=int)
        semester = request.form.get('semester', type=int)
        if not code or not name:
            form['department_ids'] = department_ids
            form['prerequisite_id'] = prerequisite_id
            return render_template('courses/create.html', departments=departments, courses=courses,
                                  course_dept_map=course_dept_map,
                                  form=form, form_error='الكود والاسم مطلوبان',
                                  user=current_user())
        if not department_ids:
            form['department_ids'] = department_ids
            form['prerequisite_id'] = prerequisite_id
            return render_template('courses/create.html', departments=departments, courses=courses,
                                  course_dept_map=course_dept_map,
                                  form=form, form_error='يرجى تحديد قسم واحد على الأقل',
                                  user=current_user())
        if year is None or year < 1:
            # Derive the global semester from the primary (first) placement.
            semester = semester or (placements[0]['semester'] if placements and isinstance(placements[0], dict) else 1)
        else:
            semester = semester
        if semester is None or semester < 1:
            semester = 1
        form['year'] = year
        form['semester'] = semester
        course_service.create_course(db, form, placements, prerequisite_id)
        flash('تم إضافة المقرر', 'success')
        return redirect(url_for('courses.courses_list'))
    return render_template('courses/create.html', departments=departments, courses=courses,
                          course_dept_map=course_dept_map,
                          form={}, form_error=None,
                          user=current_user())


@bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@permission_required('courses.manage')
@csrf_required
def courses_edit(id):
    db = get_db()
    c = course_service.get_course(db, id)
    if not c:
        flash('المقرر غير موجود', 'error')
        return redirect(url_for('courses.courses_list'))
    departments, courses, course_dept_map, prereq_ids, current_dept_ids = course_service.get_edit_form_data(db, id)
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        name = request.form.get('name', '').strip()
        placements = _build_placements(request.form)
        department_ids = [p['department_id'] for p in placements] \
            if placements and isinstance(placements[0], dict) else placements
        form = {
            'code': code, 'name': name,
            'theoretical_hours': request.form.get('theoretical_hours', c['theoretical_hours'], type=int),
            'practical_hours': request.form.get('practical_hours', c['practical_hours'], type=int),
            'total_hours': request.form.get('total_hours', c['total_hours'], type=int),
            'icon': (request.form.get('icon', c['icon'] or '📖').strip() or '📖'),
            'notes': request.form.get('notes', '').strip(),
            'year': request.form.get('year', c['year'], type=int) or c['year'],
            'semester': request.form.get('semester', c['semester'], type=int) or c['semester'],
        }
        # Sync global semester with the primary (first) placement if provided.
        if placements and isinstance(placements[0], dict):
            form['semester'] = placements[0]['semester']
        prerequisite_id = request.form.get('prerequisite_id', type=int)
        if not code or not name:
            course_data = dict(c)
            course_data.update(form)
            return render_template('courses/edit.html', course=course_data, departments=departments,
                                  courses=courses, course_dept_map=course_dept_map,
                                  prereq_ids=prereq_ids, current_dept_ids=department_ids or current_dept_ids,
                                  form_error='الكود والاسم مطلوبان',
                                  user=current_user())
        course_service.update_course(db, id, form, placements, prerequisite_id)
        flash('تم تحديث المقرر', 'success')
        return redirect(url_for('courses.courses_list'))
    return render_template('courses/edit.html', course=dict(c), departments=departments,
                          courses=courses, course_dept_map=course_dept_map,
                          prereq_ids=prereq_ids, current_dept_ids=current_dept_ids,
                          user=current_user())


@bp.route('/<int:id>')
@login_required
@permission_required('courses.manage')
def course_detail(id):
    db = get_db()
    result = course_service.get_course_detail(db, id)
    if not result:
        flash('المقرر غير موجود', 'error')
        return redirect(url_for('courses.courses_list'))
    course, departments, prerequisites = result
    return render_template('courses/detail.html', course=course, departments=departments,
                          prerequisites=prerequisites,
                          user=current_user())


@bp.route('/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('courses.manage')
@csrf_required
def courses_delete(id):
    db = get_db()
    course_service.course_delete(db, id, lambda db: add_history(
        db, 'soft_delete', 'course', id, session['user_id'], session['username'], f'حذف مقرر'))
    flash('تم الحذف بنجاح', 'success')
    return redirect_back('courses.courses_list')


@bp.route('/bulk-delete', methods=['POST'])
@login_required
@permission_required('courses.manage')
@csrf_required
def courses_bulk_delete():
    ids = request.form.getlist('course_ids')
    ids = [i for i in ids if i.isdigit()]
    if not ids:
        flash('لم يتم تحديد أي مقررات', 'error')
        return redirect(url_for('courses.courses_list'))
    db = get_db()
    for cid in ids:
        course_service.course_delete(db, int(cid), lambda db, cid=cid: add_history(
            db, 'soft_delete', 'course', int(cid), session['user_id'], session['username'], 'حذف مقرر'))
    flash(f'تم الحذف بنجاح', 'success')
    return redirect_back('courses.courses_list')


@bp.route('/bulk-delete-permanent', methods=['POST'])
@login_required
@permission_required('courses.manage')
@csrf_required
def courses_bulk_permanent_delete():
    ids = request.form.getlist('course_ids')
    expanded = []
    for i in ids:
        for part in i.split(','):
            part = part.strip()
            if part.isdigit():
                expanded.append(part)
    ids = expanded
    if not ids:
        flash('??? ??? ????? ?? ????', 'error')
        return redirect_back('courses.courses_list')
    db = get_db()
    for cid in ids:
        course_service.course_hard_delete(db, int(cid))
    flash(f'تم حذف {len(ids)} مقرر نهائياً', 'success')
    return redirect_back('courses.courses_list')


@bp.route('/restore/<int:id>', methods=['POST'])
@login_required
@permission_required('courses.manage')
@csrf_required
def courses_restore(id):
    db = get_db()
    course_service.course_restore(db, id)
    flash('تم استعادة المقرر', 'success')
    return redirect_back('courses.courses_list')


@bp.route('/delete-permanent/<int:id>', methods=['POST'])
@login_required
@permission_required('courses.manage')
@csrf_required
def courses_delete_permanent(id):
    db = get_db()
    course_service.course_hard_delete(db, id)
    flash('تم حذف المقرر نهائياً', 'success')
    return redirect_back('courses.courses_list')

