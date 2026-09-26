import os
import secrets
from datetime import timedelta

from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

# /     /     >---- هذي الدالة تجيب سر التطبيق (SECRET_KEY) من ملف .secret_key
# /     /     >---- أو من المتغيرات البيئية، وإذا ما لقاتهم تصنع واحد جديد
def _load_secret_key(base_dir: str) -> str:
    """Resolve the Flask secret key without any predictable fallback.

    Priority: ``SECRET_KEY`` env var → persisted ``.secret_key`` file → or
    generate a new random key and persist it (so sessions survive restarts).
    The file is git-ignored; a hardcoded default would allow session forgery.
    """
    # /     /     >---- نشوف إذا فيه مفتاح في المتغيرات البيئية
    env_key = os.environ.get('SECRET_KEY')
    if env_key:
        return env_key
    # /     /     >---- إذا لا، نشوف في ملف .secret_key
    key_file = os.path.join(base_dir, '.secret_key')
    if os.path.exists(key_file):
        value = open(key_file).read().strip()
        if value:
            return value
    # /     /     >---- إذا لا شي، نصنع مفتاح عشوائي ونحفظه في الملف
    value = secrets.token_hex(32)
    try:
        with open(key_file, 'w') as handle:
            handle.write(value)
    except OSError:
        pass
    return value

# ─────────────────────────────────────────────

# /     /     >---- كلاس الإعدادات الرئيسي للتطبيق، يحتوي على كل الإعدادات الأساسية
class Config:
    # /     /     >---- رقم إصدار التطبيق
    APP_VERSION = os.environ.get('APP_VERSION') or '2026.08.31.2'
    # /     /     >---- مفتاح السر للجلسات
    SECRET_KEY = _load_secret_key(basedir)
    # /     /     >---- مسار قاعدة البيانات
    DATABASE = os.environ.get('DATABASE') or os.path.join(basedir, 'database', 'data.db')
    # /     /     >---- مجلد الرفع
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or os.path.join(basedir, 'uploads')
    # /     /     >---- الحد الأقصى لحجم الملف المرفوع (16 ميجابايت)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    # /     /     >---- إعدادات الكوكيز الأمنية
    SESSION_COOKIE_HTTPONLY = True
    # /     /     >---- الكوكيز آمن بشكل افتراضي، يتحول لـ false فقط للتطوير المحلي
    SESSION_COOKIE_SECURE = os.environ.get(
        'SESSION_COOKIE_SECURE', 'true'
    ).strip().lower() in ('1', 'true', 'yes', 'on')
    SESSION_COOKIE_SAMESITE = 'Lax'
    # /     /     >---- مدة صلاحية الجلسة (7 أيام)
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # ── أساس رابط إعادة تعيين كلمة المرور ──────────────────────────
    # The reset link is a bearer credential, so its origin must come from a
    # configured base rather than the request's Host header. Empty means
    # "derive from the request" and logs a warning; set it in production.
    RESET_BASE_URL = (os.environ.get('RESET_BASE_URL') or '').strip().rstrip('/')

    # ── إعدادات البريد الإلكتروني ──────────────────────────────────
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or ''
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or ''
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'noreply@zuwaratc.edu.ly'
