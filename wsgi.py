"""Production WSGI entrypoint.

Usage:
    python serve.py                          (recommended — Waitress)
    waitress-serve --host=0.0.0.0 --port=5000 wsgi:app  (alternative)
"""
from flask_db import init_db, bootstrap_defaults
from app import create_app

# Run schema migration once at startup (idempotent, safe to repeat)
init_db()

# Seed defaults on fresh databases
bootstrap_defaults()

app = create_app()
