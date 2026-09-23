"""Faculty Performance Evaluation routes — كشف العبء التدريسي."""

from flask import Blueprint, session, request, render_template, redirect, url_for, flash, jsonify, abort

from flask_db import get_db
from security import login_required, permission_required, role_required, csrf_required
from security import current_user
from security.authorization import get_granted_roles, get_active_roles, has_permission
from services import faculty_performance_service as fps

bp = Blueprint('faculty_performance', __name__, url_prefix='/faculty-performance')


def _semester_dates(academic_year: str, semester: int):
    """Return (start_date, end_date) for a given term + semester."""
    from database.repositories.faculty_performance_repository import (
        semester_bounds,
    )
    return semester_bounds(academic_year, semester)


def _check_teacher_access(db, teacher_id):
    """Abort 403 if the current user cannot access this teacher's data.

    Multi-role aware: resolves the user's **granted** roles (``session``
    ``user_roles``/multi-role model) rather than the single legacy
    ``users.role`` column — a user holding the office role may reach any
    teacher even if their fallback DB role says otherwise.

    Rules:
    - any granted role in (faculty_affairs, research_development)
      may access any teacher
    - head_of_department: only teachers in their own department
    - teacher: only themselves (granted even when also holding another role)
    """
    user = current_user()
    if not user:
        abort(401)

    roles = get_granted_roles()
    if any(r in ('faculty_affairs', 'research_development')
           for r in roles):
        return

    teacher = db.execute(
        'SELECT department_id FROM teachers WHERE id = ? AND deleted_at IS NULL',
        (teacher_id,),
    ).fetchone()
    if not teacher:
        abort(404)

    if 'teacher' in roles:
        user_teacher_id = db.execute(
            'SELECT id FROM teachers WHERE user_id = ? AND deleted_at IS NULL',
            (user['id'],),
        ).fetchone()
        if user_teacher_id and user_teacher_id['id'] == teacher_id:
            return

    if 'head_of_department' in roles:
        user_dept = session.get('hod_department_id')
        if user_dept:
            is_member = db.execute(
                'SELECT 1 FROM teacher_departments '
                'WHERE teacher_id = ? AND department_id = ? LIMIT 1',
                (teacher_id, user_dept),
            ).fetchone()
            if is_member:
                return

    abort(403)


def _collect_teaching_rows():
    """Read the editing-rows form arrays into a coherent row list.

    ``rd_id[]`` carries the real ``course_id`` for existing rows and the
    literal ``new`` for rows added in the editor. ``rd_remove[]`` holds the
    ids the user checked for removal.
    """
    ids = request.form.getlist('rd_id[]')
    names = request.form.getlist('rd_course_name[]')
    codes = request.form.getlist('rd_course_code[]')
    ltypes = request.form.getlist('rd_lecture_type[]')
    phases = request.form.getlist('rd_course_phase[]')
    depts = request.form.getlist('rd_department[]')
    groups = request.form.getlist('rd_group[]')
    days = request.form.getlist('rd_day[]')
    starts = request.form.getlist('rd_start_time[]')
    ends = request.form.getlist('rd_end_time[]')
    hours_list = request.form.getlist('rd_hours[]')
    counts_list = request.form.getlist('rd_student_count[]')
    removed = set(request.form.getlist('rd_remove[]'))

    def _at(lst, idx, default=''):
        return lst[idx].strip() if idx < len(lst) else default

    rows = []
    for i, rid in enumerate(ids):
        if rid in removed:
            continue
        course_id = int(rid) if rid.isdigit() else None
        name = _at(names, i)
        code = _at(codes, i)
        day = _at(days, i)
        start = _at(starts, i)
        end = _at(ends, i)
        if course_id is None and not (name or code or day or start or end):
            continue
        raw_hours = _at(hours_list, i, '0') or '0'
        try:
            hours = int(float(raw_hours))
        except ValueError:
            hours = 0
        raw_count = _at(counts_list, i, '')
        student_count = int(raw_count) if raw_count.isdigit() else (raw_count or '')
        rows.append({
            'course_id': course_id,
            'course_name': name,
            'course_code': code,
            'lecture_type': _at(ltypes, i),
            'course_phase': _at(phases, i),
            'department': _at(depts, i),
            'group_number': _at(groups, i),
            'day': day,
            'start_time': start,
            'end_time': end,
            'hours': hours,
            'student_count': student_count,
        })
    return rows


