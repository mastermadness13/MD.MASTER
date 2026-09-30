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

from flask import flash, jsonify, redirect, request, session, url_for

from core.constants import ROLE_LABELS, ROLE_PERMISSIONS

# ترتيب الأدوار (الأعلى أولاً). بعد تسجيل الدخول الطالب
# ينزل على أعلى دور عنده، ويقدر يبدل بين الأدوار داخل التطبيق.
# العميد فوق الجميع لأنه المالك المؤسسي للقوائم والصلاحيات،
# ومن بعده بقية الأدوار الإدارية بترتيبها السابق بلا تغيير،
# ثم رئيس القسم فوق الأستاذ.
ROLE_PRIORITY = [
    'dean',
    'research_development',
    'faculty_affairs',
    'exam',
    'head_of_department',
    'teacher',
    'visitor',
]

# /     /     >---- مجموعة كل الأدوار المعروفة
ALL_ROLES_SET = frozenset(ROLE_PRIORITY)

# ─────────────────────────────────────────────

# /     /     >---- نحول حجة الدور إلى قائمة أدوار صحيحة (نشيل المجهولة)
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
    # /     /     >---- نصفي الأدوار اللي فيش منها في النظام
    return [r for r in roles if r in ALL_ROLES_SET]

# ─────────────────────────────────────────────

# /     /     >---- نرجع كل الأدوار اللي المستخدم مخول بيهن في هذي الجلسة
def get_granted_roles() -> list:
    """Return the authenticated user's full role set for this session.

    Prefers ``session['roles']`` (the multi-role list set at login); falls
    back to the single ``session['role']`` for legacy/partial sessions so an
    already-logged-in user is never locked out.
    """
    # /     /     >---- نفضّل القائمة الكاملة من الجلسة
    roles = session.get('roles')
    if isinstance(roles, list) and roles:
        return [r for r in roles if r in ALL_ROLES_SET] or [str(session.get('role', 'teacher')) or 'teacher']
    # /     /     >---- خلاف ذلك نرجع الدور الوحيد القديم
    return [str(session.get('role', 'teacher')) or 'teacher']

# ─────────────────────────────────────────────

# /     /     >---- نرجع الدور(الأدوار) اللي المستخدم شغال فيه الحين
def get_active_roles() -> list:
    """Return the role(s) the user is *currently operating under*.

    Unlike ``get_granted_roles()`` this follows the in-app role switcher:
    ``session['role']`` is the active role and everything the user sees right
    now (nav, permissions) is scoped to it.  Falls back to the full granted
    set only when the active role is unknown so nobody is locked out.
    """
    # /     /     >---- الدور النشط موجود في الجلسة
    active = session.get('role')
    roles = _normalize_roles([active] if active else '')
    if roles:
        return roles
    # /     /     >---- إذا ما عرفناه نرجع كل الأدوار
    return get_granted_roles()

# ─────────────────────────────────────────────

# /     /     >---- نرجع أعلى دور في الأولوية بين القائمة
def highest_priority_role(roles) -> str:
    """Return the highest-priority role among *roles* ('' when none)."""
    clean = _normalize_roles(roles)
    for r in ROLE_PRIORITY:
        if r in clean:
            return r
    return ''

# ─────────────────────────────────────────────

# /     /     >---- نجمع كل الصلاحيات من كل أدوار المستخدم
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

# ─────────────────────────────────────────────

# /     /     >---- نتأكد إذا المستخدم عنده صلاحية معينة
def has_permission(role, permission: str | None, department_id=None) -> bool:
    """Check whether a role (or list of roles) holds a specific permission."""
    # /     /     >---- إذا مافي صلاحية مطلوبة نسمح
    if permission is None:
        return True
    if permission not in get_user_permissions(role, department_id):
        return False
    # /     /     >---- تكليف «عرض فقط» يخفض صلاحية واحدة بعينها: نخفي
    # /     /     >---- أزرار الكتابة على صفحته ونرفض إرسالها معاً، لأن
    # /     /     >---- القالب والبوابة يقرآن نفس الدالة. بقية حسابه
    # /     /     >---- (جدوله، ملفه، صفحاته الأخرى) لا يتأثر.
    return not _is_demoted_write(permission)


def _write_blueprints(permission: str) -> frozenset:
    """Blueprints whose endpoints are gated by *permission* itself.

    Derived from the live URL map rather than a hand-written list, because one
    page family is served by more than one blueprint: ``classrooms`` renders
    the rooms page while ``api_rooms`` is the JSON surface the SPA writes
    through, and both declare ``rooms.manage``.  Testing the blueprint against
    the page's HTML name alone let every ``/api/*`` write sail past a
    read-only assignment.

    Both ``permission_required`` and ``api_permission_required`` stamp
    ``_required_permission`` on the view function, so this single lookup covers
    every door and keeps covering routes added later.

    Cached on the app: the URL map is fixed once blueprints are registered.
    """
    from flask import current_app

    cache = current_app.extensions.setdefault('write_permission_blueprints', {})
    try:
        return cache[permission]
    except KeyError:
        pass

    found = set()
    for endpoint in current_app.url_map.iter_rules():
        view_func = current_app.view_functions.get(endpoint.endpoint)
        if view_func is None:
            continue
        if getattr(view_func, '_required_permission', None) != permission:
            continue
        blueprint_name = endpoint.endpoint.rsplit('.', 1)[0]
        if blueprint_name != endpoint.endpoint:
            found.add(blueprint_name)

    cache[permission] = frozenset(found)
    return cache[permission]


