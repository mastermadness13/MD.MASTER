"""Permission model — role → set of permission strings.

Architecture:  Role → Permissions → Navigation
The authenticated user's role is the single source of truth.
"""

# ─────────────────────────────────────────────────────────────────────────────
# /     /     >---- ملاحظة مهمة: المسارات الخاصة بالمدرس (teacher_only)
# /     /     >---- محكومة بالدور (security.role_required) مو بالصلاحيات —
# /     /     >---- يعني لا تحاول تعطيها أو تمنعها من خريطة role_permissions.
# /     /     >---- هذي خاصة بالمدرسين وفقط
# ─────────────────────────────────────────────────────────────────────────────

# /     /     >---- خريطة الصلاحيات لكل دور في النظام
# /     /     >---- Architecture: الدور ← الصلاحيات ← التنقل
ROLE_PERMISSIONS = {
    # ── قسم البحث والتطوير والمناهج ─────────────────────────────────
    'research_development': {
        'dashboard.view', 'dashboard.nav',
        'departments.view',
        'teachers.view',
        'courses.manage', 'courses.view',
        'timetable.view',
        'academic_calendar.manage',
        'course_content.view', 'course_content.manage',
        'course_content.create', 'course_content.edit', 'course_content.submit',
        'course_content.review', 'course_content.publish', 'course_content.unpublish',
        'reports.view',
        'uploads.serve',
        'profile.view', 'profile.edit',
        'faculty_performance.view',
    },
    # ── مكتب إدارة أعضاء هيئة التدريس ───────────────────────────────
    'faculty_affairs': {
        'dashboard.view', 'dashboard.nav',
        'teachers.manage', 'teachers.view',
        'teachers.lookup_lists.manage',
        'teachers.assign',
        'timetable.view',
        'history.view',
        'uploads.serve',
        'tools.view',
        'rooms.view', 'rooms.manage',
        'profile.view', 'profile.edit',
        'faculty_performance.view', 'faculty_performance.view_summary',
        'faculty_performance.edit_research',
        'faculty_performance.edit_assignments', 'faculty_performance.edit_leaves',
        'faculty_performance.print',
    },
    # ── رئيس القسم ──────────────────────────────────────────────────
    'head_of_department': {
        'dashboard.view', 'dashboard.nav',
        'teachers.view',
        'course_content.view',
        'timetable.view', 'timetable.edit',
        'exams.view', 'exams.department_schedule',
        'messages.review', 'messages.view',
        'materials.manage', 'uploads.view', 'uploads.serve',
        'profile.view', 'profile.edit',
        'faculty_performance.view', 'faculty_performance.edit_research',
        'faculty_performance.edit_assignments', 'faculty_performance.print',
    },
    # ── عضو هيئة التدريس (المدرس) ───────────────────────────────────
    'teacher': {
        'dashboard.view',
        'timetable.view',
        'course_content.view', 'course_content.edit',
        'messages.view', 'uploads.view',
        'profile.view', 'profile.edit',
    },
# ── قسم الإدارة والامتحانات ─────────────────────────────────────
    'exam': {
        'dashboard.view', 'dashboard.nav',
        'departments.view', 'departments.manage',
        'courses.view',
        'course_content.view',
        'rooms.view',  # /     /     >---- عرض القاعات لاختيارها عند جدولة الامتحانات فقط
        'exams.view', 'exams.manage', 'exams.period', 'exams.planning', 'exams.department_schedule', 'exams.assign_room',
        'uploads.serve',
        'tools.view',
        'profile.view', 'profile.edit',
    },
    # ── العميد ───────────────────────────────────────────────────
    # /     /     >---- إشراف قراءة فقط على كل نطاقات النظام
    'dean': {
        'dashboard.view', 'dashboard.nav',
        'departments.view',
        'teachers.view',
        'courses.view',
        'rooms.view',
        'timetable.view',
        'exams.view',
        'course_content.view',
        'reports.view',
        'history.view',
        'uploads.serve',
        'profile.view', 'profile.edit',
        'faculty_performance.view', 'faculty_performance.view_summary',
        'faculty_performance.print',
    },
    # ── الزائر العام ─────────────────────────────────────────────
    # /     /     >---- مشاهدة النشرات المتاحة فقط (لا تعديل ولا بيانات خاصة)
    'visitor': {
        'dashboard.view', 'dashboard.nav',
        'courses.view',
        'timetable.view',
        'exams.view',
        'course_content.view',
        'uploads.serve',
        'profile.view',
    },
}