def _save_inline_profile(db, teacher_id, academic_year, semester):
    repo = fps._repo(db)
    repo.save_report_profile_draft(teacher_id, academic_year, semester, {
        'name': request.form.get('name', '').strip(),
        'section': request.form.get('section', '').strip(),
        'dept_name': request.form.get('department', '').strip(),
        'qual_name': request.form.get('qualification', '').strip(),
        'rank_name': request.form.get('rank', '').strip(),
        'specialization': request.form.get('specialization', '').strip(),
        'academic_number': request.form.get('academic_number', '').strip(),
        'national_id': request.form.get('national_id', '').strip(),
        'first_lecture_date': request.form.get('first_lecture_date', '').strip(),
        'work_start_date': request.form.get('work_start_date', '').strip(),
    })

    rows = _collect_teaching_rows()
    repo.save_report_teaching_draft(teacher_id, academic_year, semester, rows)

    counts = {}
    for r in rows:
        if r.get('course_id') and str(r.get('student_count', '')).isdigit():
            counts[r['course_id']] = int(r['student_count'])
    repo.save_student_counts(teacher_id, academic_year, semester, counts)


@bp.route('/preview/<int:teacher_id>', methods=['GET', 'POST'])
@login_required
@permission_required('faculty_performance.view')
@csrf_required
def preview(teacher_id):
    """Preview the performance form, with optional inline editing."""
    db = get_db()
    _check_teacher_access(db, teacher_id)
    academic_year = request.args.get('year', '')
    semester = request.args.get('semester', type=int)
    department_id = request.args.get('dept', type=int)

    if not academic_year:
        active = fps.get_active_semester(db)
        academic_year = active.get('academic_year', '')
        if semester is None:
            semester = active.get('semester', 1)
    if semester is None:
        semester = 1

    edit_mode = request.args.get('edit') == '1'
    if request.method == 'POST':
        if not has_permission(get_active_roles(), 'faculty_performance.edit_research'):
            abort(403)
        _save_inline_profile(db, teacher_id, academic_year, semester)
        flash('تم حفظ بيانات الأستاذ وأعداد الطلبة بنجاح', 'success')
        return redirect(url_for(
            'faculty_performance.preview', teacher_id=teacher_id,
            year=academic_year, semester=semester,
            dept=request.form.get('dept') or None,
        ))

    data = fps.get_performance_form_data(
        db, teacher_id, academic_year, semester,
        department_id=department_id)
    if not data:
        flash('العضو غير موجود', 'error')
        return redirect(url_for('faculty_performance.reports_select'))

    _leaves_out_of_semester_warning(
        db, data, teacher_id, academic_year, semester)
    select_data = fps.get_select_data(db)
    options = {
        'department': [r['name'] for r in db.execute(
            'SELECT name FROM departments ORDER BY name').fetchall()],
        'qualification': [r['name_ar'] for r in db.execute(
            'SELECT name_ar FROM qualifications ORDER BY name_ar').fetchall()],
        'rank': [r['name_ar'] for r in db.execute(
            'SELECT name_ar FROM academic_ranks ORDER BY name_ar').fetchall()],
        'specialization': [r['name'] for r in db.execute(
            'SELECT name FROM specializations ORDER BY name').fetchall()],
        'course': [r['name'] for r in db.execute(
            'SELECT name FROM courses ORDER BY name').fetchall()],
    }

    return render_template(
        'faculty_performance/preview.html',
        user=current_user(),
        form_data=data,
        research_types=select_data['research_types'],
        admin_task_types=select_data['admin_task_types'],
        admin_task_hours=select_data['admin_task_hours'],
        leave_types=select_data['leave_types'],
        edit_mode=edit_mode,
        profile_options=options,
    )


# ── Edit Pages ───────────────────────────────────────────────────

