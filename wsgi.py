"""Production WSGI entrypoint.

Usage:
    python serve.py                          (recommended — Waitress)
    waitress-serve --host=0.0.0.0 --port=5000 wsgi:app  (alternative)
"""

# /     /     >---- نستورد الدوال اللي نحتاجها
from flask_db import init_db, bootstrap_defaults
from app import create_app

# /     /     >---- نهيئ الجداول مرة وحدة عند بدء التشغيل (آمن يتكرر)
init_db()

# /     /     >---- نزرع البيانات الأساسية إذا القاعدة جديدة
bootstrap_defaults()

# /     /     >---- نصنع التطبيق
app = create_app()
