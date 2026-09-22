"""Navigation registry — ordered sidebar items.

Each item defines:
  key         – matches sidebar_active values in templates
  endpoint    – Flask endpoint for url_for()
  icon        – Material Symbol name
  label       – Arabic display text
  permission  – required permission string (single source of truth)
  active_keys – list of sidebar_active values that should highlight this item
  section     – 'main' (always visible) or 'more' (collapsible hidden section)
"""

NAV_ITEMS = [
    # ── لوحة التحكم ──────────────────────────────────────────────
    {
        'key': 'dashboard',
        'endpoint': 'dashboard.dashboard',
        'icon': 'dashboard',
        'label': 'لوحة التحكم',
        'permission': 'dashboard.view',
        'active_keys': ['dashboard.dashboard'],
        'section': 'main',
    },
    # ── أعضاء هيئة التدريس ───────────────────────────────────────
    {
        'key': 'teachers_admin',
        'endpoint': 'teachers.teachers_list',
        'icon': 'school',
        'label': 'أعضاء هيئة التدريس',
        'permission': 'teachers.manage',
        'active_keys': ['teachers'],
        'section': 'main',
    },
    # ── قائمة معدل الأداء (مكتب أعضاء هيئة التدريس) ────────────────
    {
        'key': 'faculty_performance_rate',
        'endpoint': 'faculty_performance.performance_rate_list',
        'icon': 'monitoring',
        'label': 'قائمة معدل الأداء',
        'permission': 'faculty_performance.view_summary',
        'active_keys': ['faculty_performance_rate'],
        'section': 'main',
    },
    # ── المقررات الدراسية ────────────────────────────────────────
    {
        'key': 'courses',
        'endpoint': 'courses.courses_list',
        'icon': 'menu_book',
        'label': 'المقررات الدراسية',
        'permission': 'courses.view',
        'active_keys': ['courses'],
        'section': 'main',
    },
    # ── الجدول الدراسي ───────────────────────────────────────────
    {
        'key': 'timetable',
        'endpoint': 'timetable.timetable',
        'icon': 'calendar_today',
        'label': 'الجدول الدراسي',
        'permission': 'timetable.view',
        'active_keys': ['timetable.timetable', 'timetable.timetable_department_view', 'timetable.rnd_timetable'],
        'section': 'main',
    },
    # ── الجدول الامتحانات ────────────────────────────────────────
    {
        'key': 'exams',
        'endpoint': 'exams.exams',
        'icon': 'grading',
        'label': 'الجدول الامتحانات',
        'permission': 'exams.view',
        'active_keys': ['exams.exams'],
        'section': 'main',
    },
    # ── رفع محتوى المقرر (المناهج والمفردات) ──────────────────────
    {
        'key': 'course_content_admin',
        'endpoint': 'teacher_pages.super_admin_course_content_list',
        'icon': 'description',
        'label': 'رفع محتوى المقرر',
        'permission': 'course_content.manage',
        'active_keys': ['course_content_admin'],
        'section': 'main',
    },
    # ── قسم "المزيد" (عناصر مخفية في قسم قابل للطي) ───────────────
    # سجل التغييرات
    {
        'key': 'history',
        'endpoint': 'history.history_list',
        'icon': 'history',
        'label': 'سجل التغييرات',
        'permission': 'history.view',
        'active_keys': ['history'],
        'section': 'more',
    },
    # الأقسام
    {
        'key': 'departments',
        'endpoint': 'departments.departments_list',
        'icon': 'account_tree',
        'label': 'الأقسام',
        'permission': 'departments.manage',
        'active_keys': ['departments'],
        'section': 'more',
    },
]


def get_nav_for_permissions(user_permissions: set[str]) -> list[dict]:
    """Return navigation items filtered by user's permissions."""
    return [item for item in NAV_ITEMS if item['permission'] in user_permissions]