def _leaves_out_of_semester_warning(db, data, teacher_id, academic_year, semester):
    """Annotate preview warnings when saved leaves fall outside the viewed term.

    Leaves are stored per teacher (not per term); the official form filters
    them by the semester window at read time. So a saved leave whose dates are
    outside the displayed term shows a "hidden edit" symptom — this warning
    tells the user those leaves exist but are not part of this term's form.
    """
    repo = fps._repo(db)
    all_leaves = repo.get_leaves(teacher_id, academic_year, semester)
    entered = sum(
        1 for lv in all_leaves
        if lv.get('leave_type') and lv.get('start_date'))
    visible = len(data.get('leaves') or [])
    hidden = entered - visible
    if hidden > 0:
        warnings = list(data.get('warnings') or [])
        warnings.insert(0, {
            'type': 'leaves_out_of_semester',
            'severity': 'info',
            'message': (
                f'توجد {hidden} إجازة مسجلة خارج فترة الفصل المعروض '
                f'({fps.academic_year_label(academic_year)} — '
                f'{fps.SEMESTER_LABELS.get(semester, "")}). '
                'الإجازات محفوظة لكنها لا تظهر في هذا الكشف.'
            ),
        })
        data['warnings'] = warnings


def _get_form_context(db, teacher_id):
    """Shared context for edit pages."""
    teacher = db.execute(
        'SELECT id, name FROM teachers WHERE id = ? AND deleted_at IS NULL',
        (teacher_id,),
    ).fetchone()
    if not teacher:
        return None
    return dict(teacher)


@bp.route('/edit-research/<int:teacher_id>', methods=['GET', 'POST'])
@login_required
@permission_required('faculty_performance.edit_research')
@csrf_required
def edit_research(teacher_id):
    """Edit research activities for a teacher."""
    db = get_db()
    _check_teacher_access(db, teacher_id)
    ctx = _get_form_context(db, teacher_id)
    if not ctx:
        flash('العضو غير موجود', 'error')
        return redirect(url_for('faculty_performance.reports_select'))

    academic_year = request.args.get('year') or request.form.get('academic_year', '')
    semester = request.args.get('semester', 1, type=int) or request.form.get('semester', 1, type=int)

    if request.method == 'POST':
        activities = []
        types = request.form.getlist('activity_type[]')
        hours_list = request.form.getlist('hours[]')
        notes_list = request.form.getlist('notes[]')
        for i, atype in enumerate(types):
            raw = hours_list[i].strip() if i < len(hours_list) else ''
            hours = int(raw) if raw.isdigit() else 0
            activities.append({
                'activity_type': atype,
                'hours': hours,
                'notes': notes_list[i] if i < len(notes_list) else '',
            })
        fps.save_research_data(db, teacher_id, academic_year, semester, activities)
        flash('تم حفظ الأنشطة البحثية بنجاح', 'success')
        return redirect(url_for(
            'faculty_performance.preview',
            teacher_id=teacher_id, year=academic_year, semester=semester,
        ))

    repo = fps._repo(db)
    research = repo.get_research_activities(teacher_id, academic_year, semester)
    rules_raw = repo.get_workload_rules(
        ctx.get('rank_id', 0) or 0, academic_year
    ) if ctx.get('rank_id') else []
    rules = {r['category']: r for r in rules_raw}
    max_research = rules.get('research', {}).get('max_hours', 10)

    select_data = fps.get_select_data(db)

    return render_template(
        'faculty_performance/edit_research.html',
        user=current_user(),
        teacher=ctx,
        research=research,
        research_types=select_data['research_types'],
        academic_year=academic_year,
        semester=semester,
        max_research=max_research,
    )


