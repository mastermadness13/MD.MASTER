from flask import Blueprint, session, request, render_template, redirect, url_for, flash, abort
from werkzeug.security import check_password_hash

from flask_db import get_db
from database.history import add_history
from security import csrf_required, login_required, permission_required
from security import current_user, validate_password
from services import user_service
bp = Blueprint('profile', __name__, url_prefix='/profile')

# /     /     >---- مسؤوليات كل دور تُعرض في صفحة الملف الشخصي
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


# /     /     >---- قسم البحث والتطوير الإداري أو لا شيء إن لم يوجد
def _resolve_rnd_department(db):
    """Return the R&D department row, or None if not found.

    Prefers the administrative department whose name/display_name identifies
    R&D so the profile panel never shows a different administrative department
    (e.g. the exams department) merely because it sorts first.
    """
    rows = db.execute(
        "SELECT * FROM departments WHERE type = 'administrative' "
        "AND deleted_at IS NULL ORDER BY name"
    ).fetchall()
    if not rows:
        return None
    for row in rows:
        hay = ' '.join(str(row[k] or '') for k in ('name', 'display_name'))
        if 'بحث' in hay or 'تطوير' in hay:
            return row
    return rows[0]


# /     /     >---- صفحة الملف الشخصي: تحديث الحساب أو بيانات قسم البحث والتطوير
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
            # Username and password administration is deliberately not part
            # of the self-service profile.  Faculty-affairs staff manage
            # those credentials through the administrative teacher flow.
            if any(request.form.get(name) is not None for name in (
                    'username', 'password', 'current_password',
                    'new_password', 'confirm_password')):
                abort(403)
            return _handle_account_update(db, is_rnd)
        elif form_type == 'department' and is_rnd:
            return _handle_department_update(db)
        elif form_type == 'security':
            abort(403)

        flash('طلب غير صالح', 'error')
        return redirect(url_for('profile.profile'))

    return _render_profile(db, is_rnd, can_edit_account=role == 'faculty_affairs')


# /     /     >---- تحديث بيانات الحساب (البريد/الاسم الظاهر/الهاتف)
# /     /     >---- اعتمادات الدخول واسم المستخدم تُدار حصراً من المكتب المختص
def _handle_account_update(db, is_rnd):
    username = db.execute(
        'SELECT username FROM users WHERE id = ?', (session['user_id'],)
    ).fetchone()['username']
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    label = request.form.get('label', '').strip()

    # /     /     >---- تحقق من اسم الدخول: مطلوب وطول كافٍ وعدم التكرار
    try:
        db.execute(
            'UPDATE users SET email = ?, label = ?, phone = ? WHERE id = ?',
            (email, label, phone, session['user_id'])
        )
        role = session.get('role', '')
        # /     /     >---- مزامنة الهاتف مع سجل الأستاذ إن كان الدور أستاذاً
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


# /     /     >---- تحديث بيانات قسم البحث والتطوير (يعرض/اختصار/وصف)
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


# /     /     >---- تغيير كلمة مرور الحساب من صفحة الملف الشخصي
def _handle_password_update(db):
    current = (request.form.get('current_password') or '').strip()
    new_pass = request.form.get('new_password') or ''
    confirm = request.form.get('confirm_password') or ''

    user = user_service.get_user_by_id(db, session['user_id'])
    error = None
    if not user or not check_password_hash(user['password'], current):
        error = 'كلمة المرور الحالية غير صحيحة'
    elif new_pass != confirm:
        error = 'كلمة المرور الجديدة وتأكيدها غير متطابقين'
    elif validate_password(new_pass):
        error = validate_password(new_pass)
    elif check_password_hash(user['password'], new_pass):
        error = 'كلمة المرور الجديدة يجب أن تختلف عن كلمة المرور الحالية'

    if error:
        flash(error, 'error')
        return redirect(url_for('profile.profile'))

    try:
        user_service.change_user_password(db, session['user_id'], new_pass)
        db.commit()
    except Exception:
        db.rollback()
        flash('حدث خطأ أثناء تغيير كلمة المرور', 'error')
        return redirect(url_for('profile.profile'))

    flash('تم تغيير كلمة المرور بنجاح', 'success')
    return redirect(url_for('profile.profile'))


# /     /     >---- تجهيز بيانات صفحة الملف: حساب + ملف أستاذ + قسم + مسؤوليات
def _render_profile(db, is_rnd, form_error=None, can_edit_account=False):
    user = db.execute(
        'SELECT u.*, d.name AS department_name FROM users u '
        'LEFT JOIN departments d ON u.department_id = d.id WHERE u.id = ?',
        (session['user_id'],)
    ).fetchone()
    user = dict(user) if user else {}

    teacher = db.execute(
        '''SELECT t.*, s.name AS specialization_name,
                  d.name AS department_name,
                  q.name_ar AS qualification_name,
                  r.name_ar AS rank_name,
                  cl.name_ar AS classification_name
           FROM teachers t
           LEFT JOIN specializations s ON t.specialization_id = s.id
           LEFT JOIN departments d ON t.department_id = d.id
           LEFT JOIN qualifications q ON t.qualification_id = q.id
           LEFT JOIN academic_ranks r ON t.rank_id = r.id
           LEFT JOIN classifications cl ON t.classification_id = cl.id
           WHERE t.user_id = ?''',
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
        can_edit_account=can_edit_account,
    )