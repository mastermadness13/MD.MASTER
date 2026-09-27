"""Production WSGI entrypoint.

Usage:
    python serve.py                          (recommended — Waitress)
    waitress-serve --host=0.0.0.0 --port=5000 wsgi:app  (alternative)
    gunicorn wsgi:app                        (alternative, on Linux hosts)
    passenger / panel "startup file" = wsgi.py   (shared hosting behind nginx)

Environment knobs (same names as serve.py, so both entrypoints behave alike):
    TRUST_PROXY_HEADERS=true    trust X-Forwarded-* from the fronting proxy
                                (needs TRUSTED_PROXY_IPS). Only when the app
                                is NOT directly internet-facing.
     TRUSTED_PROXY_IPS=1.2.3.4  comma-separated source IPs of the proxy(ies).
                                Without it proxy headers are ignored (fail-safe).
"""

import os

# /     /     >---- نستورد الدوال اللي نحتاجها
from flask_db import init_db, bootstrap_defaults
from core.wsgi_proxy import build_wsgi_chain
from app import create_app

# /     /     >---- نهيئ الجداول مرة وحدة عند بدء التشغيل (آمن يتكرر)
init_db()

# /     /     >---- نزرع البيانات الأساسية إذا القاعدة جديدة
bootstrap_defaults()

# /     /     >---- نصنع التطبيق
app = create_app()

# /     /     >---- إذا السيرفر وراء بروكسي (مثل Nginx)، نثق بالهيدرز
# /     /     >---- فقط من مصدر موثوق (TRUSTED_PROXY_IPS) — البقية تُقدَّم دون تعديل
trust_proxy = os.environ.get('TRUST_PROXY_HEADERS', '').strip().lower() in ('1', 'true', 'yes')
app.wsgi_app = build_wsgi_chain(
    app.wsgi_app,
    trust_proxy_headers=trust_proxy,
    trusted_proxy_ips=os.environ.get('TRUSTED_PROXY_IPS', ''),
)