@bp.route('/edit-assignments/<int:teacher_id>', methods=['GET', 'POST'])
@login_required
@permission_required('faculty_performance.edit_assignments')
@csrf_required
def edit_assignments(teacher_id):
    """Edit admin assignments for a teacher."""
    db = get_db()
    _check_teacher_access(db, teacher_id)
    ctx = _get_form_context(db, teacher_id)
    if not ctx:
        flash('العضو غير موجود', 'error')
        return redirect(url_for('faculty_performance.reports_select'))

    academic_year = request.args.get('year') or request.form.get('academic_year', '')
    semester = request.args.get('semester', 1, type=int) or request.form.get('semester', 1, type=int)

    if request.method == 'POST':
        assignments = []
        names = request.form.getlist('task_name[]')
        auto_list = request.form.getlist('auto_hours[]')
        manual_list = request.form.getlist('manual_hours[]')
        assign_dates = request.form.getlist('assignment_date[]')
        start_list = request.form.getlist('start_date[]')
        end_list = request.form.getlist('end_date[]')
        notes_list = request.form.getlist('notes[]')
        for i, name in enumerate(names):
            assignments.append({
                'task_name': name,
                'auto_hours': auto_list[i] if i < len(auto_list) else None,
                'manual_hours': manual_list[i] if i < len(manual_list) else 0,
                'assignment_date': assign_dates[i] if i < len(assign_dates) else '',
                'start_date': start_list[i] if i < len(start_list) else '',
                'end_date': end_list[i] if i < len(end_list) else None,
                'notes': notes_list[i] if i < len(notes_list) else '',
                'academic_year': academic_year,
                'semester': semester,
            })
        fps.save_admin_data(db, teacher_id, assignments)
        flash('تم حفظ التكليفات الإدارية بنجاح', 'success')
        return redirect(url_for(
            'faculty_performance.preview',
            teacher_id=teacher_id, year=academic_year, semester=semester,
        ))

    repo = fps._repo(db)
    assignments = repo.get_admin_assignments(teacher_id, academic_year, semester)
    sem_start, sem_end = _semester_dates(academic_year, semester)
    select_data = fps.get_select_data(db)

    return render_template(
        'faculty_performance/edit_assignments.html',
        user=current_user(),
        teacher=ctx,
        assignments=assignments,
        admin_task_types=select_data['admin_task_types'],
        admin_task_hours=select_data['admin_task_hours'],
        academic_year=academic_year,
        semester=semester,
        sem_start=sem_start,
        sem_end=sem_end,
    )


@bp.route('/edit-leaves/<int:teacher_id>')
@login_required
@permission_required('faculty_performance.edit_leaves')
def edit_leaves(teacher_id):
    """Legacy leaves editor — superseded by faculty_performance.leaves_manage."""
    return redirect(url_for('faculty_performance.leaves_manage', teacher_id=teacher_id))


# ── Print Page ───────────────────────────────────────────────────

@bp.route('/print/<int:teacher_id>')
@login_required
@permission_required('faculty_performance.print')
def print_form(teacher_id):
    """Print-ready A4 page styled like MS Word."""
    db = get_db()
    _check_teacher_access(db, teacher_id)
    academic_year = request.args.get('year', '')
    semester = request.args.get('semester', type=int)
    department_id = request.args.get('dept', type=int)

    if not academic_year:
        active = fps.get_active_semester(db)
        academic_year = active.get('academic_year', '')
        if semester is None:
            semester = active.get('semester', 1)
    if semester is None:
        semester = 1

    data = fps.get_performance_form_data(
        db, teacher_id, academic_year, semester,
        department_id=department_id)
    if not data:
        flash('العضو غير موجود', 'error')
        return redirect(url_for('faculty_performance.reports_select'))

    return render_template(
        'faculty_performance/print.html',
        form_data=data,
    )


# ── Official Reports Office (مكتب إدارة أعضاء هيئة التدريس) ──

@bp.route('/reports')
@login_required
@permission_required('faculty_performance.view')
def reports_select():
    """Unified selection screen: report per course OR per teacher."""
    db = get_db()
    select_data = fps.get_select_data(db)
    return render_template(
        'faculty_performance/select_report.html',
        user=current_user(),
        select_data=select_data,
    )


@bp.route('/reports/course/<int:course_id>')
@login_required
@permission_required('faculty_performance.view')
def course_report(course_id):
    """Course-level official report: themed view or Word-style print."""
    db = get_db()
    academic_year = request.args.get('year', '')
    semester = request.args.get('semester', 1, type=int)
    department_id = request.args.get('dept', type=int)
    view = request.args.get('view', 'interface')

    if not academic_year:
        flash('يرجى تحديد العام الجامعي', 'error')
        return redirect(url_for('faculty_performance.reports_select'))

    data = fps.get_course_report_data(
        db, course_id, academic_year, semester, department_id)
    if not data:
        flash('المقرر غير موجود', 'error')
        return redirect(url_for('faculty_performance.reports_select'))

    template = ('faculty_performance/print_course.html'
                if view == 'print'
                else 'faculty_performance/report_course.html')
    return render_template(
        template,
        user=current_user(),
        form_data=data,
    )


