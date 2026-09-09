from flask import Blueprint, session, request, render_template, redirect, url_for, flash

from flask_db import get_db
from database.history import add_history
from security import csrf_required, login_required, permission_required
from security import current_user
bp = Blueprint('profile', __name__, url_prefix='/profile')

_ROLE_RESPONSIBILITIES = {
    'research_development': [
        ('menu_book', 'إدارة المقررات الدراسية'),
        ('description', 'مراجعة محتوى المقررات'),
        ('calendar_today', 'إدارة الجدول الدراسي'),
        ('account_tree', 'الاطلاع على الأقسام'),
        ('school', 'إدارة أعضاء هيئة التدريس'),
        ('bar_chart', 'إعداد التقارير'),
    ],
    'head_of_department': [
        ('school', 'متابعة أعضاء هيئة التدريس'),
        ('menu_book', 'عرض المقررات'),
        ('calendar_today', 'إدارة الجدول الدراسي'),
        ('grading', 'إدارة الامتحانات'),
        ('mail', 'مراجعة الرسائل'),
        ('meeting_room', 'إدارة طلبات القاعات'),
    ],
    'teacher': [
        ('calendar_today', 'عرض الجدول الدراسي'),
        ('description', 'إدارة محتوى المقررات'),
        ('upload_file', 'رفع الملفات'),
        ('mail', 'الرسائل'),
        ('meeting_room', 'طلبات القاعات'),
    ],
    'faculty_affairs': [
        ('school', 'إدارة أعضاء هيئة التدريس'),
        ('upload_file', 'رفع الملفات'),
    ],
    'exam': [
        ('calendar_today', 'عرض الجدول الدراسي'),
        ('menu_book', 'عرض المقررات'),
        ('meeting_room', 'عرض القاعات'),
        ('grading', 'إدارة الامتحانات'),
    ],
}


def _resolve_rnd_department(db):
    """Return the R&D department row, or None if not found."""
    return db.execute(
        "SELECT * FROM departments WHERE type = 'administrative' "
        "AND deleted_at IS NULL ORDER BY name"
    ).fetchone()


@bp.route('', methods=['GET', 'POST'])
@login_required
@permission_required('profile.view')
@csrf_required
def profile():
    db = get_db()
    role = session.get('role', '')
    is_rnd = role == 'research_development'

    if request.method == 'POST':
        form_type = request.form.get('form_type', 'account')

        if form_type == 'account':
            return _handle_account_update(db, is_rnd)
        elif form_type == 'department' and is_rnd:
            return _handle_department_update(db)

        flash('طلب غير صالح', 'error')
        return redirect(url_for('profile.profile'))

    return _render_profile(db, is_rnd)


def _handle_account_update(db, is_rnd):
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    label = request.form.get('label', '').strip()
    phone = request.form.get('phone', '').strip()

    if not username:
        return _render_profile(db, is_rnd,
                               form_error='اسم المستخدم مطلوب')

    if len(username) < 2:
        return _render_profile(db, is_rnd,
                               form_error='اسم المستخدم يجب أن يكون حرفين على الأقل')

    existing = db.execute(
        'SELECT id FROM users WHERE username = ? AND id != ?',
        (username, session['user_id'])
    ).fetchone()
    if existing:
        return _render_profile(db, is_rnd,
                               form_error='اسم المستخدم مستخدم من حساب آخر')

    try:
        db.execute(
            'UPDATE users SET username = ?, email = ?, label = ?, phone = ? WHERE id = ?',
            (username, email, label, phone, session['user_id'])
        )
        role = session.get('role', '')
        if role == 'teacher':
            db.execute(
                'UPDATE teachers SET phone = ? WHERE user_id = ?',
                (phone, session['user_id'])
            )
        db.commit()
    except Exception:
        db.rollback()
        return _render_profile(db, is_rnd,
                               form_error='حدث خطأ أثناء تحديث الحساب')

    session['username'] = username
    session['label'] = label
    flash('تم تحديث معلومات الحساب', 'success')
    return redirect(url_for('profile.profile'))


def _handle_department_update(db):
    display_name = request.form.get('dept_display_name', '').strip()
    abbreviation = request.form.get('dept_abbreviation', '').strip()
    description = request.form.get('dept_description', '').strip()

    dept = _resolve_rnd_department(db)
    if not dept:
        flash('لم يتم العثور على قسم البحث والتطوير', 'error')
        return redirect(url_for('profile.profile'))

    try:
        db.execute(
            'UPDATE departments SET display_name = ?, abbreviation = ?, description = ? WHERE id = ?',
            (display_name, abbreviation, description, dept['id'])
        )
        db.commit()
    except Exception:
        db.rollback()
        return _render_profile(db, True,
                               form_error='حدث خطأ أثناء تحديث بيانات القسم')

    flash('تم تحديث بيانات القسم', 'success')
    return redirect(url_for('profile.profile'))


def _render_profile(db, is_rnd, form_error=None):
    user = db.execute(
        'SELECT u.*, d.name AS department_name FROM users u '
        'LEFT JOIN departments d ON u.department_id = d.id WHERE u.id = ?',
        (session['user_id'],)
    ).fetchone()
    user = dict(user) if user else {}

    teacher = db.execute(
        'SELECT t.*, s.name AS specialization_name FROM teachers t '
        'LEFT JOIN specializations s ON t.specialization_id = s.id '
        'WHERE t.user_id = ?',
        (session['user_id'],)
    ).fetchone()
    teacher = dict(teacher) if teacher else None

    department = None
    if is_rnd:
        department = _resolve_rnd_department(db)
        department = dict(department) if department else None

    responsibilities = _ROLE_RESPONSIBILITIES.get(
        session.get('role', ''), []
    )

    return render_template(
        'profile/settings.html',
        user=user,
        teacher=teacher,
        department=department,
        responsibilities=responsibilities,
        form_error=form_error,
        current_user=user,
    )
