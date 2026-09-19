"""Role definitions — the six system roles and their display labels.

The former ``support_admin`` role was removed; existing accounts were
promoted to ``super_admin`` by the schema migration.
"""

# ── أسماء الأدوار (أسماء العرض بالعربي) ───────────────────────────────────────
# /     /     >---- كل دور في النظام عنده اسم عربي يظهر في الواجهة
ROLE_NAMES = {
    'super_admin': 'مدير النظام',
    'research_development': 'قسم البحث والتطوير والمناهج',
    'faculty_affairs': 'مكتب إدارة أعضاء هيئة التدريس',
    'head_of_department': 'رئيس القسم',
    'teacher': 'عضو هيئة تدريس',
    'exam': 'قسم الإدارة والامتحانات',
}

# /     /     >---- اسم ثاني لنفس القاموس (للتوافق مع الأكواد القديمة)
ROLE_LABELS = ROLE_NAMES

# /     /     >---- قائمة كل الأدوار (للترتيب والعد)
ALL_ROLES = tuple(ROLE_NAMES)