# ── Faculty Affairs Office modules (تقارير الأعضاء + الإجازات) ──


@bp.route('/member-reports')
@login_required
@permission_required('faculty_performance.view')
@role_required('faculty_affairs')
def member_reports():
    """التقارير: قائمة أعضاء + بحث + عرض التقرير لكل عضو."""
    db = get_db()
    members = fps.list_members_summary(db)
    return render_template(
        'faculty_performance/member_reports.html',
        user=current_user(),
        members=members,
    )


@bp.route('/performance-rate-list')
@login_required
@permission_required('faculty_performance.view_summary')
def performance_rate_list():
    """قائمة معدل الأداء — ملخص الساعات لكل الأعضاء (للسوبر أدمن).

    Consumed by the super-admin sidebar item. Shows per-member teaching /
    research / admin / leaves totals (the same numbers as the official
    performance form) plus the sum across all members.
    """
    db = get_db()
    academic_year = request.args.get('year', '')
    semester = request.args.get('semester', type=int)

    active = fps.get_active_semester(db)
    if not academic_year:
        academic_year = active.get('academic_year', '')
    if semester is None:
        semester = active.get('semester', 1)

    rows, totals = fps.list_members_performance_summary(
        db, academic_year, semester)

    return render_template(
        'faculty_performance/performance_rate_list.html',
        user=current_user(),
        rows=rows,
        totals=totals,
        academic_year=academic_year,
        semester=semester,
        semester_label=fps.SEMESTER_LABELS.get(semester, ''),
        academic_year_label=fps.academic_year_label(academic_year),
        academic_years=fps.get_select_data(db)['academic_years'],
    )


@bp.route('/assignments')
@login_required
@permission_required('faculty_performance.edit_assignments')
def assignments_index():
    """المهام الإدارية: اختيار عضو لإضافة/تعديل تكليفاته الإدارية."""
    db = get_db()
    members = fps.list_members_summary(db)
    return render_template(
        'faculty_performance/assignments_index.html',
        user=current_user(),
        members=members,
    )


@bp.route('/leaves')
@login_required
@permission_required('faculty_performance.edit_leaves')
def leaves_index():
    """الإجازات: اختيار عضو لإدارة إجازاته."""
    db = get_db()
    members = fps.list_members_summary(db)
    return render_template(
        'faculty_performance/leaves_index.html',
        user=current_user(),
        members=members,
    )


@bp.route('/leaves/<int:teacher_id>/manage', methods=['GET', 'POST'])
@login_required
@permission_required('faculty_performance.edit_leaves')
@csrf_required
def leaves_manage(teacher_id):
    """إدارة إجازات عضو (صفحة مستقلة داخل المكتب)."""
    db = get_db()
    _check_teacher_access(db, teacher_id)
    ctx = fps._repo(db).get_teacher_profile(teacher_id)
    if not ctx:
        flash('العضو غير موجود', 'error')
        return redirect(url_for('faculty_performance.leaves_index'))

    if request.method == 'POST':
        leaves = []
        types = request.form.getlist('leave_type[]')
        d_numbers = request.form.getlist('decision_number[]')
        d_authorities = request.form.getlist('decision_authority[]')
        d_dates = request.form.getlist('decision_date[]')
        s_dates = request.form.getlist('start_date[]')
        e_dates = request.form.getlist('end_date[]')
        hours_list = request.form.getlist('hours[]')
        notes_list = request.form.getlist('notes[]')
        for i, lt in enumerate(types):
            leaves.append({
                'leave_type': lt,
                'decision_number': d_numbers[i] if i < len(d_numbers) else '',
                'decision_authority': d_authorities[i] if i < len(d_authorities) else '',
                'decision_date': d_dates[i] if i < len(d_dates) else '',
                'start_date': s_dates[i] if i < len(s_dates) else '',
                'end_date': e_dates[i] if i < len(e_dates) else None,
                'hours': hours_list[i] if i < len(hours_list) else 0,
                'notes': notes_list[i] if i < len(notes_list) else '',
            })
        fps.save_leaves_data(db, teacher_id, leaves)
        flash('تم حفظ إجازات العضو بنجاح', 'success')
        return redirect(url_for(
            'faculty_performance.leaves_manage', teacher_id=teacher_id))

    leaves = fps._repo(db).get_leaves(teacher_id, '', 1)
    return render_template(
        'faculty_performance/leaves_manage.html',
        user=current_user(),
        teacher=ctx,
        leaves=leaves,
        leave_types=fps.get_select_data(db)['leave_types'],
    )


