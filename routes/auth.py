import os
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, session, redirect, url_for, request, render_template, flash, jsonify, get_flashed_messages
from werkzeug.security import generate_password_hash, check_password_hash

from flask_db import get_db
from database.history import add_history
from core.auth_limits import (
    is_forgot_blocked,
    is_login_blocked,
    is_reset_blocked,
    record_forgot,
    record_login_failure,
    record_reset,
    reset_login,
)
from security import csrf_required, login_required, validate_password
from security import current_user, generate_csrf_token
from services import user_service
from services import notification_service
from services import email_service

bp = Blueprint('auth', __name__)


def _reset_link_fallback_enabled() -> bool:
    """Allow the reset URL to be rendered in dev/test only (CWE-200).

    In production the URL is never disclosed in the response body; the account
    holder must receive it by email.
    """
    return os.environ.get('RESET_LINK_FALLBACK', '').strip().lower() in ('1', 'true', 'yes', 'on')


# /     /     >---- تسجيل الدخول: حد المحاولات + توثيق + توجيه حسب الدور الهابط
@bp.route('/login', methods=['GET', 'POST'])
@csrf_required
def login():
    if request.method == 'POST':
        client_ip = request.remote_addr
        username = request.form.get('username', '').strip()
        if is_login_blocked(client_ip, username):
            return render_template('auth/login.html', username=username,
                                   auth_warning='تم تجاوز الحد المسموح لمحاولات الدخول، يرجى المحاولة لاحقاً')
        password = request.form.get('password', '')
        remember = request.form.get('remember')
        db = get_db()
        success, user = user_service.authenticate(db, username, password, remember, session)
        if success:
            reset_login(client_ip, username)
            session['welcome_user'] = user['username']
            # Landing role is the highest-priority granted role, resolved at
            # authenticate time into session['role'] (multi-role model).
            # /     /     >---- الدور الهابط يُحدَّد وقت التوثيق داخل الجلسة
            landing_role = session.get('role', '')
            if landing_role == 'exam':
                session['landing_endpoint'] = 'exams.exams'
                return redirect(url_for('exams.exams'))
            if landing_role == 'faculty_affairs':
                session['landing_endpoint'] = 'teachers.teachers_list'
                return redirect(url_for('teachers.teachers_list'))
            session['landing_endpoint'] = 'dashboard.dashboard'
            return redirect(url_for('dashboard.dashboard'))
        record_login_failure(client_ip, username)
        return render_template('auth/login.html', username=username, form_error='اسم المستخدم أو كلمة المرور غير صحيحة')
    return render_template('auth/login.html')


@bp.route('/logout')
@login_required
def logout():
    session.clear()
    flash('تم تسجيل الخروج', 'success')
    return redirect(url_for('auth.login'))


# /     /     >---- نسيت كلمة المرور: إنشاء رمز إعادة تعيين وإرسال بالبريد (أو عرض الرابط للتطوير فقط)
@bp.route('/forgot-password', methods=['GET', 'POST'])
@csrf_required
def forgot_password():
    if request.method == 'POST':
        client_ip = request.remote_addr or 'unknown'
        username = request.form.get('username', '').strip()
        # /     /     >---- CWE-307: حد محاولات الاستعادة حسب IP واسم المستخدم
        if is_forgot_blocked(client_ip, username):
            return render_template(
                'auth/forgot_password.html',
                auth_warning='تم تجاوز الحد الأقصى لمحاولات الاستعادة، يرجى المحاولة لاحقاً',
            )
        record_forgot(client_ip, username)

        db = get_db()
        result = user_service.create_password_reset(db, username)
        if result:
            token, email = result
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            email_sent = bool(email) and email_service.send_reset_email(email, reset_url)
            # /     /     >---- CWE-200: الرابط لا يُعرض إلا في وضع التطوير/الاختبار
            if not email_sent and _reset_link_fallback_enabled():
                return render_template('auth/forgot_password.html',
                                       reset_url=reset_url, token=token)
        # /     /     >---- CWE-204: استجابة موحّدة للحساب الموجود وغير الموجود
        # /     /     >---- لا نكشف ما إذا أُرسل البريد فعلاً ولا ما إذا كان الحساب موجوداً
        flash('إذا كان الحساب موجوداً، سيتم إرسال رابط إعادة التعيين إلى بريدك الإلكتروني', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot_password.html')


# /     /     >---- إعادة تعيين كلمة المرور بالرمز مع فحص الصلاحية والتحقق من التطابق
@bp.route('/reset-password/<token>', methods=['GET', 'POST'])
@csrf_required
def reset_password(token):
    if request.method == 'POST':
        client_ip = request.remote_addr or 'unknown'
        # /     /     >---- CWE-307: حد محاولات إعادة التعيين حسب IP وبحسب الرمز
        if is_reset_blocked(client_ip, token):
            flash('تم تجاوز الحد الأقصى لمحاولات إعادة التعيين، يرجى المحاولة لاحقاً', 'warning')
            return redirect(url_for('auth.login'))
        record_reset(client_ip, token)

    db = get_db()
    row = user_service.validate_reset_token(db, token)
    if not row:
        flash('رابط إعادة التعيين غير صالح أو منتهي الصلاحية', 'error')
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm-password', '')
        error = None
        if password != confirm:
            error = 'كلمة المرور غير متطابقة'
        else:
            error = validate_password(password)
            # /     /     >---- CWE-620: منع إعادة استخدام كلمة المرور الحالية
            if error is None:
                user = user_service.get_user_by_id(db, row['user_id'])
                if user and check_password_hash(user['password'], password):
                    error = 'كلمة المرور الجديدة يجب أن تختلف عن كلمة المرور الحالية'
        if error:
            return render_template('auth/reset_password.html', token=token,
                                  form_error=error)
        user_service.reset_password(db, row, password)
        flash('تم تغيير كلمة المرور بنجاح', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/reset_password.html', token=token)


# /     /     >---- تغيير كلمة المرور من داخل الجلسة (JSON أو نموذج HTML)
@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
@csrf_required
def change_password():
    if request.method == 'POST':
        payload = request.get_json(silent=True) or request.form
        is_json = request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        current = (payload.get('current_password') or '').strip()
        new_pass = payload.get('new_password') or ''
        confirm = payload.get('confirm_password') or ''

        db = get_db()
        user = user_service.get_user_by_id(db, session['user_id'])

        # /     /     >---- سلسلة التحقق: الحالية + التطابق + القواعد + عدم التكرار
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
            if is_json:
                return jsonify({'ok': False, 'message': error}), 400
            return render_template('auth/change_password.html', user=current_user(),
                                  form_error=error)

        user_service.change_user_password(db, session['user_id'], new_pass)
        if is_json:
            return jsonify({'ok': True, 'message': 'تم تغيير كلمة المرور بنجاح'})
        return render_template('auth/change_password.html', user=current_user(),
                              success=True)
    return render_template('auth/change_password.html', user=current_user())