def _is_demoted_write(permission: str) -> bool:
    """True when *permission* is a write on the active read-only page.

    Stateless on purpose: it asks the current request's blueprint which page
    family is being rendered, so it cannot drift from a stale session key and
    cannot fail open after a restart.

    "Same page" means: the permission is one of the page's declared writes
    *and* the request sits on a blueprint that gates that same permission.  The
    second half is what brings the ``/api/*`` twin in with the HTML page,
    instead of trusting a single blueprint name to name the whole family.
    """
    from flask import has_request_context

    # Outside a request there is no page being rendered, so no demotion can
    # apply.  Keeps the pure helpers (``has_permission``, ``compute_scope``)
    # callable from tests and batch tools without a request context.
    if not has_request_context():
        return False

    from flask import request
    from services.task_page_service import active_page

    page_key, mode, _label = active_page()
    if page_key is None or mode != 'view':
        return False
    from core.constants.task_pages import TASK_PAGES
    page = TASK_PAGES.get(page_key)
    if page is None:
        return False
    if permission not in page['write_permissions']:
        return False
    return request.blueprint in _write_blueprints(permission)

# ─────────────────────────────────────────────

# /     /     >---- هل هذا العميل يقرأ JSON بدل HTML؟
# /     /     >---- لا نعدّ `*/*` هنا عن قصد: متصفح Chrome يرسل
# /     /     >---- `text/html,...,*/*;q=0.8` في نموذج HTML عادي، فلو عدّناه
# /     /     >---- JSON لكان نموذج الحذف العادي يرجع JSON بدل الصفحة.
def wants_json_response() -> bool:
    """True when the caller parses the body as JSON instead of rendering HTML.

    Deliberately narrow: only an explicit ``X-Requested-With`` (fetch/XHR) or an
    ``application/json`` Accept entry counts.  ``*/*`` is excluded because every
    browser form post carries it, and answering those with JSON would replace
    ordinary HTML pages with a raw JSON blob.
    """
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    return 'application/json' in request.headers.get('Accept', '')


# /     /     >---- رفض JSON بدل التوجيه: بوابة صفحة ترجع 302 يتبعها fetch
# /     /     >---- فيُعاد HTML (صفحة الدخول) ويقرأه العميل بـ JSON.parse
def json_denial(message: str, status: int):
    """Return a JSON denial for AJAX callers, or ``None`` for browser callers."""
    if not wants_json_response():
        return None
    return jsonify(ok=False, message=message), status


# ─────────────────────────────────────────────

# /     /     >---- ديكوريتور: يشترط تسجيل الدخول للصفحة
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # /     /     >---- إذا ما فيه مستخدم في الجلسة نوجهه لصفحة الدخول
        if 'user_id' not in session:
            denial = json_denial('انتهت الجلسة. سجّل الدخول مجدداً.', 401)
            if denial is not None:
                return denial
            flash('يرجى تسجيل الدخول أولاً', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)

    return decorated_function

# ─────────────────────────────────────────────

