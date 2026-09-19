"""SQLite connection helpers.

A thin, Flask-free wrapper around the ``sqlite3`` stdlib that applies the
connection defaults the application relies on (row factory, UTF-8 text,
foreign keys, WAL journal mode).
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from utils.text import normalize_arabic_name

# ─────────────────────────────────────────────

# /     /     >---- نضبط الاتصال بالإعدادات المعيارية: الصفوف، المفاتيح الأجنبية...
def configure_connection(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Apply the standard connection pragmas and row factory in place."""
    # /     /     >---- النصوص كلها نصوص عادية
    conn.text_factory = str
    # /     /     >---- الصفوف ترجع ككائنات Row تقدر تتعامل معاهم كقواميس
    conn.row_factory = sqlite3.Row
    # /     /     >---- تفعيل المفاتيح الأجنبية
    conn.execute('PRAGMA foreign_keys = ON')
    # /     /     >---- وضع WAL: أأمن من الكراش ويسمح بالقراءة المتزامنة
    conn.execute('PRAGMA journal_mode = WAL')
    # /     /     >---- نستنى لحد 5 ثواني إذا القاعدة مقفولة
    conn.execute('PRAGMA busy_timeout = 5000')
    # /     /     >---- دالة SQL مخصصة: normalize_arabic(النص)
    conn.create_function('normalize_arabic', 1, lambda s: normalize_arabic_name(s))
    return conn

# ─────────────────────────────────────────────

# /     /     >---- نفتح اتصال مُجوّز بقاعدة SQLite في المسار المعطى
def connect(path: str) -> sqlite3.Connection:
    """Open a configured connection to the SQLite database at *path*."""
    conn = sqlite3.connect(path)
    conn.execute('PRAGMA encoding = "UTF-8"')
    return configure_connection(conn)

# ─────────────────────────────────────────────

# /     /     >---- نفس connect، بس إذا المسار فاضي نرجع None
def connect_or_none(path: Optional[str]) -> Optional[sqlite3.Connection]:
    """Like :func:`connect` but returns *None* for a falsy path."""
    if not path:
        return None
    return connect(path)