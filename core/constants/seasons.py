"""Academic season helpers for grouping content by academic term.

The Libyan academic year is split into:
  * خريفي  (fall)   – September .. January
  * ربيعي  (spring) – February .. June/July

Soft-deleted entities carry the UTC timestamp of their removal (``deleted_at``),
while timetables/exams belong to an academic term. Both are grouped with the
same ``year → season`` presentation.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

SEASON_FALL = "\u062e\u0631\u064a\u0641\u064a"    # خريفي
SEASON_SPRING = "\u0631\u0628\u064a\u0639\u064a"  # ربيعي

_FALL_MONTHS = {9, 10, 11, 12}

_FALL_CODE_PREFIX = "fall_"
_SPRING_CODE_PREFIX = "spring_"

# Legacy timetable snapshots imported from the old system carry synthetic
# ``migrated_<department_id>_<year_level>`` codes: one per department/stage
# combo rather than per real academic term.  They are merged into a single
# pseudo-period everywhere in the UI so teachers see one history entry
# instead of a fragmented list.
LEGACY_PERIOD_CODE = "__legacy__"
_LEGACY_MIGRATED_PREFIX = "migrated"
LEGACY_PERIOD_LABEL = (
    "\u0627\u0644\u0623\u0631\u0634\u064a\u0641 \u0627\u0644\u0633\u0627\u0628\u0642 "
    "(\u0645\u0633\u062a\u0648\u0631\u062f)"          # \u0627\u0644\u0641\u0635\u0644 \u0627\u0644\u0633\u0627\u0628\u0642 (\u0645\u0633\u062a\u0648\u0631\u062f)
)


def is_legacy_period_code(code: Any) -> bool:
    """True for synthetic ``migrated_*`` snapshot codes."""
    if not code:
        return False
    return str(code).strip().lower().startswith(_LEGACY_MIGRATED_PREFIX)


def normalize_period_code(code: Any) -> str:
    """Collapse all ``migrated_*`` variants into the single legacy code."""
    if is_legacy_period_code(code):
        return LEGACY_PERIOD_CODE
    return (code or "").strip() if code else ""


def _parse_date(value: Any):
    """Parse the leading YYYY-MM-DD out of a datetime-ish value."""
    if value is None:
        return None
    s = str(value)[:10]
    parts = s.split("-")
    if len(parts) < 3:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def season_label(value: Any) -> str:
    """Return e.g. 'خريفي 2026' for a date/datetime string."""
    parsed = _parse_date(value)
    if not parsed:
        return ""
    year, month = parsed
    if month == 1:
        return f"{SEASON_FALL} {year - 1}"
    if month in _FALL_MONTHS:
        return f"{SEASON_FALL} {year}"
    return f"{SEASON_SPRING} {year}"


def period_label(code: Any) -> str:
    """Return e.g. '\u062e\u0631\u064a\u0641\u064a 2026' for a timetable_versions semester_code.

    Understands ``fall_YYYY`` / ``spring_YYYY`` codes.  Legacy or migrated
    codes have no reliable year/season mapping, so an empty string is
    returned and callers fall back to their DB-driven display names.
    """
    if not code:
        return ""
    s = str(code).strip().lower()
    if s.startswith(_FALL_CODE_PREFIX):
        year = s[len(_FALL_CODE_PREFIX):]
        return f"{SEASON_FALL} {year}" if year.isdigit() else ""
    if s.startswith(_SPRING_CODE_PREFIX):
        year = s[len(_SPRING_CODE_PREFIX):]
        return f"{SEASON_SPRING} {year}" if year.isdigit() else ""
    return ""


def period_sort_key(code: Any) -> Tuple[int, int]:
    """Sort key for semester codes; use with ``reverse=True``.

    Newest-first order: within the same calendar year the fall term spans a
    later window (Sep..Jan) than the spring term, so it sorts first.
    Unknown/legacy codes sink to the end of the list.
    """
    if not code:
        return (-1, -1)
    s = str(code).strip().lower()
    if s.startswith(_FALL_CODE_PREFIX):
        year = s[len(_FALL_CODE_PREFIX):]
        if year.isdigit():
            return (int(year), 2)
    if s.startswith(_SPRING_CODE_PREFIX):
        year = s[len(_SPRING_CODE_PREFIX):]
        if year.isdigit():
            return (int(year), 1)
    return (-1, -1)


def group_by_season(rows: List[Dict[str, Any]],
                    date_key: str = "deleted_at") -> List[Tuple[str, List[Dict[str, Any]]]]:
    """Group page rows into consecutive ``(label, rows)`` chunks.

    Rows must already be sorted newest-first by their deletion date so that
    each chunk renders as one contiguous year/season block.
    """
    groups: List[Tuple[str, List[Dict[str, Any]]]] = []
    index: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        label = season_label(row.get(date_key)) if isinstance(row, dict) else ""
        if not label:
            label = "-"
        if label not in index:
            index[label] = []
            groups.append((label, index[label]))
        index[label].append(row)
    return groups
