"""Navigation registry — ordered sidebar items.

Each item defines:
  key         – matches sidebar_active values in templates
  endpoint    – Flask endpoint for url_for()
  icon        – Material Symbol name
  label       – Arabic display text
  permission  – required permission string
  active_keys – list of sidebar_active values that should highlight this item

  section     – 'main' (always visible) or 'more' (collapsible hidden section)
"""

# /     /     >---- السجل الرئيسي لقائمة التنقل (الشريط الجانبي)
# /     /     >---- كل عنصر فيه: مفتاح، الصفحة، الأيقونة، الاسم، زالصاحية، والقسم (رئيسي أو مخفي)
NAV_ITEMS = [
    # ── لوحة التحكم ──────────────────────────────────────────────
    {
        'key': 'dashboard',
        'endpoint': 'dashboard.dashboard',
        'icon': 'dashboard',
        'label': 'لوحة التحكم',
        'permission': 'dashboard.view',
        'active_keys': ['dashboard.dashboard'],
        'exclude_roles': ['exam'],   # /     /     >---- قسم الامتحانات ما يشوفش لوحة التحكم
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
    # ── تقارير الأعضاء (لشؤون أعضاء هيئة التدريس) ────────────────
    {
        'key': 'faculty_reports',
        'endpoint': 'faculty_performance.member_reports',
        'icon': 'assessment',
        'label': 'تقارير الأعضاء',
        'permission': 'faculty_performance.view',
        'active_keys': ['faculty_reports'],
        'role_filter': 'faculty_affairs',
        'section': 'main',
    },
    # ── الإجازات (لشؤون أعضاء هيئة التدريس) ──────────────────────
    {
        'key': 'faculty_leaves',
        'endpoint': 'faculty_performance.leaves_index',
        'icon': 'event_busy',
        'label': 'الإجازات',
        'permission': 'faculty_performance.edit_leaves',
        'active_keys': ['faculty_leaves'],
        'role_filter': 'faculty_affairs',
        'section': 'main',
    },
    # ── قائمة معدل الأداء (السوبر أدمن) ───────────────────────────
    {
        'key': 'faculty_performance_rate',
        'endpoint': 'faculty_performance.performance_rate_list',
        'icon': 'monitoring',
        'label': 'قائمة معدل الأداء',
        'permission': 'faculty_performance.view_summary',
        'active_keys': ['faculty_performance_rate'],
        'section': 'main',
    },
    # ── المقررات الدراسية (إدارة) ────────────────────────────────
    {
        'key': 'courses_admin',
        'endpoint': 'courses.courses_list',
        'icon': 'menu_book',
        'label': 'المقررات الدراسية',
        'permission': 'courses.manage',
        'active_keys': ['courses'],
        'section': 'main',
    },
    # ── المقررات (مشاهدة فقط) ────────────────────────────────────
    {
        'key': 'courses_view',
        'endpoint': 'courses.courses_list',
        'icon': 'menu_book',
        'label': 'المقررات',
        'permission': 'courses.view',
        'active_keys': ['courses'],
        'exclude_roles': ['exam'],   # /     /     >---- قسم الامتحانات ما يشوفش هذي
        'section': 'main',
    },
    # ── القاعات ──────────────────────────────────────────────────
    {
        'key': 'rooms',
        'endpoint': 'classrooms.rooms_list',
        'icon': 'meeting_room',
        'label': 'القاعات',
        'permission': 'rooms.view',
        'active_keys': ['rooms'],
        'section': 'main',
    },
    # ── الجدول الدراسي ───────────────────────────────────────────
    {
        'key': 'timetable',
        'endpoint': 'timetable.timetable',
        'icon': 'calendar_today',
        'label': 'الجدول الدراسي',
        'permission': 'timetable.view',
        'active_keys': ['timetable.timetable', 'timetable.timetable_department_view'],
        'exclude_roles': ['research_development', 'exam'],   # /     /     >---- ليش هذول؟ لأن عندهم جدول خاص فيهم
        'section': 'main',
    },
    # ── الجدول الدراسي لقسم البحث والتطوير ───────────────────────
    {
        'key': 'timetable_rnd',
        'endpoint': 'timetable.rnd_timetable',
        'icon': 'calendar_today',
        'label': 'الجدول الدراسي',
        'permission': 'timetable.view',
        'active_keys': ['timetable.rnd_timetable'],
        'role_filter': 'research_development',
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
    # ── رفع المقرر (المحتوى الدراسي) ─────────────────────────────
    {
        'key': 'course_content_admin',
        'endpoint': 'teacher_pages.super_admin_course_content_list',
        'icon': 'description',
        'label': 'رفع المقرر',
        'permission': 'course_content.manage',
        'active_keys': ['course_content_admin'],
        'section': 'main',
    },
    # ── المقررات المكلف بها (للمدرس) ─────────────────────────────
    {
        'key': 'course_content_teacher',
        'endpoint': 'teacher_pages.teacher_course_content',
        'icon': 'upload_file',
        'label': 'المقررات المكلف بها',
        'permission': 'course_content.view',
        'active_keys': ['course_content'],
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
    # طلبات تغيير القاعات (لرئيس القسم)
    {
        'key': 'classroom_requests_hod',
        'endpoint': 'classroom_requests.pending',
        'icon': 'meeting_room',
        'label': 'طلبات تغيير القاعات',
        'permission': 'classroom_requests.manage',
        'active_keys': ['classroom_requests'],
        'role_filter': 'head_of_department',
        'section': 'more',
    },
    # إضافة أستاذ للقسم (لرئيس القسم)
    {
        'key': 'teachers_assign',
        'endpoint': 'teachers.teachers_list',
        'icon': 'person_add',
        'label': 'إضافة أستاذ للقسم',
        'permission': 'teachers.assign',
        'active_keys': ['teachers'],
        'role_filter': 'head_of_department',
        'section': 'more',
    },
    # المواد الدراسية
    {
        'key': 'materials',
        'endpoint': 'hod_pages.hod_materials',
        'icon': 'menu_book',
        'label': 'المواد الدراسية',
        'permission': 'materials.manage',
        'active_keys': ['materials'],
        'section': 'more',
    }]