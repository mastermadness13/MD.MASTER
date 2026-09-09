import os
import secrets
from datetime import timedelta

from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))


def _load_secret_key(base_dir: str) -> str:
    """Resolve the Flask secret key without any predictable fallback.

    Priority: ``SECRET_KEY`` env var → persisted ``.secret_key`` file → or
    generate a new random key and persist it (so sessions survive restarts).
    The file is git-ignored; a hardcoded default would allow session forgery.
    """
    env_key = os.environ.get('SECRET_KEY')
    if env_key:
        return env_key
    key_file = os.path.join(base_dir, '.secret_key')
    if os.path.exists(key_file):
        value = open(key_file).read().strip()
        if value:
            return value
    value = secrets.token_hex(32)
    try:
        with open(key_file, 'w') as handle:
            handle.write(value)
    except OSError:
        pass
    return value


class Config:
    APP_VERSION = os.environ.get('APP_VERSION') or '2026.08.31.2'
    SECRET_KEY = _load_secret_key(basedir)
    DATABASE = os.environ.get('DATABASE') or os.path.join(basedir, 'database', 'data.db')
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or os.path.join(basedir, 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    SESSION_COOKIE_HTTPONLY = True
    # Secure by default; set SESSION_COOKIE_SECURE=false only for plain-HTTP
    # local development (see .env.example).
    SESSION_COOKIE_SECURE = os.environ.get(
        'SESSION_COOKIE_SECURE', 'true'
    ).strip().lower() in ('1', 'true', 'yes', 'on')
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # Mail (SMTP) settings
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or ''
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or ''
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'noreply@zuwaratc.edu.ly'