# /     /     >---- ديكوريتور: يشترط صلاحية معينة للصفحة
def permission_required(permission):
    """Check that the logged-in user holds the given permission.

    The permission is evaluated against the active role. Other granted roles
    remain available to the role switcher but must not leak capabilities into
    the current context.
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # /     /     >---- أول شي يتأكد من تسجيل الدخول
            if 'user_id' not in session:
                denial = json_denial('انتهت الجلسة. سجّل الدخول مجدداً.', 401)
                if denial is not None:
                    return denial
                return redirect(url_for('auth.login'))
            # A one-time initial credential may authenticate the user, but it
            # must not grant access to the application until it is replaced.
            # Keep logout available so a user can abandon the session.
            if (session.get('force_password_change')
                    and request.endpoint not in ('auth.change_password', 'auth.logout')):
                denial = json_denial('يجب تغيير كلمة المرور أولاً.', 403)
                if denial is not None:
                    return denial
                return redirect(url_for('auth.change_password'))
            # /     /     >---- نجمع كل أدوار المستخدم ونتأكد من الصلاحية
            roles = get_active_roles()
            dept_id = session.get('department_id')
            if not has_permission(roles, permission, dept_id):
                denial = json_denial('ليس لديك صلاحية لتنفيذ هذا الإجراء.', 403)
                if denial is not None:
                    return denial
                # /     /     >---- سحب صلاحية يجب أن يخفي الصفحة لا أن
                # /     /     >---- يصرخ في وجه المستخدم. التوجيه إلى لوحته
                # /     /     >---- بلا رسالة: العنصر اختفى من القائمة أيضاً
                # /     /     >---- لأن التنقل يفلتر بالصلاحيات نفسها.
                # /     /     >---- وredirect_back كان يترك حلقة إعادة توجيه
                # /     /     >---- إذا كان المرجع نفس الصفحة الممنوعة.
                return redirect(url_for('dashboard.dashboard'))
            return f(*args, **kwargs)

        # Store required permission for deny-by-default before_request hook
        decorated_function._required_permission = permission
        return decorated_function

    return decorator

# ─────────────────────────────────────────────

# /     /     >---- ديكوريتور: يحصر الصفحة على أدوار محددة بالضبط
def role_required(*roles):
    """Gate a route by the user's fixed role, not by a permission.

    Used for pages tied to a specific data shape (e.g. ``teachers`` rows)
    where granting a permission would be meaningless — see decision 2.1.
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # /     /     >---- يتأكد من تسجيل الدخول
            if 'user_id' not in session:
                denial = json_denial('انتهت الجلسة. سجّل الدخول مجدداً.', 401)
                if denial is not None:
                    return denial
                return redirect(url_for('auth.login'))
            # /     /     >---- يتأكد الدور النشط موجود في الأدوار المسموحة
            if session.get('role', '') not in roles:
                denial = json_denial('ليس لديك صلاحية لتنفيذ هذا الإجراء.', 403)
                if denial is not None:
                    return denial
                return redirect(url_for('dashboard.dashboard'))
            return f(*args, **kwargs)

        # Declare the role gate so the deny-by-default before_request hook
        # recognises this endpoint as guarded instead of refusing it.
        decorated_function._required_roles = tuple(roles)
        return decorated_function

    return decorator

# ─────────────────────────────────────────────

# /     /     >---- ديكوريتور: يقبل أي دور من القائمة (أي واحد يكفي)
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
                denial = json_denial('انتهت الجلسة. سجّل الدخول مجدداً.', 401)
                if denial is not None:
                    return denial
                return redirect(url_for('auth.login'))
            # /     /     >---- نشوف إذا أي دور من أدوار المستخدم في القائمة
            granted = set(get_granted_roles())
            if not granted.intersection(roles):
                denial = json_denial('ليس لديك صلاحية لتنفيذ هذا الإجراء.', 403)
                if denial is not None:
                    return denial
                return redirect(url_for('dashboard.dashboard'))
            return f(*args, **kwargs)

        # Declare the role gate so the deny-by-default before_request hook
        # recognises this endpoint as guarded instead of refusing it.
        decorated_function._required_any_roles = tuple(roles)
        return decorated_function

    return decorator

# ─────────────────────────────────────────────

# /     /     >---- نرجع رابط الرسائل في الهيدر حسب الدور
def get_header_messages_url(roles) -> str | None:
    """Return the messages endpoint for the header, or None.

    Multi-role aware: prefers the HOD messages page when the user holds the
    ``head_of_department`` role, else the teacher messages page when they hold
    ``teacher``.
    """
    roles = _normalize_roles(roles)
    # /     /     >---- رئيس القسم أولاً
    if 'head_of_department' in roles:
        return 'hod_pages.hod_messages'
    # /     /     >---- وبعدين المدرس
    if 'teacher' in roles:
        return 'teacher_pages.teacher_messages'
    return None

# ─────────────────────────────────────────────

# /     /     >---- مساعد القوالب (Jinja): يضيف دوال التنقل في كل الصفحات
def get_nav_items(role, department_id=None):
    """Backward-compatible helper: navigation items for a role/dept.

    Delegates to the permission-based pipeline so both the SPA bootstrap
    (``api/auth_api.py``) and template injection share the same source of truth.
    """
    perms = get_user_permissions(role, department_id)
    from core.constants.navigation import get_nav_for_permissions
    return get_nav_for_permissions(perms)


# /     /     >---- مساعد القوالب (Jinja): يضيف دوال التنقل في كل الصفحات
def inject_navigation() -> dict:
    """Jinja context processor — makes nav helpers available in every template.

    ``nav_items``/``user_permissions``/``has_permission``/``header_messages_url``
    reflect the user's active role. Granted roles are exposed separately only
    for the role switcher.
    """
    from core.constants.navigation import get_nav_for_permissions
    roles = get_active_roles()
    granted_roles = get_granted_roles()
    dept_id = session.get('department_id')
    perms = get_user_permissions(roles, dept_id)
    return {
        'nav_items': get_nav_for_permissions(perms),
        'user_permissions': perms,
        'has_permission': lambda perm: perm in perms,
        'header_messages_url': get_header_messages_url(roles),
        'role_labels': ROLE_LABELS,
        'hide_sidebar': False,
        'user_roles': granted_roles,
        'user_priority_role': highest_priority_role(granted_roles),
    }