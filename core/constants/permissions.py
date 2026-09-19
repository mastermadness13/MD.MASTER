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
    # ── مدير النظام (كله إله) ───────────────────────────────────────
    'super_admin': {
        'dashboard.view',
        'departments.manage', 'departments.view',
        'teachers.manage', 'teachers.view',
        'courses.manage', 'courses.view',
        'rooms.manage', 'rooms.view',
        'timetable.view', 'timetable.edit',
        'exams.view', 'exams.manage', 'exams.period', 'exams.planning', 'exams.department_schedule', 'exams.assign_room',
        'history.view',
        'course_content.view', 'course_content.manage',
        'course_content.create', 'course_content.edit',
        'course_content.review', 'course_content.publish', 'course_content.unpublish',
        'reports.view',
        'uploads.serve',
        'tools.view',
        'profile.view', 'profile.edit',
        'faculty_performance.view', 'faculty_performance.edit_research',
        'faculty_performance.edit_assignments', 'faculty_performance.edit_leaves',
        'faculty_performance.print',
        'faculty_performance.view_summary',
    },
    # ── قسم البحث والتطوير والمناهج ─────────────────────────────────
    'research_development': {
        'dashboard.view',
        'departments.view',
        'teachers.view',
        'courses.manage', 'courses.view',
        'timetable.view',
        'course_content.view', 'course_content.manage',
        'course_content.create', 'course_content.edit', 'course_content.submit',
        'course_content.review', 'course_content.publish',
        'reports.view',
        'uploads.serve',
        'profile.view', 'profile.edit',
        'faculty_performance.view', 'faculty_performance.edit_research',
        'faculty_performance.edit_assignments', 'faculty_performance.edit_leaves',
        'faculty_performance.print',
    },
    # ── مكتب إدارة أعضاء هيئة التدريس ───────────────────────────────
    'faculty_affairs': {
        'dashboard.view',
        'teachers.manage', 'teachers.view',

        'course_content.view',
        'uploads.serve',
        'tools.view',
        'profile.view', 'profile.edit',
        'faculty_performance.view', 'faculty_performance.edit_research',
        'faculty_performance.edit_assignments', 'faculty_performance.edit_leaves',
        'faculty_performance.print',
    },
    # ── رئيس القسم ──────────────────────────────────────────────────
    'head_of_department': {
        'dashboard.view',
        'teachers.view', 'teachers.assign',
        'courses.view',
        'course_content.view',
        'timetable.view', 'timetable.edit',
        'exams.view', 'exams.department_schedule',
        'materials.manage',
        'messages.review',
        'classroom_requests.manage',
        'profile.view', 'profile.edit',
        'faculty_performance.view', 'faculty_performance.edit_research',
        'faculty_performance.edit_assignments', 'faculty_performance.print',
    },
    # ── عضو هيئة التدريس (المدرس) ───────────────────────────────────
    'teacher': {
        'dashboard.view',
        'timetable.view',
        'course_content.view',
        'course_content.edit',
        'uploads.view',
        'messages.view',
        'classroom_requests.view',
        'uploads.serve',
        'tools.view',
        'profile.view', 'profile.edit',
        'faculty_performance.view', 'faculty_performance.print',
    },
    # ── قسم الإدارة والامتحانات ─────────────────────────────────────
    'exam': {
        'dashboard.view',
        'timetable.view',
        'courses.view',
        'course_content.view',
        'rooms.view',
        'exams.view', 'exams.manage', 'exams.period', 'exams.planning', 'exams.department_schedule', 'exams.assign_room',
        'uploads.serve',
        'tools.view',
        'profile.view', 'profile.edit',
    },
}