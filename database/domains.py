"""Logical database domains.

The database is a single physical SQLite file (``database/data.db``), but every
table belongs to exactly one *named domain*.  These domains are the "parts" of
the system: Identity, Academic, Scheduling, Examinations, Communication,
Auditing.

This module is the single source of truth for the domain model:

* :data:`DOMAINS` — ordered mapping ``domain_key -> DomainInfo``.
* :data:`TABLE_DOMAIN` — reverse map ``table_name -> domain_key``.
* :func:`sync_domain_registry` — persists the mapping into a
  ``schema_domains`` registry table on every startup, so the database
  self-describes its own parts.
* ``python -m database.domains`` — prints the current mapping.

Flask-independent: functions accept a configured ``sqlite3.Connection``.
"""

from __future__ import annotations

import sqlite3
from collections import OrderedDict

# /     /     >---- ترتيب المجالات (الأقسام المنطقية) في النظام
DOMAIN_ORDER = [
    'identity',
    'academic',
    'scheduling',
    'examinations',
    'communication',
    'auditing',
]

# /     /     >---- المجالات الكاملة: لكل مجال اسم وتوصيف وجداوله
DOMAINS: OrderedDict[str, dict] = OrderedDict(
    (
        # ── الهوية: الحسابات والمصادقة ───────────────────────────────
        (
            'identity',
            {
                'name_en': 'Identity',
                'name_ar': 'الهوية',
                'description_en': 'System accounts, authentication and access.',
                'description_ar': 'حسابات النظام والمصادقة والوصول.',
                'tables': ['users', 'password_resets'],
            },
        ),
        # ── الكلية: الأقسام والمدرسين والمقررات ──────────────────────
        (
            'academic',
            {
                'name_en': 'Academic',
                'name_ar': 'الكلية',
                'description_en': 'Departments, faculty, courses and study plans.',
                'description_ar': 'الأقسام وهيئة التدريس والمقررات والخطط الدراسية.',
                'tables': [
                    'departments',
                    'department_majors',
                    'teachers',
                    'teacher_departments',
                    'qualifications',
                    'academic_ranks',
                    'classifications',
                    'rank_rules',
                    'courses',
                    'course_departments',
                    'course_prerequisites',
                    'course_content_submissions',
                    'course_content_curriculum',
                    'course_vocabulary',
                    'teacher_course_files',
                    'faculty_attendance',
                ],
            },
        ),
        # ── الجدولة: القاعات والجداول وطلبات التبديل ──────────────────
        (
            'scheduling',
            {
                'name_en': 'Scheduling',
                'name_ar': 'الجدولة',
                'description_en': 'Rooms, time periods and the weekly timetable.',
                'description_ar': 'القاعات والفترات الزمنية والجدول الأسبوعي.',
                'tables': [
                    'rooms',
                    'room_types',
                    'room_statuses',
                    'floors',
                    'period_settings',
                    'timetable',
                ],
            },
        ),
        # ── الامتحانات: الجدول والفترات ───────────────────────────────
        (
            'examinations',
            {
                'name_en': 'Examinations',
                'name_ar': 'الامتحانات',
                'description_en': 'Exam schedule, periods and settings.',
                'description_ar': 'جدول الامتحانات وفتراتها وإعداداتها.',
                'tables': ['exam_schedule', 'exam_settings'],
            },
        ),
        # ── التواصل: الإشعارات والرسائل والمواد ───────────────────────
        (
            'communication',
            {
                'name_en': 'Communication',
                'name_ar': 'التواصل',
                'description_en': 'Notifications, announcements, messages and shared materials.',
                'description_ar': 'الإشعارات والإعلانات والرسائل والمواد المشتركة.',
                'tables': [
                    'notifications',
                    'department_announcements',
                    'teacher_messages',
                    'message_replies',
                    'teacher_documents',
                    'teacher_materials',
                    'teacher_requests',
                ],
            },
        ),
        # ── التدقيق: سجل النشاط ───────────────────────────────────────
        (
            'auditing',
            {
                'name_en': 'Auditing',
                'name_ar': 'التدقيق',
                'description_en': 'System activity and change history.',
                'description_ar': 'سجل نشاط النظام وتغييراته.',
                'tables': ['history'],
            },
        ),
    )
)

# /     /     >---- قائمة كل الجداول من كل المجالات
ALL_DOMAIN_TABLES: list[str] = [t for d in DOMAINS.values() for t in d['tables']]