@bp.route('/leaves/<int:teacher_id>/print')
@login_required
@permission_required('faculty_performance.print')
def leaves_print(teacher_id):
    """تقرير إجازات عضو — صفحة طباعة A4."""
    db = get_db()
    _check_teacher_access(db, teacher_id)
    data = fps.get_leave_report_data(db, teacher_id)
    if not data:
        flash('العضو غير موجود', 'error')
        return redirect(url_for('faculty_performance.leaves_index'))
    return render_template(
        'faculty_performance/leaves_report.html',
        print_title='تقرير الإجازات',
        report=data,
    )


# ── AJAX API ─────────────────────────────────────────────────────

@bp.route('/api/teachers-by-dept')
@login_required
@permission_required('faculty_performance.view')
def api_teachers_by_dept():
    """Return teachers list for a department (AJAX dropdown)."""
    dept_id = request.args.get('department_id', type=int)
    if not dept_id:
        return jsonify([])
    db = get_db()
    teachers = fps.get_teachers_by_dept(db, dept_id)
    return jsonify(teachers)


# ── Leaves AJAX (in-place modal — no redirect after save) ──────

@bp.route('/api/teachers/<int:teacher_id>/leaves')
@login_required
@permission_required('faculty_performance.view')
def api_teacher_leaves(teacher_id):
    """Return one teacher's leaves for the in-page leave editor modal."""
    db = get_db()
    _check_teacher_access(db, teacher_id)
    repo = fps._repo(db)
    teacher = repo.get_teacher_profile(teacher_id)
    if not teacher:
        return jsonify({'ok': False, 'message': 'العضو غير موجود'}), 404
    return jsonify({
        'ok': True,
        'teacher_id': teacher_id,
        'teacher_name': teacher.get('name', ''),
        'dept_name': teacher.get('dept_name', '') or '',
        'leave_types': fps.get_select_data(db)['leave_types'],
        'leaves': repo.get_leaves(teacher_id, '', 1),
    })


@bp.route('/api/teachers/<int:teacher_id>/leaves', methods=['POST'])
@login_required
@permission_required('faculty_performance.edit_leaves')
@csrf_required
def api_teacher_leaves_save(teacher_id):
    """Save leaves from the in-page modal — JSON only, never redirects."""
    db = get_db()
    _check_teacher_access(db, teacher_id)
    payload = request.get_json(silent=True) or {}
    cleaned = []
    for lv in payload.get('leaves') or []:
        leave_type = (lv.get('leave_type') or '').strip()
        start_date = lv.get('start_date') or ''
        if not leave_type or not start_date:
            continue
        cleaned.append({
            'leave_type': leave_type,
            'decision_number': lv.get('decision_number') or '',
            'decision_authority': lv.get('decision_authority') or '',
            'decision_date': lv.get('decision_date') or '',
            'start_date': start_date,
            'end_date': lv.get('end_date') or None,
            'hours': int(lv.get('hours') or 0),
            'notes': lv.get('notes') or '',
        })
    fps.save_leaves_data(db, teacher_id, cleaned)
    return jsonify({
        'ok': True,
        'success': True,
        'teacher_id': teacher_id,
        'leaves_count': len(cleaned),
        'total_hours': sum(int(lv['hours']) for lv in cleaned),
    })


