from flask import Blueprint, session, request, render_template, redirect, url_for, flash, jsonify

from flask_db import get_db
from security import current_user, csrf_required, get_granted_roles
from services.dashboard_service import get_dashboard_stats
from services import dashboard_service
from utils.redirects import redirect_back

bp = Blueprint('dashboard', __name__)


# /     /     >---- تبديل واجهة الدور (مع دعم AJAX وفحص الأدوار الممنوحة)
@bp.route('/switch-role', methods=['POST'])
@csrf_required
def switch_role():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    requested = request.form.get('role', '').strip()
    granted = set(get_granted_roles())
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.headers.get('Accept') == 'application/json'
    )
    if requested in granted:
        session['role'] = requested
        if is_ajax:
            return jsonify({'ok': True, 'message': 'تم تغيير الواجهة'})
        flash('تم تغيير الواجهة', 'success')
    else:
        if is_ajax:
            return jsonify({'ok': False, 'message': 'ليس لديك هذا الدور'}), 403
        flash('ليس لديك هذا الدور', 'error')
    return redirect_back(fallback_endpoint='dashboard.dashboard')


# /     /     >---- الرئيسية: تحويل حسب الدور ثم تحميل قوالب وإحصائيات كل دور
@bp.route('/')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('public_site.index_page'))

    role = session.get('role', '')

    # /     /     >---- أدوار خاصة تُحوَّل مباشرة لصفحاتها المقررة
    if role == 'exam':
        return redirect(url_for('exams.exams'))

    if role == 'faculty_affairs':
        return redirect(url_for('teachers.teachers_list'))

    show = request.args.get('show', 5, type=int)

    # /     /     >---- قالب اللوحة حسب الدور (الافتراضي للأساتذة)
    role_templates = {
        'super_admin': 'dashboard/super_admin.html',
        'research_development': 'dashboard/rnd.html',
        'faculty_affairs': 'dashboard/faculty_affairs.html',
        'head_of_department': 'dashboard/hod.html',
        'teacher': 'dashboard/teacher.html',
        'exam': 'dashboard/exam_dept.html',
    }
    template = role_templates.get(role, 'dashboard/teacher.html')

    stats = get_dashboard_stats(role, show)

    # /     /     >---- بيانات خاصة لكل دور إن لزمت الصفحة
    faculty_data = {}
    if role == 'faculty_affairs':
        db = get_db()
        faculty_data = dashboard_service.get_faculty_affairs_dashboard_data(db)

    hod_data = {}
    if role == 'head_of_department':
        db = get_db()
        dept_id = session.get('hod_department_id')
        hod_data = dashboard_service.get_hod_dashboard_data(db, dept_id)

    teacher_data = {}
    if role == 'teacher':
        db = get_db()
        teacher_data = dashboard_service.get_teacher_dashboard_data(db, session['user_id'])

    dept_data = {}
    if role == 'exam':
        db = get_db()
        dept_data = dashboard_service.get_exam_dept_dashboard_data(db)
    elif role == 'research_development':
        db = get_db()
        dept_data = dashboard_service.get_rnd_dept_dashboard_data(db)

    return render_template(template, user=current_user(),
                          stats=stats, faculty_data=faculty_data,
                          hod_data=hod_data,
                          teacher_data=teacher_data, dept_data=dept_data)