"""Database-layer constants.

Values that describe the persistence layer (soft-delete tables, default
schema paths) live here instead of ``core/`` because they are SQLite-specific.
"""

from __future__ import annotations

# ── Soft-delete tables ────────────────────────────────────────────────────────
# Tables carrying a `deleted_at` column; `deleted_at IS NULL` filters them.
SOFT_DELETE_TABLES = frozenset({
    'teachers', 'rooms', 'courses', 'departments', 'timetable',
})