@bp.route('/api/teachers/<int:teacher_id>/leaves-section')
@login_required
@permission_required('faculty_performance.view')
def api_teacher_leaves_section(teacher_id):
    """Rendered leaves section + warnings for live in-page refresh (preview)."""
    db = get_db()
    _check_teacher_access(db, teacher_id)
    academic_year = request.args.get('year', '')
    semester = request.args.get('semester', 1, type=int)
    department_id = request.args.get('dept', type=int)
    if not academic_year:
        active = fps.get_active_semester(db)
        academic_year = active.get('academic_year', '')
        if semester is None:
            semester = active.get('semester', 1)
    if semester is None:
        semester = 1

    data = fps.get_performance_form_data(
        db, teacher_id, academic_year, semester,
        department_id=department_id)
    if not data:
        return jsonify({'ok': False, 'message': 'العضو غير موجود'}), 404
    _leaves_out_of_semester_warning(
        db, data, teacher_id, academic_year, semester)
    return jsonify({
        'ok': True,
        'teacher_id': teacher_id,
        'leaves_html': render_template(
            'faculty_performance/_leaves_section.html', fd=data),
        'warnings_html': render_template(
            'faculty_performance/_preview_warnings.html',
            warnings=data.get('warnings') or []),
    })


# ── Research hours AJAX (in-place modal — no redirect after save) ──

def _resolve_term(db, year, semester):
    """Return (academic_year, semester), defaulting to the active term."""
    if not year:
        active = fps.get_active_semester(db)
        return active.get('academic_year', ''), active.get('semester', 1) if semester is None else semester
    return year, semester if semester is not None else 1


@bp.route('/api/teachers/<int:teacher_id>/research')
@login_required
@permission_required('faculty_performance.view')
def api_teacher_research(teacher_id):
    """Return one teacher's research activities for the in-page editor modal."""
    db = get_db()
    _check_teacher_access(db, teacher_id)
    repo = fps._repo(db)
    teacher = repo.get_teacher_profile(teacher_id)
    if not teacher:
        return jsonify({'ok': False, 'message': 'العضو غير موجود'}), 404
    academic_year, semester = _resolve_term(
        db, request.args.get('year', ''), request.args.get('semester', type=int))

    research = repo.get_research_activities(teacher_id, academic_year, semester)
    rules_raw = repo.get_workload_rules(
        teacher.get('rank_id', 0) or 0, academic_year
    ) if teacher.get('rank_id') else []
    rules = {r['category']: r for r in rules_raw}
    max_research = rules.get('research', {}).get('max_hours', 10)

    return jsonify({
        'ok': True,
        'teacher_id': teacher_id,
        'teacher_name': teacher.get('name', ''),
        'dept_name': teacher.get('dept_name', '') or '',
        'academic_year': academic_year,
        'semester': semester,
        'research_types': fps.get_select_data(db)['research_types'],
        'max_research': max_research,
        'research': research,
    })


@bp.route('/api/teachers/<int:teacher_id>/research', methods=['POST'])
@login_required
@permission_required('faculty_performance.edit_research')
@csrf_required
def api_teacher_research_save(teacher_id):
    """Save research activities from the in-page modal — JSON only, never redirects."""
    db = get_db()
    _check_teacher_access(db, teacher_id)
    payload = request.get_json(silent=True) or {}
    academic_year, semester = _resolve_term(
        db, payload.get('academic_year') or '', int(payload.get('semester') or 1))

    activities = []
    for act in payload.get('activities') or []:
        atype = (act.get('activity_type') or '').strip()
        if not atype:
            continue
        raw = str(act.get('hours') or '')
        hours = int(raw) if str(raw).isdigit() else 0
        activities.append({
            'activity_type': atype,
            'hours': hours,
            'notes': (act.get('notes') or '').strip(),
        })
    fps.save_research_data(db, teacher_id, academic_year, semester, activities)
    return jsonify({
        'ok': True,
        'success': True,
        'teacher_id': teacher_id,
        'total_hours': sum(int(a['hours']) for a in activities),
    })


