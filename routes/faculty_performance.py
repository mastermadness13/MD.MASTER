"""Faculty Performance Evaluation routes — كشف العبء التدريسي."""

from flask import Blueprint, session, request, render_template, redirect, url_for, flash, jsonify, abort

from flask_db import get_db
from security import login_required, permission_required, csrf_required
from security import current_user
from security.authorization import get_granted_roles, has_permission
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
    - any granted role in (super_admin, faculty_affairs, research_development)
      may access any teacher
    - head_of_department: only teachers in their own department
    - teacher: only themselves (granted even when also holding another role)
    """
    user = current_user()
    if not user:
        abort(401)

    roles = get_granted_roles()
    if any(r in ('super_admin', 'faculty_affairs', 'research_development')
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


@bp.route('/preview/<int:teacher_id>')
@login_required
@permission_required('faculty_performance.view')
def preview(teacher_id):
    """Preview the performance form (read-only)."""
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
        'faculty_performance/preview.html',
        user=current_user(),
        form_data=data,
        research_types=fps.get_select_data(db)['research_types'],
        admin_task_types=fps.get_select_data(db)['admin_task_types'],
        admin_task_hours=fps.get_select_data(db)['admin_task_hours'],
    )


# ── Edit Pages ───────────────────────────────────────────────────

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


@bp.route('/edit-leaves/<int:teacher_id>', methods=['GET', 'POST'])
@login_required
@permission_required('faculty_performance.edit_leaves')
@csrf_required
def edit_leaves(teacher_id):
    """Edit leaves for a teacher."""
    db = get_db()
    _check_teacher_access(db, teacher_id)
    ctx = _get_form_context(db, teacher_id)
    if not ctx:
        flash('العضو غير موجود', 'error')
        return redirect(url_for('faculty_performance.reports_select'))

    academic_year = request.args.get('year') or request.form.get('academic_year', '')
    semester = request.args.get('semester', 1, type=int) or request.form.get('semester', 1, type=int)

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
        flash('تم حفظ الإجازات بنجاح', 'success')
        return redirect(url_for(
            'faculty_performance.preview',
            teacher_id=teacher_id, year=academic_year, semester=semester,
        ))

    repo = fps._repo(db)
    leaves = repo.get_leaves(teacher_id, academic_year, semester)

    return render_template(
        'faculty_performance/edit_leaves.html',
        user=current_user(),
        teacher=ctx,
        leaves=leaves,
        leave_types=fps.get_select_data(db)['leave_types'],
        academic_year=academic_year,
        semester=semester,
    )


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
def member_reports():
    """التقارير: قائمة أعضاء + بحث + عرض التقرير لكل عضو."""
    db = get_db()
    members = fps.list_members_summary(db)
    return render_template(
        'faculty_performance/member_reports.html',
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
