import secrets
from datetime import datetime, timedelta

from flask import Blueprint, session, redirect, url_for, request, render_template, flash, get_flashed_messages
from werkzeug.security import generate_password_hash, check_password_hash

from flask_db import get_db
from database.history import add_history
from core.rate_limiter import RateLimiter
from security import csrf_required, login_required, validate_password
from security import current_user, generate_csrf_token
from services import user_service
from services import notification_service
from services import email_service

bp = Blueprint('auth', __name__)

_login_limiter = RateLimiter(max_requests=5, window_seconds=60)


@bp.route('/login', methods=['GET', 'POST'])
@csrf_required
def login():
    if request.method == 'POST':
        client_ip = request.remote_addr
        if _login_limiter.is_limited(client_ip):
            return render_template('auth/login.html', form_error='تم تجاوز الحد المسموح لمحاولات الدخول، يرجى المحاولة لاحقاً')
        _login_limiter.record(client_ip)
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember')
        db = get_db()
        success, user = user_service.authenticate(db, username, password, remember, session)
        if success:
            _login_limiter.reset(client_ip)
            session['welcome_user'] = user['username']
            # Landing role is the highest-priority granted role, resolved at
            # authenticate time into session['role'] (multi-role model).
            landing_role = session.get('role', '')
            if landing_role == 'exam':
                session['landing_endpoint'] = 'exams.exams'
                return redirect(url_for('exams.exams'))
            if landing_role == 'faculty_affairs':
                session['landing_endpoint'] = 'teachers.teachers_list'
                return redirect(url_for('teachers.teachers_list'))
            session['landing_endpoint'] = 'dashboard.dashboard'
            return redirect(url_for('dashboard.dashboard'))
        return render_template('auth/login.html', username=username, form_error='اسم المستخدم أو كلمة المرور غير صحيحة')
    return render_template('auth/login.html')


@bp.route('/logout')
@login_required
def logout():
    session.clear()
    flash('تم تسجيل الخروج', 'success')
    return redirect(url_for('auth.login'))


@bp.route('/forgot-password', methods=['GET', 'POST'])
@csrf_required
def forgot_password():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        db = get_db()
        result = user_service.create_password_reset(db, username)
        if result:
            token, email = result
            if email:
                reset_url = url_for('auth.reset_password', token=token, _external=True)
                email_sent = email_service.send_reset_email(email, reset_url)
                if email_sent:
                    flash('تم إرسال رابط إعادة تعيين كلمة المرور إلى بريدك الإلكتروني', 'success')
                    return redirect(url_for('auth.login'))
                else:
                    flash('حدث خطأ أثناء إرسال البريد الإلكتروني، يرجى المحاولة لاحقاً', 'error')
            else:
                flash('لم يتم العثور على بريد إلكتروني مرتبط بهذا الحساب', 'error')
        else:
            flash('لم يتم العثور على حساب بهذا الاسم', 'error')
        return render_template('auth/forgot_password.html')
    return render_template('auth/forgot_password.html')


@bp.route('/reset-password/<token>', methods=['GET', 'POST'])
@csrf_required
def reset_password(token):
    db = get_db()
    row = user_service.validate_reset_token(db, token)
    if not row:
        flash('رابط إعادة التعيين غير صالح أو منتهي الصلاحية', 'error')
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm-password', '')
        if password != confirm:
            return render_template('auth/reset_password.html', token=token,
                                  form_error='كلمة المرور غير متطابقة')
        elif validate_password(password):
            return render_template('auth/reset_password.html', token=token,
                                  form_error=validate_password(password))
        user_service.reset_password(db, row, password)
        flash('تم تغيير كلمة المرور بنجاح', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/reset_password.html', token=token)


@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
@csrf_required
def change_password():
    if request.method == 'POST':
        current = request.form.get('current_password', '')
        new_pass = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        db = get_db()
        user = user_service.get_user_by_id(db, session['user_id'])
        if not check_password_hash(user['password'], current):
            return render_template('auth/change_password.html', user=current_user(),
                                  form_error='كلمة المرور الحالية غير صحيحة')
        elif new_pass != confirm:
            return render_template('auth/change_password.html', user=current_user(),
                                  form_error='كلمة المرور الجديدة وتأكيدها غير متطابقين')
        elif validate_password(new_pass):
            return render_template('auth/change_password.html', user=current_user(),
                                  form_error=validate_password(new_pass))
        user_service.change_user_password(db, session['user_id'], new_pass)
        flash('تم تغيير كلمة المرور بنجاح', 'success')
        return redirect(url_for('dashboard.dashboard'))
    return render_template('auth/change_password.html', user=current_user())
