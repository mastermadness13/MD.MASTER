"""Production server using Waitress (Windows-compatible WSGI).

Usage:
    python serve.py                          # defaults: 0.0.0.0:5000, 4 threads
    python serve.py --host 127.0.0.1 --port 8080 --threads 8
    set waitress.channels=2 && python serve.py
"""

from __future__ import annotations

import argparse
import os

from waitress import serve

from flask_db import init_db, bootstrap_defaults
from app import create_app

init_db()
bootstrap_defaults()
app = create_app()


def main():
    parser = argparse.ArgumentParser(description='ROPEY production server')
    parser.add_argument('--host', default=os.environ.get('WAITRESS_HOST', '0.0.0.0'))
    parser.add_argument('--port', type=int, default=int(os.environ.get('WAITRESS_PORT', '5000')))
    parser.add_argument('--threads', type=int, default=int(os.environ.get('WAITRESS_THREADS', '4')))
    args = parser.parse_args()

    print(f'Starting ROPEY on http://{args.host}:{args.port} ({args.threads} threads)')
    serve(
        app,
        host=args.host,
        port=args.port,
        threads=args.threads,
        url_scheme='http',
        ident='ROPEY',
    )


if __name__ == '__main__':
    main()
