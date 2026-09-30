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

# ── أيقونة واسم كل صفحة يمكن ربطها بتكليف إداري ─────────────────────
# /     /     >---- write_permissions: ما الذي يُسقطه وضع «عرض فقط».
# /     /     >---- view_permission: ما لازم يبقى موجوداً لعرض الصفحة.
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
        'write_permissions': ('rooms.manage',),
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
        ),
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
