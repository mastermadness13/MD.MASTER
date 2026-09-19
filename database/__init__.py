"""Database layer — SQLite access, schema, history, and repositories.

Flask-independent.  The Flask adapter lives at the project root in
``flask_db.py``; this package only requires the ``sqlite3`` stdlib.

Seeding (``bootstrap_defaults``) lives in ``scripts/seed.py`` and is
called via ``flask_db.bootstrap_defaults()``, not from this package.
"""

# /     /     >---- الحزمة الأساسية لقاعدة البيانات: الاتصال، المخطط، السجل، المستودعات

# ── استيراد الدوال الأساسية ─────────────────────────────────────
from database.connection import connect
from database.schema import ensure_schema
from database.history import add_history

__all__ = ['connect', 'ensure_schema', 'add_history']