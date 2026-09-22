"""Production server using Waitress (Windows-compatible WSGI).

Usage:
    python serve.py                          # defaults: 0.0.0.0:5000, 4 threads
    python serve.py --host 127.0.0.1 --port 8080 --threads 8
    set waitress.channels=2 && python serve.py

Environment knobs:
    WAITRESS_HOST, WAITRESS_PORT, WAITRESS_THREADS   server bind settings
    WAITRESS_URL_SCHEME                              'http' (default) or 'https'
                                                       when TLS is terminated by the
                                                       server itself or is fake-tested;
                                                       behind a TLS proxy leave 'http'
                                                       and set TRUST_PROXY_HEADERS=true
    TRUST_PROXY_HEADERS=true                         trust X-Forwarded-* from a
                                                       reverse proxy (needed so Secure
                                                       cookies and redirects work
                                                       behind HTTPS offload). Only set
                                                       when the app is NOT directly
                                                       internet-facing.
     TRUSTED_PROXY_IPS=1.2.3.4,10.0.0.0/8              comma-separated source IPs of the
                                                       fronting proxy(ies). REQUIRED
                                                       together with TRUST_PROXY_HEADERS;
                                                       without it proxy headers are
                                                       ignored (fail-safe).
"""

from __future__ import annotations

import argparse
import os

from waitress import serve

from core.wsgi_proxy import build_wsgi_chain
from flask_db import init_db, bootstrap_defaults
from app import create_app

# /     /     >---- نهيئ قاعدة البيانات والبيانات الأساسية
init_db()
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

# ─────────────────────────────────────────────

# /     /     >---- الدالة الرئيسية اللي تشغل سيرفر الإنتاج
def main():
    # /     /     >---- نقرأ المعاملات من السطر الأوامر
    parser = argparse.ArgumentParser(description='ROPEY production server')
    parser.add_argument('--host', default=os.environ.get('WAITRESS_HOST', '0.0.0.0'))
    parser.add_argument('--port', type=int, default=int(os.environ.get('WAITRESS_PORT', '5000')))
    parser.add_argument('--threads', type=int, default=int(os.environ.get('WAITRESS_THREADS', '4')))
    args = parser.parse_args()

    # /     /     >---- نوع البروتوكول (HTTP أو HTTPS)
    url_scheme = os.environ.get('WAITRESS_URL_SCHEME', 'http')
    print(f'Starting ROPEY on http://{args.host}:{args.port} ({args.threads} threads)')
    # /     /     >---- نشغّل السيرفر
    serve(
        app,
        host=args.host,
        port=args.port,
        threads=args.threads,
        url_scheme=url_scheme,
        ident='ROPEY',
    )

# ─────────────────────────────────────────────

# /     /     >---- نقطة الدخول
if __name__ == '__main__':
    main()
