"""Flask adapter for the ``database`` package.

The ``database`` package itself is Flask-free.  This module is the thin glue
that binds it to a Flask application:

  • opens/closes a connection per request (``g``),
  • registers the ``flask init-db`` CLI command,
  • re-exports a few helpers so callers can keep a single import site.

Schema initialization (``ensure_schema``) is run once at startup in
``wsgi.py`` or ``app.py``'s ``__main__`` block — NOT lazily per-request.
"""

from __future__ import annotations

import os
import sqlite3

import click
from flask import g
from flask.cli import with_appcontext

from config import Config
from database.connection import connect
from database.history import add_history
from database.schema import ensure_schema

# ── تحميل سكربت الزراعة (seed.py) من مجلد scripts ──────────────
import sys as _sys
import importlib.util as _iu
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in _sys.path:
    _sys.path.insert(0, _project_root)
_seed_spec = _iu.spec_from_file_location(
    '_scripts_seed',
    os.path.join(_project_root, 'scripts', 'seed.py'),
)
_seed_mod = _iu.module_from_spec(_seed_spec)
_seed_spec.loader.exec_module(_seed_mod)
_bootstrap_defaults = _seed_mod.bootstrap_defaults

DATABASE = Config.DATABASE

# ─────────────────────────────────────────────

# /     /     >---- تجيب الاتصال بقاعدة البيانات للطلب الحالي
def get_db():
    """Return the per-request SQLite connection, creating it on first use."""
    # /     /     >---- نشوف إذا فيه اتصال محفوظ في الجلسة
    db = getattr(g, '_database', None)
    if db is None:
        # /     /     >---- ما فيه، نصنع واحد جديد
        db = g._database = connect(DATABASE)
    else:
        # /     /     >---- فيه اتصال، نتأكد شغال. إذا مقفل نفتح واحد جديد
        try:
            db.execute('SELECT 1')
        except sqlite3.ProgrammingError:
            db.close()
            db = g._database = connect(DATABASE)
    return db

# ─────────────────────────────────────────────

# /     /     >---- نغلق الاتصال بقاعدة البيانات في نهاية الطلب
def close_db(e: BaseException | None = None) -> None:
    """Close the per-request connection if one was opened."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# ─────────────────────────────────────────────

# /     /     >---- نزرع البيانات الأساسية في قاعدة البيانات
def bootstrap_defaults() -> None:
    """Seed default data into the configured database."""
    _bootstrap_defaults(DATABASE)

# ─────────────────────────────────────────────

# /     /     >---- نهيئ قاعدة البيانات من الصفر (الجدول + الهجرة)
def init_db() -> None:
    """Create a fresh schema from ``database/schema.sql`` and migrate."""
    conn = connect(DATABASE)
    # /     /     >---- نقرأ ملف SQL ونشغّله
    schema_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'database', 'schema.sql'
    )
    with open(schema_path, mode='r', encoding='utf-8') as f:
        conn.executescript(f.read())
    # /     /     >---- نطبق التغييرات إن وجدت
    ensure_schema(conn)
    conn.commit()
    conn.close()

# ─────────────────────────────────────────────

# /     /     >---- أمر سطر الأوامر: flask init-db
@click.command('init-db')
@click.option('--confirm', is_flag=True, default=False,
              help='Required to proceed. Prevents accidental data loss.')
@with_appcontext
def init_db_command(confirm):
    """Clear existing data, create new tables, and seed default data.

    WARNING: This destroys all existing data. Requires --confirm flag.
    """
    import sqlite3
    from config import Config
    db_path = Config.DATABASE
    # /     /     >---- نشوف كم مستخدم موجود في القاعدة
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute('SELECT COUNT(*) FROM users').fetchone()
        user_count = row[0] if row else 0
        conn.close()
    except Exception:
        user_count = 0

    # /     /     >---- إذا فيه مستخدمين وما كتبنا --confirm نوقف
    if user_count > 0 and not confirm:
        click.echo(
            f'ABORT: Database has {user_count} users. '
            'This command destroys all data.\n'
            'Re-run with --confirm if you truly want to reset:\n'
            '  flask init-db --confirm'
        )
        return

    # /     /     >---- إذا فيه مستخدمين، نسأله يأكد
    if user_count > 0:
        click.confirm(
            f'Database has {user_count} users. This will DESTROY all data. Continue?',
            abort=True
        )

    # /     /     >---- نهيئ القاعدة ونزرع البيانات
    init_db()
    click.echo('Initialized the database schema.')
    bootstrap_defaults()
    click.echo('Seeded default data.')

# ─────────────────────────────────────────────

# /     /     >---- نضمن أن مخطط قاعدة البيانات محدث حتى في قواعد البيانات القديمة
def ensure_database_schema() -> None:
    """Apply any pending SQLite schema migrations for an existing DB."""
    conn = connect(DATABASE)
    try:
        ensure_schema(conn)
        conn.commit()
    finally:
        conn.close()


# /     /     >---- نسجل الدوال مع تطبيق Flask
def init_app(app) -> None:
    """Register database functions with the Flask app."""
    ensure_database_schema()
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)

# ─────────────────────────────────────────────

__all__ = ['get_db', 'close_db', 'init_app', 'init_db', 'init_db_command',
           'bootstrap_defaults', 'ensure_schema', 'add_history']
