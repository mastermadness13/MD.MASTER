"""Role definitions — the seven system roles and their display labels.

The former ``support_admin`` role was removed; the ``super_admin`` role was
removed entirely and the office-manager (``faculty_affairs``) account is now
the bootstrap user.
"""

# ── أسماء الأدوار (أسماء العرض بالعربي) ───────────────────────────────────────
# /     /     >---- كل دور في النظام عنده اسم عربي يظهر في الواجهة
ROLE_NAMES = {
    'research_development': 'قسم البحث والتطوير والمناهج',
    'faculty_affairs': 'مكتب إدارة أعضاء هيئة التدريس',
    'head_of_department': 'رئيس القسم العلمي',
    'teacher': 'عضو هيئة تدريس',
    'exam': 'قسم الدراسة والامتحانات',
    'dean': 'العميد',
    'visitor': 'الزائر العام',
}

# /     /     >---- اسم ثاني لنفس القاموس (للتوافق مع الأكواد القديمة)
ROLE_LABELS = ROLE_NAMES

# /     /     >---- قائمة كل الأدوار (للترتيب والعد)
ALL_ROLES = tuple(ROLE_NAMES)