import os
from datetime import timedelta

from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))


class Config:
    APP_VERSION = os.environ.get('APP_VERSION') or '2026.08.31.2'
    SECRET_KEY = os.environ.get('SECRET_KEY') or (
        open(os.path.join(basedir, '.secret_key')).read().strip()
        if os.path.exists(os.path.join(basedir, '.secret_key'))
        else 'ropely-secret-key-change-in-production'
    )
    DATABASE = os.environ.get('DATABASE') or os.path.join(basedir, 'database', 'data.db')
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or os.path.join(basedir, 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # Mail (SMTP) settings
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or ''
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or ''
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'noreply@zuwaratc.edu.ly'
