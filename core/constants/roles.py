"""Role definitions — the six system roles and their display labels.

The former ``support_admin`` role was removed; existing accounts were
promoted to ``super_admin`` by the schema migration.
"""

# ── Role names (Arabic display labels) ────────────────────────────────────────
ROLE_NAMES = {
    'super_admin': 'مدير النظام',
    'research_development': 'قسم البحث والتطوير والمناهج',
    'faculty_affairs': 'مكتب إدارة أعضاء هيئة التدريس',
    'head_of_department': 'رئيس القسم',
    'teacher': 'عضو هيئة تدريس',
    'exam': 'قسم الإدارة والامتحانات',
}

# Backward-compatible alias used by the template context processor.
ROLE_LABELS = ROLE_NAMES

ALL_ROLES = tuple(ROLE_NAMES)
