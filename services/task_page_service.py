"""Resolve the page attached to the active administrative assignment.

The lookup row (``admin_assignment_types``) is the block the dean builds: its
name shows in the teacher dropdown, and ``page_key``/``page_access_mode`` say
which screen the holder lands on and whether they may write to it.  This module
is the single place that answers "what page is this person on right now, and
may they edit it?" so the route guard, the navigation and the templates all
agree instead of each re-deriving it.
"""

from __future__ import annotations

from core.constants.task_pages import (
    ACCESS_MODES,
    DEFAULT_ACCESS_MODE,
    MIN_VIEW_PERMISSIONS,
    TASK_PAGES,
    is_valid_page_key,
    normalise_access_mode,
)


def _db():
    """Late import: flask_db pulls in the app context."""
    from flask_db import get_db
    return get_db()


def _assignment_row_for_role(role: str):
    """The assignment row that granted *role*, if any.

    A role can appear on more than one label (the seeded aliases all share one
    ``internal_code``), so we prefer the active, protected, lowest-sort row and
    fall back to any row carrying the code.  Returning ``None`` is normal for
    roles that never came from an assignment (a plain teacher, the dean seed).
    """
    if not role:
        return None
    db = _db()
    return db.execute(
        '''SELECT id, name, page_key, page_access_mode
           FROM admin_assignment_types
           WHERE internal_code = ? AND is_protected_role = 1
           ORDER BY is_active DESC, sort_order, id
           LIMIT 1''',
        (role,),
    ).fetchone()


def active_page():
    """Return ``(page_key, access_mode, label)`` for the active role.

    ``page_key`` is ``None`` when the role has no attached page, which is the
    common case and simply means "no restriction, use the role dashboard".
    """
    from flask import session

    row = _assignment_row_for_role(session.get('role', ''))
    if row is None:
        return None, DEFAULT_ACCESS_MODE, ''
    page_key = row['page_key']
    if not is_valid_page_key(page_key):
        return None, DEFAULT_ACCESS_MODE, ''
    mode = normalise_access_mode(row['page_access_mode'])
    return page_key, mode, TASK_PAGES[page_key]['label']


def is_view_only() -> bool:
    """True when the holder may read the attached page but not write to it."""
    page_key, mode, _label = active_page()
    return page_key is not None and mode == 'view'


def attached_page_label() -> str:
    _page_key, _mode, label = active_page()
    return label


def restrict_permissions(permissions: set, page_key: str) -> set:
    """Drop the write permissions of *page_key* from *permissions*.

    A read-only assignment narrows exactly one page: the person keeps the view
    permission, the dashboard, their own timetable and their profile.  The
    baseline entries in ``MIN_VIEW_PERMISSIONS`` are re-added so a narrow
    assignment can never leave the holder unable to render the page at all.
    """
    page = TASK_PAGES.get(page_key)
    if page is None:
        return permissions
    kept = set(permissions) - set(page['write_permissions'])
    kept.add(page['view_permission'])
    kept.update(MIN_VIEW_PERMISSIONS)
    return kept


def effective_permissions(roles, department_id=None) -> set:
    """Permissions for *roles*, with a read-only assignment applied on top.

    This is the seam the rest of the app already uses: ``get_user_permissions``
    stays pure, and the read-only contract is layered on top of it in one
    place.
    """
    from security.authorization import get_user_permissions

    perms = get_user_permissions(roles, department_id)
    page_key, mode, _label = active_page()
    if page_key is not None and mode == 'view':
        perms = restrict_permissions(perms, page_key)
    return perms


__all__ = [
    'ACCESS_MODES',
    'active_page',
    'attached_page_label',
    'effective_permissions',
    'is_view_only',
    'restrict_permissions',
]
