"""Permission labels — readable Arabic names for every permission string.

Why this module
---------------
``ROLE_PERMISSIONS`` is a machine table: ``rooms.create``, ``exams.edit`` …
Perfect for a gate, unreadable for a human.  The dean reading the assignment
screen used to be shown the raw strings (``rooms.manage``) or nothing at all,
which is why the screen read as a debug dump.

This module turns one permission string into everything the UI needs to draw a
chip: an Arabic label, the domain it belongs to (القاعات، الجدول الامتحانات…) and
the action it performs (عرض / إضافة / حذف…).  Grouping by domain is what makes a
long list skimmable — a wall of chips is noise, a chip per domain with a heading
is a summary.

The contract that matters: **an unknown permission string must never break a
page.**  A permission added to a role without a label here still renders, with
the raw string as its label and a domain derived from its prefix.  The tables
are therefore a presentation layer, never a gate.
"""

from __future__ import annotations

# /     /     >---- النطاق: مفتاح البادئة (rooms.* → rooms) مع ترتيبه في العرض
# /     /     >---- والأيقونة التي تميّزه في الواجهة.
PERMISSION_DOMAINS: dict[str, dict] = {
    'rooms': {'label': 'القاعات', 'icon': 'meeting_room', 'order': 1},
    'timetable': {'label': 'الجدول الدراسي', 'icon': 'calendar_today', 'order': 2},
    'exams': {'label': 'جدول الامتحانات', 'icon': 'grading', 'order': 3},
    'teachers': {'label': 'أعضاء هيئة التدريس', 'icon': 'school', 'order': 4},
    'departments': {'label': 'الأقسام', 'icon': 'account_tree', 'order': 5},
    'courses': {'label': 'المقررات الدراسية', 'icon': 'menu_book', 'order': 6},
    'faculty_performance': {'label': 'قائمة معدل الأداء', 'icon': 'monitoring', 'order': 7},
    'history': {'label': 'سجل التغييرات', 'icon': 'history', 'order': 8},
    'dashboard': {'label': 'لوحة التحكم', 'icon': 'dashboard', 'order': 9},
    'profile': {'label': 'الملف الشخصي', 'icon': 'manage_accounts', 'order': 10},
    'messages': {'label': 'الرسائل', 'icon': 'mail', 'order': 11},
    'materials': {'label': 'المواد', 'icon': 'inventory_2', 'order': 12},
    'course_content': {'label': 'محتوى المقررات', 'icon': 'description', 'order': 13},
    'academic_calendar': {'label': 'التقويم الأكاديمي', 'icon': 'event', 'order': 14},
    'reports': {'label': 'التقارير', 'icon': 'analytics', 'order': 15},
    'uploads': {'label': 'الملفات المرفوعة', 'icon': 'upload_file', 'order': 16},
    'tools': {'label': 'الأدوات', 'icon': 'build', 'order': 17},
}

#: Last resort for a domain nobody declared: shown after every known one.
UNKNOWN_DOMAIN_ORDER = 999

# /     /     >---- الاسم العربي لكل صلاحية. المفتاح الكامل (بادئة.فعل) لا
# /     /     >---- الفعل وحده: «تعيين قاعة» و«إضافة قاعة» اسمان مختلفان.
PERMISSION_LABELS: dict[str, str] = {
    'dashboard.view': 'عرض لوحة التحكم',
    'dashboard.nav': 'التنقل بين اللوحات',
    'departments.view': 'عرض الأقسام',
    'departments.manage': 'إدارة الأقسام',
    'teachers.view': 'عرض أعضاء هيئة التدريس',
    'teachers.manage': 'إدارة أعضاء هيئة التدريس',
    'teachers.assign': 'تكليف مهام إدارية',
    'teachers.lookup_lists.manage': 'إدارة القوائم المرجعية',
    'courses.view': 'عرض المقررات الدراسية',
    'courses.manage': 'إدارة المقررات الدراسية',
    'timetable.view': 'عرض الجدول الدراسي',
    'timetable.edit': 'تعديل الجدول الدراسي',
    'academic_calendar.manage': 'إدارة التقويم الأكاديمي',
    'course_content.view': 'عرض محتوى المقررات',
    'course_content.manage': 'إدارة محتوى المقررات',
    'course_content.create': 'إضافة محتوى مقرر',
    'course_content.edit': 'تعديل محتوى مقرر',
    'course_content.submit': 'رفع محتوى مقرر للمراجعة',
    'course_content.review': 'مراجعة محتوى مقرر',
    'course_content.publish': 'نشر محتوى مقرر',
    'course_content.unpublish': 'إلغاء نشر محتوى مقرر',
    'reports.view': 'عرض التقارير',
    'uploads.view': 'عرض الملفات المرفوعة',
    'uploads.serve': 'تحميل الملفات المرفوعة',
    'profile.view': 'عرض الملف الشخصي',
    'profile.edit': 'تعديل الملف الشخصي',
    'faculty_performance.view': 'عرض قائمة معدل الأداء',
    'faculty_performance.view_summary': 'عرض ملخص معدل الأداء',
    'faculty_performance.edit_research': 'تعديل البحث العلمي',
    'faculty_performance.edit_assignments': 'تعديل التكليفات',
    'faculty_performance.edit_leaves': 'تعديل الإجازات',
    'faculty_performance.print': 'طباعة قائمة معدل الأداء',
    'history.view': 'عرض سجل التغييرات',
    'tools.view': 'عرض الأدوات',
    'rooms.view': 'عرض القاعات',
    'rooms.manage': 'إدارة القاعات',
    'rooms.create': 'إضافة قاعة',
    'rooms.edit': 'تعديل قاعة',
    'rooms.delete': 'حذف قاعة',
    'exams.view': 'عرض جدول الامتحانات',
    'exams.manage': 'إدارة جدول الامتحانات',
    'exams.period': 'إدارة فترة الامتحانات',
    'exams.planning': 'تخطيط توزيع الامتحانات',
    'exams.department_schedule': 'جدولة امتحانات القسم',
    'exams.assign_room': 'تعيين قاعة الامتحان',
    'exams.create': 'إضافة امتحان',
    'exams.edit': 'تعديل امتحان',
    'exams.delete': 'حذف امتحان',
    'messages.view': 'عرض الرسائل',
    'messages.review': 'مراجعة الرسائل',
    'materials.manage': 'إدارة المواد',
}