@bp.route('/api/teachers/<int:teacher_id>/research-section')
@login_required
@permission_required('faculty_performance.view')
def api_teacher_research_section(teacher_id):
    """Rendered research section + grand total for live in-page refresh (preview)."""
    db = get_db()
    _check_teacher_access(db, teacher_id)
    academic_year, semester = _resolve_term(
        db, request.args.get('year', ''), request.args.get('semester', type=int))
    department_id = request.args.get('dept', type=int)

    data = fps.get_performance_form_data(
        db, teacher_id, academic_year, semester, department_id=department_id)
    if not data:
        return jsonify({'ok': False, 'message': 'العضو غير موجود'}), 404
    return jsonify({
        'ok': True,
        'teacher_id': teacher_id,
        'research_html': render_template(
            'faculty_performance/_research_section.html', fd=data),
        'grand_total': data.get('grand_total', data.get('total_hours')),
    })


# ── Admin assignments AJAX (in-place modal — no redirect after save) ──

@bp.route('/api/teachers/<int:teacher_id>/assignments')
@login_required
@permission_required('faculty_performance.view')
def api_teacher_assignments(teacher_id):
    """Return one teacher's admin assignments for the in-page editor modal."""
    db = get_db()
    _check_teacher_access(db, teacher_id)
    repo = fps._repo(db)
    teacher = repo.get_teacher_profile(teacher_id)
    if not teacher:
        return jsonify({'ok': False, 'message': 'العضو غير موجود'}), 404
    academic_year, semester = _resolve_term(
        db, request.args.get('year', ''), request.args.get('semester', type=int))

    sem_start, sem_end = _semester_dates(academic_year, semester)
    select_data = fps.get_select_data(db)

    return jsonify({
        'ok': True,
        'teacher_id': teacher_id,
        'teacher_name': teacher.get('name', ''),
        'dept_name': teacher.get('dept_name', '') or '',
        'academic_year': academic_year,
        'semester': semester,
        'assignments': repo.get_admin_assignments(teacher_id, academic_year, semester),
        'admin_task_types': select_data['admin_task_types'],
        'admin_task_hours': select_data['admin_task_hours'],
        'sem_start': sem_start,
        'sem_end': sem_end,
    })


@bp.route('/api/teachers/<int:teacher_id>/assignments', methods=['POST'])
@login_required
@permission_required('faculty_performance.edit_assignments')
@csrf_required
def api_teacher_assignments_save(teacher_id):
    """Save admin assignments from the in-page modal — JSON only, never redirects."""
    db = get_db()
    _check_teacher_access(db, teacher_id)
    payload = request.get_json(silent=True) or {}
    academic_year, semester = _resolve_term(
        db, payload.get('academic_year') or '', int(payload.get('semester') or 1))

    assignments = []
    for a in payload.get('assignments') or []:
        task_name = (a.get('task_name') or '').strip()
        if not task_name:
            continue
        auto = a.get('auto_hours')
        assignments.append({
            'task_name': task_name,
            'auto_hours': auto if auto is not None and auto != '' else None,
            'manual_hours': int(a.get('manual_hours') or 0),
            'assignment_date': (a.get('assignment_date') or ''),
            'start_date': (a.get('start_date') or ''),
            'end_date': (a.get('end_date') or '') or None,
            'notes': (a.get('notes') or ''),
            'academic_year': academic_year,
            'semester': semester,
        })
    fps.save_admin_data(db, teacher_id, assignments)
    return jsonify({
        'ok': True,
        'success': True,
        'teacher_id': teacher_id,
        'assignments_count': len(assignments),
    })


@bp.route('/api/teachers/<int:teacher_id>/assignments-section')
@login_required
@permission_required('faculty_performance.view')
def api_teacher_assignments_section(teacher_id):
    """Rendered assignments section + grand total for live in-page refresh (preview)."""
    db = get_db()
    _check_teacher_access(db, teacher_id)
    academic_year, semester = _resolve_term(
        db, request.args.get('year', ''), request.args.get('semester', type=int))
    department_id = request.args.get('dept', type=int)

    data = fps.get_performance_form_data(
        db, teacher_id, academic_year, semester, department_id=department_id)
    if not data:
        return jsonify({'ok': False, 'message': 'العضو غير موجود'}), 404
    return jsonify({
        'ok': True,
        'teacher_id': teacher_id,
        'assignments_html': render_template(
            'faculty_performance/_assignments_section.html', fd=data),
        'grand_total': data.get('grand_total', data.get('total_hours')),
    })
