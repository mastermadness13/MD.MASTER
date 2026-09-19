import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

from flask import (
    Flask, session, redirect, url_for, render_template, request, make_response, jsonify, flash
)
from jinja2 import FileSystemLoader

from config import Config
from flask_db import get_db, close_db, init_app as db_init_app

from security import generate_csrf_token
from security import current_user, inject_navigation
from utils.format import semester_label, teacher_label, duration_label, format_time12
from utils.format import submission_status_label, submission_status_color
from utils.format import academic_title_prefix, teacher_display_name
from utils.redirects import redirect_back

# /     /     >---- تسجيل الأخطاء والرسوم
logger = logging.getLogger(__name__)


# /     /     >---- دالة إعداد اللوقنق (تسجل الأخطاء في ملف وتشوفها في الترمينال)
def _setup_logging(app):
    """Configure rotating file + stderr logging."""
    # /     /     >---- نصنع مجلد اللوقس إذا ما كان موجود
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'ropey.log')

    # /     /     >---- تنسيق الرسائل
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')

    # /     /     >---- ملف اللوقق بالتدوير (5 ميجا كحد أقصى، 5 نسخ احتياطية)
    file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.WARNING)

    # /     /     >---- شاشة الترمينال للرسوم المهمة
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.INFO)

    # /     /     >---- في ويندوز، الترمينال ما يدعم العربي، نجبره على UTF-8
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

    # /     /     >---- نضبط مستوى التسجيل الرئيسي
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    # /     /     >---- نخفي رسوم المكتبات الزايدة
    logging.getLogger('waitress').setLevel(logging.INFO)
    logging.getLogger('urllib3').setLevel(logging.WARNING)

# ── استيراد كل البلوبرنتات (المسارات الفرعية) ─────────────────────
from routes.auth import bp as auth_bp
from routes.dashboard import bp as dashboard_bp
from routes.profile import bp as profile_bp
from routes.departments import bp as departments_bp
from routes.teachers import bp as teachers_bp
from routes.classrooms import bp as classrooms_bp
from routes.courses import bp as courses_bp
from routes.timetable import bp as timetable_bp
from routes.exams import bp as exams_bp
from routes.history import bp as history_bp
from routes.teacher_pages import bp as teacher_pages_bp
from routes.hod_pages import bp as hod_pages_bp
from routes.spa import bp as spa_bp
from routes.print_routes import bp as print_routes_bp
from routes.uploads import bp as uploads_bp
from routes.misc import bp as misc_bp
from routes.classroom_requests import bp as classroom_requests_bp
from routes.html_to_pdf import bp as html_to_pdf_bp
from routes.public_library import bp as public_library_bp
from routes.public import bp as public_bp
from routes.public_site import bp as public_site_bp
from routes.faculty_performance import bp as faculty_performance_bp
from api import register_api


