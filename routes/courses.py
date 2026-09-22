from flask import (Blueprint, abort, session, request, render_template,
                   redirect, url_for, flash, jsonify)
from utils.redirects import redirect_back

from flask_db import get_db
from database.history import add_history
from security import csrf_required, login_required, permission_required
from security import current_user, has_permission
from services import course_service
from routes.teacher_pages import build_course_content_form_context

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

    can_manage = has_permission(role, 'courses.manage', session.get('department_id'))

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


def _normalize_code(value):
    """Normalize a course code: collapse whitespace and strip surroundings."""
    return ' '.join((value or '').strip().split())


def _codes_dataset(db, dept_id):
    """Rows for the batch code editor: one per course with commas of its departments."""
    if dept_id:
        rows = db.execute(
            '''SELECT c.id, c.code, c.name, c.year,
                      (SELECT GROUP_CONCAT(d.name, '، ')
                       FROM course_departments cd2
                       JOIN departments d ON d.id = cd2.department_id
                       WHERE cd2.course_id = c.id) AS depts,
                      (SELECT GROUP_CONCAT(cd3.department_id, ',')
                       FROM course_departments cd3
                       WHERE cd3.course_id = c.id) AS dept_ids
               FROM courses c
               WHERE c.deleted_at IS NULL
                 AND EXISTS (SELECT 1 FROM course_departments cdx
                             WHERE cdx.course_id = c.id AND cdx.department_id = ?)
               ORDER BY c.name''',
            (dept_id,)
        ).fetchall()
    else:
        rows = db.execute(
            '''SELECT c.id, c.code, c.name, c.year,
                      (SELECT GROUP_CONCAT(d.name, '، ')
                       FROM course_departments cd2
                       JOIN departments d ON d.id = cd2.department_id
                       WHERE cd2.course_id = c.id) AS depts,
                      (SELECT GROUP_CONCAT(cd3.department_id, ',')
                       FROM course_departments cd3
                       WHERE cd3.course_id = c.id) AS dept_ids
               FROM courses c
               WHERE c.deleted_at IS NULL
               ORDER BY c.name'''
        ).fetchall()
    return [dict(r) for r in rows]


def _validate_code_updates(db, updates):
    """Check requested code changes and return (errors, clean_updates).

    ``updates`` is a dict {course_id: new_code}. Validation ensures codes are
    non-blank, unique within the batch, and do not collide with codes of
    courses that are not part of the change.
    """
    errors = []
    clean = {}
    seen_codes = {}
    for cid, code in updates.items():
        code = _normalize_code(code)
        if not code:
            errors.append('أحد المقررات بدون كود')
            continue
        if len(code) > 40:
            errors.append(f'الكود "{code}" طويل جداً')
            continue
        if code in seen_codes:
            errors.append(f'الكود "{code}" مكرر في الإدخال (مقررين مختلفين)')
            continue
        seen_codes[code] = cid
        clean[cid] = code

    if clean:
        excluded = ','.join('?' * len(clean))
        existing = db.execute(
            f'SELECT code FROM courses WHERE deleted_at IS NULL '
            f'AND code IN ({excluded}) AND id NOT IN ({excluded})',
            list(clean.values()) + list(clean.keys()),
        ).fetchall()
        for row in existing:
            errors.append(f'الكود "{row["code"]}" مستخدم لمقرر آخر')
    return errors, clean


