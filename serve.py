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
"""

from __future__ import annotations

import argparse
import os

from waitress import serve
from werkzeug.middleware.proxy_fix import ProxyFix

from flask_db import init_db, bootstrap_defaults
from app import create_app

init_db()
bootstrap_defaults()
app = create_app()

if os.environ.get('TRUST_PROXY_HEADERS', '').strip().lower() in ('1', 'true', 'yes'):
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


def main():
    parser = argparse.ArgumentParser(description='ROPEY production server')
    parser.add_argument('--host', default=os.environ.get('WAITRESS_HOST', '0.0.0.0'))
    parser.add_argument('--port', type=int, default=int(os.environ.get('WAITRESS_PORT', '5000')))
    parser.add_argument('--threads', type=int, default=int(os.environ.get('WAITRESS_THREADS', '4')))
    args = parser.parse_args()

    url_scheme = os.environ.get('WAITRESS_URL_SCHEME', 'http')
    print(f'Starting ROPEY on http://{args.host}:{args.port} ({args.threads} threads)')
    serve(
        app,
        host=args.host,
        port=args.port,
        threads=args.threads,
        url_scheme=url_scheme,
        ident='ROPEY',
    )


if __name__ == '__main__':
    main()