# /     /     >---- الدالة الرئيسية اللي تصنع التطبيق وتهيئ كل شي
def create_app():
    # /     /     >---- نصنع كائن Flask
    app = Flask(__name__)
    app.jinja_loader = FileSystemLoader(os.path.join(app.root_path, 'templates'))
    app.config.from_object(Config)
    # /     /     >---- نتأكد مجلد الرفع موجود
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # /     /     >---- نهيئ قاعدة البيانات واللوقنق
    db_init_app(app)
    _setup_logging(app)

    # /     /     >---- نغلق قاعدة البيانات بعد كل طلب
    @app.teardown_appcontext
    def teardown(exception):
        close_db(exception)

    # /     /     >---- نضيف الدوال المساعدة للقوالب (Jinja2)
    app.jinja_env.globals['csrf_token'] = generate_csrf_token
    app.jinja_env.globals['now'] = datetime.now
    app.jinja_env.globals['app_version'] = lambda: app.config.get('APP_VERSION', '0')
    app.jinja_env.globals['semester_label'] = semester_label
    app.jinja_env.globals['teacher_label'] = teacher_label
    app.jinja_env.globals['duration_label'] = duration_label
    app.jinja_env.globals['format_time12'] = format_time12
    app.jinja_env.globals['academic_title_prefix'] = academic_title_prefix
    app.jinja_env.globals['teacher_display_name'] = teacher_display_name
    app.jinja_env.globals['submission_status_label'] = submission_status_label
    app.jinja_env.globals['submission_status_color'] = submission_status_color
    app.context_processor(inject_navigation)

    # /     /     >---- نضيف بيانات المستخدم المرحّب به في كل صفح
    @app.context_processor
    def inject_welcome():
        return {'welcome_user': session.pop('welcome_user', None)}

    # /     /     >---- نضيف حد الرفع الأقصى في القوالب
    @app.context_processor
    def inject_upload_limit():
        mb = (app.config.get('MAX_CONTENT_LENGTH') or 0) // (1024 * 1024)
        return {'max_upload_mb': mb}

    # ── تسجيل البلوبرنتات ──────────────────────────────────────
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(departments_bp)
    app.register_blueprint(teachers_bp)
    app.register_blueprint(classrooms_bp)
    app.register_blueprint(courses_bp)
    app.register_blueprint(timetable_bp)
    app.register_blueprint(exams_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(teacher_pages_bp)
    app.register_blueprint(hod_pages_bp)
    app.register_blueprint(spa_bp)
    app.register_blueprint(print_routes_bp)
    app.register_blueprint(uploads_bp)
    app.register_blueprint(misc_bp)
    app.register_blueprint(classroom_requests_bp)
    app.register_blueprint(html_to_pdf_bp)
    app.register_blueprint(public_library_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(public_site_bp)
    app.register_blueprint(faculty_performance_bp)
    register_api(app)

    # ── فحص صحة التطبيق ─────────────────────────────────────────
    @app.route('/health')
    def health_check():
        try:
            # /     /     >---- نجرب نوصل لقاعدة البيانات
            db = get_db()
            db.execute('SELECT 1')
            return jsonify({'ok': True, 'status': 'healthy'}), 200
        except Exception:
            return jsonify({'ok': False, 'status': 'unhealthy'}), 503

    # ── معالجات الأخطاء ───────────────────────────────────────────
    from core.exceptions import AppError

    @app.errorhandler(AppError)
    def handle_app_error(e):
        # /     /     >---- إذا الطلب من AJAX نرجع JSON، وإلا نرجع صفحة
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'ok': False, 'message': e.message}), e.status_code
        flash(e.message, 'error')
        return redirect_back()

    @app.errorhandler(404)
    def not_found(e):
        # /     /     >---- صفحة 404 - الصفحة غير موجودة
        return render_template('errors/404.html'), 404

    @app.errorhandler(413)
    def file_too_large(e):
        # /     /     >---- الملف أكبر من الحد المسموح
        msg = f'حجم الملف أكبر من الحد المسموح ({app.config.get("MAX_CONTENT_LENGTH", 0) // (1024 * 1024)} ميجابايت)'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'ok': False, 'message': msg}), 413
        flash(msg, 'error')
        return redirect_back()

    @app.errorhandler(429)
    def too_many_requests(e):
        # /     /     >---- تجاوز الحد المسموح من الطلبات
        msg = 'تم تجاوز الحد المسموح من الطلبات، يرجى المحاولة لاحقاً'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'ok': False, 'message': msg}), 429
        flash(msg, 'error')
        return redirect_back()

    @app.errorhandler(500)
    def server_error(e):
        # /     /     >---- خطأ داخلي في السيرفر
        logger.exception('Internal server error')
        if 'user_id' in session:
            return render_template('errors/500.html', user=current_user()), 500
        return redirect(url_for('auth.login'))

    # ── الهيدرز الأمنية والكاش ──────────────────────────────────
    @app.after_request
    def add_security_headers(response):
        # /     /     >---- هيدرز الحماية من الثغرات الأمنية
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'

        # /     /     >---- سياسة أمان المحتوى (CSP)
        csp_parts = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://cdn.jsdelivr.net",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdn.tailwindcss.com https://cdnjs.cloudflare.com",
            "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
            "img-src 'self' data: blob:",
            "connect-src 'self'",
            "frame-ancestors 'self'",
        ]
        response.headers['Content-Security-Policy'] = '; '.join(csp_parts)

        # /     /     >---- إعداد الكاش حسب نوع المسار
        path = request.path
        if path.startswith('/static/'):
            # /     /     >---- الملفات الثابتة تكاش لمدة سنة
            response.cache_control.public = True
            response.cache_control.max_age = 31536000
        elif path.startswith('/uploads/'):
            # /     /     >---- الملفات المرفوعة تكاش لمدة ساعة
            response.cache_control.private = True
            response.cache_control.max_age = 3600

        return response

    return app

# ─────────────────────────────────────────────

# /     /     >---- نقطة الدخول الرئيسية للتشغيل المباشر
if __name__ == '__main__':
    import sys
    if 'init-db' in sys.argv:
        # /     /     >---- إذا كتبنا flask init-db نهيئ القاعدة فقط
        from flask_db import init_db, bootstrap_defaults as _seed
        init_db()
        _seed()
        print('Database initialized and seeded.')
    else:
        # /     /     >---- نشغّل السيرفر بشكل طبيعي
        from flask_db import init_db, bootstrap_defaults as _seed
        init_db()
        _seed()
        app = create_app()
        # /     /     >---- وضع التصحيح اختياري (FLASK_DEBUG=1) — إعادة التشغيل التلقائية
        # /     /     >---- تمسح عدادات تحديد معدل المحاولات من الذاكرة
        debug = os.environ.get('FLASK_DEBUG', '').strip().lower() in ('1', 'true', 'yes', 'on')
        app.run(debug=debug, host='127.0.0.1', port=5000)