@bp.route('/codes', methods=['GET', 'POST'])
@login_required
@permission_required('courses.manage')
@csrf_required
def courses_codes():
    """Batch editor for course codes, per department or for all courses."""
    abort(404)
    db = get_db()
    dept_id = request.form.get('dept', request.args.get('dept', 0, type=int), type=int) or None
    departments = db.execute(
        'SELECT id, name FROM departments WHERE hidden = 0 AND deleted_at IS NULL ORDER BY name'
    ).fetchall()
    unmatched = []
    applied = 0
    tab = request.form.get('tab', request.args.get('tab', 'inline'))
    can_manage_content = has_permission(session.get('role', ''), 'course_content.manage')
    if tab != 'content':
        tab = 'inline'
    content_ctx = {}
    if tab == 'content' and can_manage_content:
        cid = request.form.get('course_id', request.args.get('course_id', 0, type=int), type=int) or None
        sid = request.form.get('submission_id', request.args.get('submission_id', 0, type=int), type=int) or None
        ctx = None
        if cid or sid:
            ctx = build_course_content_form_context(db, course_id=cid, submission_id=sid)
        if ctx is None:
            ctx = build_course_content_form_context(db)
        content_ctx = {
            'content_selected_course_id': cid,
            'content_enabled': True,
            'content_doc': ctx.get('doc') or {},
            'content_curriculum': ctx.get('curriculum') or [],
            'content_theoretical_curriculum': ctx.get('theoretical_curriculum') or [],
            'content_practical_curriculum': ctx.get('practical_curriculum') or [],
            'content_page_mode': ctx.get('page_mode', 'create'),
            'content_edit_submission_id': ctx.get('edit_submission_id'),
            'content_academic_periods': ctx.get('academic_periods') or [],
            'content_default_period': ctx.get('default_period_id'),
            'content_courses': [],
        }
        if not content_ctx['content_courses']:
            content_ctx['content_courses'] = [dict(r) for r in db.execute(
                '''SELECT c.id, c.name, c.code, c.semester,
                          c.theoretical_hours, c.practical_hours, c.total_hours,
                          COALESCE(c.accreditation, 0) AS credits,
                          COALESCE(d.name, '') AS department_name
                   FROM courses c
                   LEFT JOIN course_departments cd ON cd.course_id = c.id
                   LEFT JOIN departments d ON cd.department_id = d.id
                   WHERE c.deleted_at IS NULL
                   GROUP BY c.id
                   ORDER BY c.name'''
            ).fetchall()]

    if request.method == 'POST':
        embed = request.form.get('embed') == '1'
        updates = {}
        bulk_text = (request.form.get('bulk_text') or '').strip()
        if bulk_text:
            for line in bulk_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = []
                for sep in ('\t', '|', '،', ','):
                    if sep in line:
                        parts = line.split(sep, 1)
                        break
                if len(parts) != 2:
                    unmatched.append(f'سطر غير مفهوم: {line}')
                    continue
                code, name = _normalize_code(parts[0]), parts[1].strip()
                if not code or not name:
                    unmatched.append(f'سطر غير مكتمل: {line}')
                    continue
                candidates = db.execute(
                    'SELECT id FROM courses WHERE deleted_at IS NULL AND name = ?',
                    (name,)
                ).fetchall()
                if not candidates:
                    candidates = db.execute(
                        '''SELECT id FROM courses WHERE deleted_at IS NULL
                           AND REPLACE(REPLACE(REPLACE(name, " ", ""), "(", ""), ")", "") = ?''',
                        (' '.join(name.split()).replace(' ', '').replace('(', '').replace(')', ''),)
                    ).fetchall()
                if len(candidates) == 1:
                    updates[candidates[0]['id']] = code
                elif len(candidates) > 1:
                    unmatched.append(f'أكثر من مقرر باسم "{name}"')
                else:
                    unmatched.append(f'لا يوجد مقرر باسم "{name}"')
        else:
            for key, value in request.form.items():
                if key.startswith('code_') and value is not None:
                    try:
                        updates[int(key[len('code_'):])] = value
                    except (ValueError, TypeError):
                        continue

        errors, clean = _validate_code_updates(db, updates)
        if errors:
            for msg in errors:
                flash(msg, 'error')
        else:
            changed = 0
            for cid, code in clean.items():
                row = db.execute('SELECT code FROM courses WHERE id = ?', (cid,)).fetchone()
                if row and _normalize_code(row['code']) != code:
                    db.execute('UPDATE courses SET code = ? WHERE id = ?', (code, cid))
                    add_history(
                        db, 'update', 'course', cid,
                        session.get('user_id'), session.get('username'),
                        f'تحديث كود المقرر إلى: {code}',
                    )
                    changed += 1
            db.commit()
            applied = changed
            if changed:
                flash(f'تم تحديث أكواد {changed} مقرر', 'success')
            else:
                flash('لا تغييرات على الأكواد', 'info')
        if unmatched:
            for msg in unmatched[:20]:
                flash(f'لم يُطبّق: {msg}', 'error')
        if applied or errors or unmatched:
            if embed:
                return redirect(url_for('courses.courses_list', view='codes'))
            return redirect(url_for('courses.courses_list'))

    courses = _codes_dataset(db, dept_id)
    content_ctx.update({
        'courses': courses,
        'departments': departments,
        'dept_id': dept_id,
        'tab': tab,
        'can_manage_content': can_manage_content,
        'user': current_user(),
    })
    return render_template('courses/codes.html', **content_ctx)
