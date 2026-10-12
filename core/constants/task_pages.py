"""Task pages — the screens an administrative assignment can be attached to.

An entry in ``admin_assignment_types`` is a *block*, not a label: the dean
writes its name once, it shows up in the teacher's create/edit dropdown, and it
can be pointed at one of the pages below. Whoever holds the assignment lands on
that page instead of a generic dashboard, and the dean decides whether that
person may **edit** it or only **view** it.

``access_mode`` is enforced per page, not per account: a read-only assignment
hides the write controls on its own page and refuses the write endpoints, while
the rest of the person's account (their own timetable, their profile) is
untouched.  That is the same contract the role→permission map already has
(``rooms.view`` without ``rooms.manage``), so nothing new has to be invented at
render time — ``page_key`` simply names which permission family to demote.
"""

from __future__ import annotations

from collections.abc import Mapping

from core.constants.permission_labels import group_permissions

# ── أيقونة واسم كل صفحة يمكن ربطها بتكليف إداري ─────────────────────
# /     /     >---- write_permissions: ما الذي يُسقطه وضع «عرض فقط».
# /     /     >---- view_permission: ما لازم يبقى موجوداً لعرض الصفحة.
# /     /     >---- render_blueprints: الـ blueprints التي ترسم الصفحة نفسها،
# /     /     >---- فتُخفض الكتابة فيها حتى لو لم تكن مصنّفة كتابة فيها.
# /     /     >---- لا يوجد حقل «blueprint» هنا عمداً: عائلة الصفحة الواحدة
# /     /     >---- موزّعة على أكثر من blueprint («القاعات» = classrooms و
# /     /     >---- api_rooms معاً)، فتسميته باسم واحد كانت توحي بتغطية
# /     /     >---- شاملة وهي كذلك ليست. التحديد الفعلي يُشتقّ من url_map في
# /     /     >---- security/authorization.py::_write_blueprints، فيلتقط أي
# /     /     >---- مسار محمي بنفس الصلاحية بلا قائمة تُنسى.
TASK_PAGES: dict[str, dict] = {
    'rooms': {
        'label': 'القاعات',
        'endpoint': 'classrooms.rooms_list',
        'icon': 'meeting_room',
        'view_permission': 'rooms.view',
        # /     /     >---- rooms.manage باقية في القائمة: هي الاسم الخام
        # /     /     >---- الذي حملته الأدوار القديمة، وتبقى في
        # /     /     >---- exposed_permissions ليقرأها العميل بوضوح.
        'write_permissions': ('rooms.create', 'rooms.edit', 'rooms.delete',
                              'rooms.manage'),
        'render_blueprints': ('classrooms', 'api_rooms'),
    },
    'timetable': {
        'label': 'الجدول الدراسي',
        'endpoint': 'timetable.timetable',
        'icon': 'calendar_today',
        'view_permission': 'timetable.view',
        'write_permissions': ('timetable.edit',),
    },
    'exams': {
        'label': 'الجدول الامتحانات',
        'endpoint': 'exams.exams',
        'icon': 'grading',
        'view_permission': 'exams.view',
        # exams.department_schedule يحفظ تاريخ الامتحان لكل مادة ويبعثه —
        # كتابة كاملة، وقُدرت ناقصة هنا فبقي الباب مفتوحاً على «عرض فقط».
        'write_permissions': (
            'exams.manage', 'exams.period', 'exams.planning',
            'exams.assign_room', 'exams.department_schedule',
            'exams.create', 'exams.edit', 'exams.delete',
        ),
        'render_blueprints': ('exams', 'api_exams'),
    },
    'teachers': {
        'label': 'أعضاء هيئة التدريس',
        'endpoint': 'teachers.teachers_list',
        'icon': 'school',
        'view_permission': 'teachers.view',
        'write_permissions': (
            'teachers.manage', 'teachers.assign', 'teachers.lookup_lists.manage',
        ),
    },
    'departments': {
        'label': 'الأقسام',
        'endpoint': 'departments.departments_list',
        'icon': 'account_tree',
        'view_permission': 'departments.view',
        'write_permissions': ('departments.manage',),
    },
    'courses': {
        'label': 'المقررات الدراسية',
        'endpoint': 'courses.courses_list',
        'icon': 'menu_book',
        'view_permission': 'courses.view',
        'write_permissions': ('courses.manage',),
    },
    'performance': {
        'label': 'قائمة معدل الأداء',
        'endpoint': 'faculty_performance.performance_rate_list',
        'icon': 'monitoring',
        'view_permission': 'faculty_performance.view_summary',
        'write_permissions': (
            'faculty_performance.edit_research',
            'faculty_performance.edit_assignments',
            'faculty_performance.edit_leaves',
        ),
    },
    'history': {
        'label': 'سجل التغييرات',
        'endpoint': 'history.history_list',
        'icon': 'history',
        'view_permission': 'history.view',
        'write_permissions': (),
    },
}

