"""Permission model — role → set of permission strings.

Architecture:  Role → Permissions → Navigation
The authenticated user's role is the single source of truth.
"""

# ─────────────────────────────────────────────────────────────────────────────
# teacher_only routes are role-gated (security.role_required), not permission-
# gated — do not attempt to grant/revoke them via the role_permissions map.
# This mirrors decision 2.1: /teacher/profile, /teacher/my-schedule and
# other teacher-scoped routes belong to the `teachers` data shape and are meaningless for
# roles without a linked teachers row.
# ─────────────────────────────────────────────────────────────────────────────
ROLE_PERMISSIONS = {
    'super_admin': {
        'dashboard.view',
        'departments.manage', 'departments.view',
        'teachers.manage', 'teachers.view',
        'courses.manage', 'courses.view',
        'rooms.manage', 'rooms.view',
        'timetable.view', 'timetable.edit',
        'exams.view', 'exams.manage', 'exams.period', 'exams.planning', 'exams.department_schedule', 'exams.assign_room',
        'history.view',
        'course_content.view',
        'reports.view',
        'uploads.serve',
        'tools.view',
        'profile.view', 'profile.edit',
        'academic_calendar.manage',
        'faculty_performance.view', 'faculty_performance.edit_research',
        'faculty_performance.edit_assignments', 'faculty_performance.edit_leaves',
        'faculty_performance.print',
    },
    'research_development': {
        'dashboard.view',
        'departments.view',
        'teachers.view',
        'courses.manage', 'courses.view',
        'timetable.view',
        'course_content.view',
        'reports.view',
        'uploads.serve',
        'profile.view', 'profile.edit',
        'academic_calendar.manage',
        'faculty_performance.view', 'faculty_performance.edit_research',
        'faculty_performance.edit_assignments', 'faculty_performance.edit_leaves',
        'faculty_performance.print',
    },
    'faculty_affairs': {
        'dashboard.view',
        'teachers.manage', 'teachers.view',

        'uploads.serve',
        'tools.view',
        'profile.view', 'profile.edit',
        'faculty_performance.view', 'faculty_performance.edit_research',
        'faculty_performance.edit_assignments', 'faculty_performance.edit_leaves',
        'faculty_performance.print',
    },
    'head_of_department': {
        'dashboard.view',
        'teachers.view', 'teachers.assign',
        'courses.view',
        'timetable.view', 'timetable.edit',
        'exams.view', 'exams.department_schedule',
        'materials.manage',
        'messages.review',
        'classroom_requests.manage',
        'profile.view', 'profile.edit',
        'faculty_performance.view', 'faculty_performance.edit_research',
        'faculty_performance.edit_assignments', 'faculty_performance.print',
    },
    'teacher': {
        'dashboard.view',
        'timetable.view',
        'course_content.edit',
        'uploads.view',
        'messages.view',
        'classroom_requests.view',
        'uploads.serve',
        'tools.view',
        'profile.view', 'profile.edit',
        'faculty_performance.view', 'faculty_performance.print',
    },
    'exam': {
        'dashboard.view',
        'timetable.view',
        'courses.view',
        'rooms.view',
        'exams.view', 'exams.manage', 'exams.period', 'exams.planning', 'exams.department_schedule', 'exams.assign_room',
        'academic_calendar.manage',
        'uploads.serve',
        'tools.view',
        'profile.view', 'profile.edit',
    },
}
