"""Database-layer constants.

Values that describe the persistence layer (soft-delete tables, default
schema paths) live here instead of ``core/`` because they are SQLite-specific.
"""

from __future__ import annotations

# ── جداول الحذف الناعم ────────────────────────────────────────────────────────
# /     /     >---- الجداول اللي فيها عمود deleted_at؛ والفلترة تكون deleted_at IS NULL
SOFT_DELETE_TABLES = frozenset({
    'teachers', 'rooms', 'courses', 'departments', 'timetable',
})