# ── نمط الوصول ──────────────────────────────────────────────────────
ACCESS_MODES: dict[str, str] = {
    'edit': 'تعديل كامل',
    'view': 'عرض فقط',
}

DEFAULT_ACCESS_MODE = 'edit'

# /     /     >---- وضع «عرض فقط» يُبقي القدرة على قراءة الصفحة وإلا صار
# /     /     >---- الحجب مُعطِّلاً بلا فائدة: لا كتابة ولا حتى قراءة.
MIN_VIEW_PERMISSIONS: tuple[str, ...] = (
    'dashboard.view',
    'dashboard.nav',
    'uploads.serve',
    'profile.view',
)


def page_keys() -> list[str]:
    """Valid ``page_key`` values."""
    return list(TASK_PAGES)


def is_valid_page_key(key: str | None) -> bool:
    return bool(key) and key in TASK_PAGES


def normalise_access_mode(mode: str | None) -> str:
    """Coerce anything unexpected to the safe full-access default."""
    return mode if mode in ACCESS_MODES else DEFAULT_ACCESS_MODE


def describe_assignment_page(row: Mapping) -> dict:
    """Derive the page binding and the permissions it exposes for one
    ``admin_assignment_types`` row.

    Pure: no DB, no request context, and it never raises. Accepts a mapping
    (a plain dict or an sqlite3.Row converted to dict) with keys
    ``page_key`` and ``page_access_mode``; missing/None/invalid values are
    handled gracefully. This mirrors the read-only demotion semantics in
    ``services/task_page_service.restrict_permissions`` without importing it.
    """
    # /     /     >---- القراءة فقط: أي مفتاح مفقود أو غير صالح يُعالج بلا استثناء
    if row is None:
        row = {}
    elif not isinstance(row, Mapping):
        # /     /     >---- نحوّل أي صف SQLite إلى قاموس حتى لا يفشل .get
        row = dict(row)
    page_key = row.get('page_key')
    has_page = is_valid_page_key(page_key)
    page = TASK_PAGES.get(page_key) if has_page else None

    page_label = page['label'] if page else ''
    icon = page['icon'] if page else ''
    endpoint = page['endpoint'] if page else ''
    access_mode = (
        normalise_access_mode(row.get('page_access_mode')) if has_page else None
    )
    access_mode_label = ACCESS_MODES.get(access_mode, '') if access_mode else ''
    view_permission = page['view_permission'] if page else None
    write_permissions = tuple(page['write_permissions']) if page else ()
    render_blueprints = tuple(page.get('render_blueprints', ())) if page else ()

    # /     /     >---- حزمة صلاحيات الصفحة: (view + write) في وضع التعديل، أو (view + الأساسيات) في وضع العرض
    # /     /     >---- يجب أن تبقى متزامنة مع restrict_permissions في services/task_page_service
    if has_page and access_mode == 'edit':
        exposed_permissions = (view_permission, *write_permissions)
    elif has_page and access_mode == 'view':
        exposed_permissions = (view_permission, *MIN_VIEW_PERMISSIONS)
    else:
        exposed_permissions = ()

    grants_write = bool(has_page and access_mode == 'edit' and write_permissions)
    invalid_page_key = bool(page_key) and not has_page
    warning = (
        'يمنح هذا التكليف صلاحيات تعديل (كتابة) على الصفحة المرتبطة — '
        'راجع الصلاحيات قبل التفعيل.'
        if grants_write else ''
    )

    return {
        'has_page': has_page,
        'page_key': page_key,
        'page_label': page_label,
        'icon': icon,
        'endpoint': endpoint,
        'access_mode': access_mode,
        'access_mode_label': access_mode_label,
        'view_permission': view_permission,
        'write_permissions': write_permissions,
        'render_blueprints': render_blueprints,
        'exposed_permissions': exposed_permissions,
        'grants_write': grants_write,
        'invalid_page_key': invalid_page_key,
        'warning': warning,
        # /     /     >---- إضافي فقط: نفس الصلاحيات لكن مقرّبة بنطاقاتها
        # /     /     >---- وبأسمائها العربية، حتى يقرأها العميل ولا يرى
        # /     /     >---- نصوصاً تقنية. withheld_groups هي ما يحجبه وضع
        # /     /     >---- «عرض فقط».
        'permission_groups': group_permissions(exposed_permissions),
        'withheld_groups': group_permissions(
            [p for p in write_permissions if p not in exposed_permissions]
        ),
    }