# /     /     >---- الفعل الذي تمارسه الصلاحية. يُستعمل لاسم عربي مختصر في
# /     /     >---- رأس المجموعة، ولتمييز الصلاحيات المتشابهة الاسم.
PERMISSION_ACTIONS: dict[str, str] = {
    'dashboard.view': 'view',
    'dashboard.nav': 'nav',
    'departments.view': 'view',
    'departments.manage': 'manage',
    'teachers.view': 'view',
    'teachers.manage': 'manage',
    'teachers.assign': 'assign',
    'teachers.lookup_lists.manage': 'manage',
    'courses.view': 'view',
    'courses.manage': 'manage',
    'timetable.view': 'view',
    'timetable.edit': 'edit',
    'academic_calendar.manage': 'manage',
    'course_content.view': 'view',
    'course_content.manage': 'manage',
    'course_content.create': 'create',
    'course_content.edit': 'edit',
    'course_content.submit': 'submit',
    'course_content.review': 'review',
    'course_content.publish': 'publish',
    'course_content.unpublish': 'unpublish',
    'reports.view': 'view',
    'uploads.view': 'view',
    'uploads.serve': 'serve',
    'profile.view': 'view',
    'profile.edit': 'edit',
    'faculty_performance.view': 'view',
    'faculty_performance.view_summary': 'view',
    'faculty_performance.edit_research': 'edit',
    'faculty_performance.edit_assignments': 'edit',
    'faculty_performance.edit_leaves': 'edit',
    'faculty_performance.print': 'print',
    'history.view': 'view',
    'tools.view': 'view',
    'rooms.view': 'view',
    'rooms.manage': 'manage',
    'rooms.create': 'create',
    'rooms.edit': 'edit',
    'rooms.delete': 'delete',
    'exams.view': 'view',
    'exams.manage': 'manage',
    'exams.period': 'period',
    'exams.planning': 'plan',
    'exams.department_schedule': 'edit',
    'exams.assign_room': 'assign',
    'exams.create': 'create',
    'exams.edit': 'edit',
    'exams.delete': 'delete',
    'messages.view': 'view',
    'messages.review': 'review',
    'materials.manage': 'manage',
}

ACTION_LABELS: dict[str, str] = {
    'view': 'عرض',
    'nav': 'تنقل',
    'create': 'إضافة',
    'edit': 'تعديل',
    'delete': 'حذف',
    'assign': 'تعيين',
    'period': 'فترة',
    'plan': 'تخطيط',
    'manage': 'إدارة',
    'submit': 'رفع',
    'review': 'مراجعة',
    'publish': 'نشر',
    'unpublish': 'إلغاء نشر',
    'serve': 'تحميل',
    'print': 'طباعة',
}


def _domain_key(permission: str) -> str:
    """The declared domain of *permission*, else its prefix before the dot."""
    prefix = str(permission).split('.', 1)[0]
    return prefix if prefix in PERMISSION_DOMAINS else prefix


def describe_permission(permission: str) -> dict:
    """Everything the UI needs to draw one permission chip. Never raises.

    An undeclared permission falls back to its raw string as label and a domain
    derived from the prefix, so adding a permission to a role can never blank
    the page that lists it.
    """
    perm = str(permission or '')
    domain = _domain_key(perm)
    domain_meta = PERMISSION_DOMAINS.get(domain, {})
    action = PERMISSION_ACTIONS.get(perm, '')
    return {
        'permission': perm,
        'label': PERMISSION_LABELS.get(perm, perm),
        'domain': domain,
        'domain_label': domain_meta.get('label', domain),
        'domain_order': domain_meta.get('order', UNKNOWN_DOMAIN_ORDER),
        'icon': domain_meta.get('icon', 'lock'),
        'action': action,
        'action_label': ACTION_LABELS.get(action, ''),
    }


def group_permissions(perms) -> list:
    """Describe *perms*, grouped by domain and ordered for reading.

    Domains come in ``PERMISSION_DOMAINS`` order (القاعات، الجدول، …) and any
    undeclared domain is appended last.  Permissions keep the order they were
    given inside their domain, so a caller can pass the page's own declaration
    order and have the chips read in that order too.
    """
    groups: dict[str, dict] = {}
    for permission in perms or ():
        item = describe_permission(permission)
        group = groups.get(item['domain'])
        if group is None:
            group = {
                'domain': item['domain'],
                'domain_label': item['domain_label'],
                'icon': item['icon'],
                'order': item['domain_order'],
                'items': [],
            }
            groups[item['domain']] = group
        group['items'].append(item)
    return sorted(groups.values(), key=lambda g: (g['order'], g['domain']))