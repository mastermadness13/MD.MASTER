"""Authorization — role → permissions and the guard decorators.

The authenticated user is the single source of truth.  A user may hold
**several roles at once** (multi-role model via the ``user_roles`` table):
  Roles → effective Permissions → Navigation

``ROLE_PERMISSIONS`` (the role → permission map) and ``NAV_ITEMS`` live in
``core/constants``.  This module contains the pure logic that interprets
them, plus the Flask decorators that enforce it.

Backward compatibility: every public function still accepts a single role
string; passing a collection (list/set/tuple) of roles yields the union of
their permissions so a multi-role user sees the combined capability set.
"""

from __future__ import annotations

from functools import wraps

from flask import flash, redirect, session, url_for

from core.constants import NAV_ITEMS, ROLE_LABELS, ROLE_PERMISSIONS
from utils.redirects import redirect_back

# Fixed landing-role priority (highest first).  After login the user lands on
# their highest-priority granted role, and can switch among granted roles
# in-app.  An empty/unknown role is treated as 'teacher'.
ROLE_PRIORITY = [
    'super_admin',
    'research_development',
    'faculty_affairs',
    'exam',
    'head_of_department',
    'teacher',
]

ALL_ROLES_SET = frozenset(ROLE_PRIORITY)


def _normalize_roles(role) -> list:
    """Coerce a role argument into a list of role strings.

    Accepts a single string, or a collection of strings.  Filters out unknown
    roles so stale session data cannot grant arbitrary permissions.
    """
    if role is None:
        return []
    if isinstance(role, str):
        roles = [role]
    else:
        roles = list(role)
    return [r for r in roles if r in ALL_ROLES_SET]


def get_granted_roles() -> list:
    """Return the authenticated user's full role set for this session.

    Prefers ``session['roles']`` (the multi-role list set at login); falls
    back to the single ``session['role']`` for legacy/partial sessions so an
    already-logged-in user is never locked out.
    """
    roles = session.get('roles')
    if isinstance(roles, list) and roles:
        return [r for r in roles if r in ALL_ROLES_SET] or [str(session.get('role', 'teacher')) or 'teacher']
    return [str(session.get('role', 'teacher')) or 'teacher']


def get_active_roles() -> list:
    """Return the role(s) the user is *currently operating under*.

    Unlike ``get_granted_roles()`` this follows the in-app role switcher:
    ``session['role']`` is the active role and everything the user sees right
    now (nav, permissions) is scoped to it.  Falls back to the full granted
    set only when the active role is unknown so nobody is locked out.
    """
    active = session.get('role')
    roles = _normalize_roles([active] if active else '')
    if roles:
        return roles
    return get_granted_roles()


def highest_priority_role(roles) -> str:
    """Return the highest-priority role among *roles* ('' when none)."""
    clean = _normalize_roles(roles)
    for r in ROLE_PRIORITY:
        if r in clean:
            return r
    return ''


def get_user_permissions(role, department_id=None) -> set:
    """Return the set of permission strings for a role or roles.

    *department_id* is accepted for signature compatibility and is ignored.
    When *role* is a collection, the result is the union of each role's
    permissions (multi-role resolution).
    """
    perms = set()
    for r in _normalize_roles(role):
        perms |= ROLE_PERMISSIONS.get(r, set())
    return perms


def has_permission(role, permission: str | None, department_id=None) -> bool:
    """Check whether a role (or list of roles) holds a specific permission."""
    if permission is None:
        return True
    return permission in get_user_permissions(role, department_id)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('يرجى تسجيل الدخول أولاً', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)

    return decorated_function


def permission_required(permission):
    """Check that the logged-in user holds the given permission.

    Multi-role aware: the permission passes if ANY of the user's granted roles
    (``session['roles']``) grants it.
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('auth.login'))
            roles = get_granted_roles()
            dept_id = session.get('department_id')
            if not has_permission(roles, permission, dept_id):
                flash('ليس لديك صلاحية للوصول إلى هذه الصفحة', 'error')
                return redirect_back()
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def role_required(*roles):
    """Gate a route by the user's fixed role, not by a permission.

    Used for pages tied to a specific data shape (e.g. ``teachers`` rows)
    where granting a permission would be meaningless — see decision 2.1.
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('auth.login'))
            if session.get('role', '') not in roles:
                flash('ليس لديك صلاحية للوصول إلى هذه الصفحة', 'error')
                return redirect(url_for('dashboard.dashboard'))
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def any_role_required(*roles):
    """Gate a route by requiring at least one of the given roles.

    Like ``role_required`` but checks against the user's **full granted role
    set** rather than only the landing role.  This lets a person who is both a
    faculty member and a head of department reach ``/teacher/*`` pages (their
    ``teacher`` role) without needing a second account.
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('auth.login'))
            granted = set(get_granted_roles())
            if not granted.intersection(roles):
                flash('ليس لديك صلاحية للوصول إلى هذه الصفحة', 'error')
                return redirect(url_for('dashboard.dashboard'))
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def get_nav_items(role, department_id=None) -> list:
    """Return the ordered list of navigation items visible to a role.

    *role* may be a single role string or a list/set of roles (multi-role).
    When multiple roles are granted, an item is shown if any role makes it
    visible, subject to the same dedup rules as before.

    Deduplicates items that share the same endpoint but differ by
    role_filter (e.g. teacher vs hod classroom_requests).
    """
    roles = _normalize_roles(role)
    perms = get_user_permissions(roles, department_id)

    seen_endpoints = set()
    seen_active_keys = set()
    items = []
    for item in NAV_ITEMS:
        if item.get('teacher_only') and 'teacher' not in roles:
            continue
        perm = item.get('permission')
        if perm is not None and perm not in perms:
            continue
        role_filter = item.get('role_filter')
        if role_filter and role_filter not in roles:
            continue
        exclude_roles = item.get('exclude_roles') or []
        if any(r in exclude_roles for r in roles):
            continue
        ep = item['endpoint']
        if ep in seen_endpoints and not role_filter:
            continue
        if not role_filter:
            active_keys = item.get('active_keys') or []
            if any(k in seen_active_keys for k in active_keys):
                continue
        seen_endpoints.add(ep)
        if role_filter:
            seen_active_keys.update(item.get('active_keys') or [])
        items.append(item)
    return items


def get_header_messages_url(role) -> str | None:
    """Return the messages endpoint for the header, or None.

    Multi-role aware: prefers the HOD messages page when the user holds the
    ``head_of_department`` role, else the teacher messages page when they hold
    ``teacher``.
    """
    roles = _normalize_roles(role)
    if 'head_of_department' in roles:
        return 'hod_pages.hod_messages'
    if 'teacher' in roles:
        return 'teacher_pages.teacher_messages'
    return None


def inject_navigation() -> dict:
    """Jinja context processor — makes nav helpers available in every template.

    ``nav_items``/``user_permissions``/``has_permission``/``header_messages_url``
    reflect the **active** role (``session['role']``), so switching roles in-app
    immediately changes the sidebar.  ``user_roles`` keeps the full granted set
    for the role switcher and badges.
    """
    roles = get_granted_roles()
    active = get_active_roles()
    dept_id = session.get('department_id')
    return {
        'nav_items': get_nav_items(active, dept_id),
        'user_permissions': get_user_permissions(active, dept_id),
        'has_permission': lambda perm: has_permission(active, perm, dept_id),
        'header_messages_url': get_header_messages_url(active),
        'role_labels': ROLE_LABELS,
        'hide_sidebar': False,
        'user_roles': roles,
        'user_priority_role': highest_priority_role(active),
    }