# /     /     >---- خريطة عكسية: اسم الجدول ← المفتاح ديالو
TABLE_DOMAIN: dict[str, str] = {t: k for k, d in DOMAINS.items() for t in d['tables']}

# ─────────────────────────────────────────────

# /     /     >---- نرجع مفتاح المجال اللي الجدول تابع له
def table_domain(table_name: str) -> str | None:
    """Return the domain key a table belongs to, or ``None`` if unknown."""
    return TABLE_DOMAIN.get(table_name)

# ─────────────────────────────────────────────

# /     /     >---- نرجع قائمة الجداول في مجال معين
def tables_in_domain(domain_key: str) -> list[str]:
    """Return the ordered list of tables for a domain key."""
    info = DOMAINS.get(domain_key)
    return list(info['tables']) if info else []

# ─────────────────────────────────────────────

# /     /     >---- نجمع الجداول حسب مجالاتها مع الحفاظ على الترتيب
def domains_for_tables(table_names) -> list[dict]:
    """Group an iterable of table names by domain, preserving domain order.

    Returns a list of ``{'domain': key, 'name_ar': ..., 'tables': [...]}``
    dicts containing only the tables that belong to a known domain.
    """
    # /     /     >---- نجهز قواميس لكل مجال
    grouped: OrderedDict[str, list[str]] = OrderedDict((k, []) for k in DOMAIN_ORDER)
    for name in table_names:
        key = table_domain(name)
        if key is not None and name not in grouped[key]:
            grouped[key].append(name)
    # /     /     >---- نبني النتيجة النهائية مع المعلومات الوجيهة
    return [
        {
            'domain': key,
            'name_en': DOMAINS[key]['name_en'],
            'name_ar': DOMAINS[key]['name_ar'],
            'description_ar': DOMAINS[key]['description_ar'],
            'tables': grouped[key],
        }
        for key in DOMAIN_ORDER
        if grouped[key]
    ]

# ─────────────────────────────────────────────

# /     /     >---- نملأ جدول سجل المجالات schema_domains في قاعدة البيانات
def sync_domain_registry(conn: sqlite3.Connection) -> None:
    """Create (if needed) and populate the ``schema_domains`` registry table.

    Records every business table's domain so the database self-describes its
    named parts.  Safe to run on every startup.
    """
    # /     /     >---- نصاوع الجدول إذا ما هو موجود
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_domains (
            domain     TEXT NOT NULL,
            name_en    TEXT NOT NULL,
            name_ar    TEXT NOT NULL,
            table_name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (domain, table_name)
        )
        """
    )
    # /     /     >---- نمسح القديم ونعبيه من جديد
    conn.execute('DELETE FROM schema_domains')
    rows = []
    for domain_key, info in DOMAINS.items():
        for sort_order, table_name in enumerate(info['tables']):
            rows.append((domain_key, info['name_en'], info['name_ar'], table_name, sort_order))
    conn.executemany(
        'INSERT INTO schema_domains (domain, name_en, name_ar, table_name, sort_order) '
        'VALUES (?, ?, ?, ?, ?)',
        rows,
    )

# ─────────────────────────────────────────────

# /     /     >---- نطبع التقسيم المنطقي لقاعدة البيانات بالأمر المباشر
def print_domains(conn: sqlite3.Connection | None = None) -> None:
    """Print the live database grouped by domain."""
    # /     /     >---- إذا ما معطيش اتصال نفتح لقاعدة البيانات الافتراضية
    if conn is None:
        db_path = __import__('config', fromlist=['Config']).Config.DATABASE
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

    # /     /     >---- نجمع كل الجداول الموجودة فعلياً
    tables = {
        row['name']
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    print('Database domains (logical parts of one SQLite file)\n')
    # /     /     >---- نطبع كل مجموعة مع جداولها وحالة وجودها
    for group in domains_for_tables(tables):
        print(f"{group['domain']} — {group['name_ar']} ({group['name_en']})")
        print(f"  {group['description_ar']}")
        for t in group['tables']:
            present = '✓' if t in tables else '✗'
            print(f'    [{present}] {t}')
        print()
    # /     /     >---- الجداول اللي ما فيش ليهن مجال
    unknown = sorted(t for t in tables if t not in TABLE_DOMAIN and not t.startswith('sqlite_'))
    if unknown:
        print('Ungrouped / system tables:')
        for t in unknown:
            print(f'    [–] {t}')
        print()

# ─────────────────────────────────────────────

# /     /     >---- نقطة الدخول: python -m database.domains
if __name__ == '__main__':
    import sys

    sys.stdout.reconfigure(encoding='utf-8')
    print_domains()