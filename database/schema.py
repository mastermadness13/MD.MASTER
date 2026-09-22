"""Schema management and migrations for SQLite.

Contains ``ensure_schema`` plus every migration helper.  Idempotent and safe
to run on every startup.  Flask-independent: callers pass a configured
``sqlite3.Connection``.

Logical organization
--------------------
Every table belongs to one of the named database domains defined in
``database/domains.py`` (Identity, Academic, Scheduling, Examinations,
Communication, Auditing).  On every startup ``ensure_schema`` writes this
mapping into the ``schema_domains`` registry table so the single physical
database self-describes its parts.  See ``database/schema_domains.md``.
"""

from __future__ import annotations

import datetime
import os
import re
import secrets
import sqlite3
from pathlib import Path

from database.domains import sync_domain_registry
from database.seed_data import (
    COURSE_ICON_MAP,
    DEFAULT_ACADEMIC_RANKS,
    DEFAULT_CLASSIFICATIONS,
    DEFAULT_COURSE_ICON,
    DEFAULT_FLOORS,
    DEFAULT_PERIODS,
    DEFAULT_QUALIFICATIONS,
    DEFAULT_RANK_RULES,
    DEFAULT_ROOM_STATUSES,
    DEFAULT_ROOM_TYPES,
    DEFAULT_SPECIALIZATIONS,
)


# /     /     >---- نجيب أسماء أعمدة جدول معين (تجمع لفحص العمود موجود ولا لأ)
def _get_column_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    try:
        rows = conn.execute(f'PRAGMA table_info({table_name})').fetchall()
    except sqlite3.OperationalError:
        return set()
    return {row[1] for row in rows}


# /     /     >---- نضيف عمود لو ما هوش موجود (ونتجاهل الخطأ لو موجود)
def _safe_add_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    try:
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}')
    except sqlite3.OperationalError:
        pass


# /     /     >---- نتأكد جدول الفترات فيه كل الفترات الافتراضية
def _ensure_periods_table(conn: sqlite3.Connection) -> None:
    try:
        rows = conn.execute('SELECT code, label FROM period_settings').fetchall()
    except sqlite3.OperationalError:
        return
    existing_codes = {row[0] for row in rows}

    # /     /     >---- كل فترة جديدة نضيفها (الباقية ماشين حالها)
    for code, label, start_time, end_time, is_enabled, sort_order in DEFAULT_PERIODS:
        if code not in existing_codes:
            conn.execute(
                """
                INSERT INTO period_settings (code, label, start_time, end_time, is_enabled, sort_order)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (code, label, start_time, end_time, is_enabled, sort_order),
            )


# /     /     >---- نتأكد جداول القوائم المرجعية موجودة ومتعبّاة بالبيانات
def _ensure_lookup_tables(conn: sqlite3.Connection) -> None:
    existing_tables = {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }

    table_defs = {
        'room_types': '''
            CREATE TABLE IF NOT EXISTS room_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name_ar TEXT NOT NULL,
                name_en TEXT NOT NULL,
                icon TEXT,
                css_class TEXT,
                sort_order INTEGER DEFAULT 0,
                UNIQUE(name_ar),
                UNIQUE(name_en)
            )
        ''',
        'room_statuses': '''
            CREATE TABLE IF NOT EXISTS room_statuses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name_ar TEXT NOT NULL,
                name_en TEXT NOT NULL,
                css_class TEXT,
                sort_order INTEGER DEFAULT 0,
                UNIQUE(name_ar),
                UNIQUE(name_en)
            )
        ''',
        'floors': '''
            CREATE TABLE IF NOT EXISTS floors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name_ar TEXT NOT NULL,
                name_en TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                UNIQUE(name_ar),
                UNIQUE(name_en)
            )
        ''',
        'qualifications': '''
            CREATE TABLE IF NOT EXISTS qualifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name_ar TEXT NOT NULL,
                name_en TEXT NOT NULL,
                UNIQUE(name_ar),
                UNIQUE(name_en)
            )
        ''',
        'academic_ranks': '''
            CREATE TABLE IF NOT EXISTS academic_ranks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name_ar TEXT NOT NULL,
                name_en TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                UNIQUE(name_ar),
                UNIQUE(name_en)
            )
        ''',
        'classifications': '''
            CREATE TABLE IF NOT EXISTS classifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name_ar TEXT NOT NULL,
                name_en TEXT NOT NULL,
                UNIQUE(name_ar),
                UNIQUE(name_en)
            )
        ''',
        'rank_rules': '''
            CREATE TABLE IF NOT EXISTS rank_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                qualification_id INTEGER NOT NULL REFERENCES qualifications(id) ON DELETE CASCADE,
                rank_id INTEGER NOT NULL REFERENCES academic_ranks(id) ON DELETE CASCADE,
                UNIQUE(qualification_id, rank_id)
            )
        '''
    }
    for table_name, ddl in table_defs.items():
        if table_name not in existing_tables:
            conn.execute(ddl)

    # /     /     >---- الجداول الافتراضية (الأنواع، الحالات، الطوابق، المؤهلات، الرتب، التصنيفات)
    tables_data = [
        ('room_types', ['name_ar', 'name_en', 'icon', 'css_class', 'sort_order'],
         DEFAULT_ROOM_TYPES,
         'name_ar'),
        ('room_statuses', ['name_ar', 'name_en', 'css_class', 'sort_order'],
         DEFAULT_ROOM_STATUSES,
         'name_ar'),
        ('floors', ['name_ar', 'name_en', 'sort_order'],
         DEFAULT_FLOORS,
         'name_ar'),
        ('qualifications', ['name_ar', 'name_en'],
         DEFAULT_QUALIFICATIONS,
         'name_ar'),
        ('academic_ranks', ['name_ar', 'name_en', 'sort_order'],
         DEFAULT_ACADEMIC_RANKS,
         'name_ar'),
        ('classifications', ['name_ar', 'name_en'],
         DEFAULT_CLASSIFICATIONS,
         'name_ar'),
    ]

    # /     /     >---- كل جدول: نضيف السطور اللي ناقصة حسب العمود الفريد
    for table_name, columns, seed_data, unique_col in tables_data:
        existing = {row[unique_col] for row in conn.execute(
            f'SELECT "{unique_col}" FROM "{table_name}"'
        ).fetchall()}
        for row_data in seed_data:
            if row_data[0] not in existing:
                col_names = ', '.join(f'"{c}"' for c in columns)
                placeholders = ', '.join('?' for _ in columns)
                conn.execute(
                    f'INSERT INTO "{table_name}" ({col_names}) VALUES ({placeholders})',
                    row_data,
                )

    # /     /     >---- نعبّي قواعد الرتب من أسماء المؤهلات والرتب
    rule_data = []
    for qual_name, rank_name in DEFAULT_RANK_RULES:
        q = conn.execute(
            'SELECT id FROM qualifications WHERE name_ar = ?', (qual_name,)
        ).fetchone()
        r = conn.execute(
            'SELECT id FROM academic_ranks WHERE name_ar = ?', (rank_name,)
        ).fetchone()
        if q and r and not conn.execute(
            'SELECT 1 FROM rank_rules WHERE qualification_id = ? AND rank_id = ?',
            (q['id'], r['id']),
        ).fetchone():
            rule_data.append((q['id'], r['id']))
    if rule_data:
        conn.executemany(
            'INSERT INTO rank_rules (qualification_id, rank_id) VALUES (?, ?)',
            rule_data,
        )

    # /     /     >---- التخصصات: لكل قسم تخصصاته الأكاديمية
    conn.execute(
        '''CREATE TABLE IF NOT EXISTS specializations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            department_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            UNIQUE(department_id, name)
        )'''
    )
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_specializations_department ON specializations(department_id)'
    )
    # /     /     >---- نعبّي تخصصات كل قسم (اللي ناقصة فقط)
    for dept_name, spec_names in DEFAULT_SPECIALIZATIONS.items():
        dept = conn.execute(
            'SELECT id FROM departments WHERE name = ?', (dept_name,)
        ).fetchone()
        if not dept:
            continue
        existing = {r[0] for r in conn.execute(
            'SELECT name FROM specializations WHERE department_id = ?', (dept['id'],)
        ).fetchall()}
        for idx, name in enumerate(spec_names):
            if name not in existing:
                conn.execute(
                    'INSERT INTO specializations (department_id, name, sort_order) VALUES (?, ?, ?)',
                    (dept['id'], name, idx + 1),
                )


# /     /     >---- نعيد تسمية قيمة في قائمة مرجعية (مع تحديث كل المراجع)
def _rename_lookup_value(conn: sqlite3.Connection, table: str, name_col: str,
                         teacher_fk_col: str, teacher_text_col: str,
                         old_name: str, new_name: str, links=()) -> None:
    """Rename a lookup value in place (keeps its id) or merge it into an
    existing target row.

    Teacher FK/text columns and lookup junction rows (e.g. ``rank_rules``)
    are updated so every reference keeps working after the rename.
    """
    # /     /     >---- نجيب القيمة القديمة
    old = conn.execute(
        f'SELECT id FROM "{table}" WHERE "{name_col}" = ? LIMIT 1', (old_name,)
    ).fetchone()
    if not old:
        return
    old_id = old[0]
    # /     /     >---- القيمة الجديدة موجودة بالفعل؟ ندمج فيها (الدمج)
    target = conn.execute(
        f'SELECT id FROM "{table}" WHERE "{name_col}" = ? LIMIT 1', (new_name,)
    ).fetchone()
    if target:
        new_id = target[0]
        # /     /     >---- نحوّل مراجع الأساتذة للقيمة الجديدة
        conn.execute(
            f'UPDATE teachers SET "{teacher_fk_col}" = ? WHERE "{teacher_fk_col}" = ?',
            (new_id, old_id),
        )
        for link_table, link_col in links:
            conn.execute(
                f'UPDATE OR IGNORE "{link_table}" SET "{link_col}" = ? WHERE "{link_col}" = ?',
                (new_id, old_id),
            )
            # UPDATE OR IGNORE skips rows that would duplicate an existing
            # (parent x child) pair; those leftovers are exactly the redundant
            # relationships covered by the target value, so drop them before
            # deleting the merged-away lookup row. This keeps the DELETE legal
            # whether the junction FK is ON DELETE CASCADE or NO ACTION.
            conn.execute(
                f'DELETE FROM "{link_table}" WHERE "{link_col}" = ?', (old_id,)
            )
        conn.execute(f'DELETE FROM "{table}" WHERE id = ?', (old_id,))
    else:
        # /     /     >---- ما فيش هدف: نعيد التسمية في مكانها
        conn.execute(
            f'UPDATE "{table}" SET "{name_col}" = ? WHERE id = ?', (new_name, old_id)
        )
    # /     /     >---- نزامن النص الـ denormalised عند الأساتذة في الحالتين
    conn.execute(
        f'UPDATE teachers SET "{teacher_text_col}" = ? WHERE "{teacher_text_col}" = ?',
        (new_name, old_name),
    )


# /     /     >---- نطابق مفردات المؤهلات والرتب والتصنيفات مع القوائم الجديدة
def _migrate_lookup_vocabulary(conn: sqlite3.Connection) -> None:
    """Align qualification / rank / classification vocabulary with the
    design's pickers, migrating legacy names in place.

    Idempotent: safe to run on every startup, including fresh installs
    where the legacy names do not exist yet.
    """
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()}
    has_rank_rules = 'rank_rules' in tables
    has_workload = 'faculty_workload_rules' in tables
    rank_links = []
    qual_links = []
    if has_rank_rules:
        rank_links.append(('rank_rules', 'rank_id'))
        qual_links.append(('rank_rules', 'qualification_id'))
    if has_workload:
        # faculty_workload_rules.rank_id references academic_ranks(id) and
        # is NOT NULL — legacy rows must follow a merged-away rank too.
        rank_links.append(('faculty_workload_rules', 'rank_id'))
    rank_links = tuple(rank_links)
    qual_links = tuple(qual_links)

    # /     /     >---- المؤهلات: دبلوم ← دبلوم عالي
    if 'qualifications' in tables:
        _rename_lookup_value(conn, 'qualifications', 'name_ar',
                             'qualification_id', 'qualification',
                             'دبلوم', 'دبلوم عالي', links=qual_links)
    # /     /     >---- الرتب: محاضر مساعد ← مساعد محاضر، وأستاذ متعاون ← معيد
    if 'academic_ranks' in tables:
        _rename_lookup_value(conn, 'academic_ranks', 'name_ar',
                             'rank_id', 'academic_rank',
                             'محاضر مساعد', 'مساعد محاضر', links=rank_links)
        _rename_lookup_value(conn, 'academic_ranks', 'name_ar',
                             'rank_id', 'academic_rank',
                             'أستاذ متعاون', 'معيد', links=rank_links)
    # /     /     >---- التصنيفات: توحيد أسماء الأعضاء
    if 'classifications' in tables:
        _rename_lookup_value(conn, 'classifications', 'name_ar',
                             'classification_id', 'classification',
                             'عضو هيئة تدريس قار', 'قار')
        _rename_lookup_value(conn, 'classifications', 'name_ar',
                             'classification_id', 'classification',
                             'عضو هيئة تدريس متعاون', 'متعاون')
        _rename_lookup_value(conn, 'classifications', 'name_ar',
                             'classification_id', 'classification',
                             'معيد', 'قار')
    if has_rank_rules:
        # /     /     >---- ننشف أي تكرار خلفه الدمج
        conn.execute('''
            DELETE FROM rank_rules WHERE id NOT IN (
                SELECT MIN(id) FROM rank_rules
                GROUP BY qualification_id, rank_id
            )
        ''')
    conn.commit()


# /     /     >---- نملأ أعمدة FK للقاعات من النصوص القديمة
def _backfill_room_fks(conn: sqlite3.Connection) -> None:
    for col, fk_table, src_col in [
        ('room_type_id', 'room_types', 'type'),
        ('status_id', 'room_statuses', 'status'),
        ('floor_id', 'floors', 'location'),
    ]:
        existing_cols = _get_column_names(conn, 'rooms')
        # /     /     >---- نضيف العمود لو ما هوش موجود
        if col not in existing_cols:
            _safe_add_column(conn, 'rooms', col, f'INTEGER REFERENCES "{fk_table}"(id) ON DELETE SET NULL')
        # /     /     >---- نطابق القيمة النصية مع المعرف في الجدول المرجعي
        conn.execute(f'''
            UPDATE rooms SET {col} = (
                SELECT id FROM "{fk_table}" WHERE name_ar = rooms."{src_col}" LIMIT 1
            ) WHERE {col} IS NULL
        ''')


# /     /     >---- نملأ أعمدة FK للأساتذة من النصوص القديمة
def _backfill_teacher_fks(conn: sqlite3.Connection) -> None:
    for col, fk_table, src_col in [
        ('qualification_id', 'qualifications', 'qualification'),
        ('rank_id', 'academic_ranks', 'academic_rank'),
        ('classification_id', 'classifications', 'classification'),
    ]:
        existing_cols = _get_column_names(conn, 'teachers')
        # /     /     >---- نضيف العمود لو ما هوش موجود
        if col not in existing_cols:
            _safe_add_column(conn, 'teachers', col, f'INTEGER REFERENCES "{fk_table}"(id) ON DELETE SET NULL')
        # /     /     >---- نطابق النص مع المعرف
        conn.execute(f'''
            UPDATE teachers SET {col} = (
                SELECT id FROM "{fk_table}" WHERE name_ar = teachers."{src_col}" LIMIT 1
            ) WHERE {col} IS NULL
        ''')


# /     /     >---- نتأكد فهارس التشغيل الأساسية موجودة
def _ensure_runtime_indexes(conn: sqlite3.Connection) -> None:
    existing_tables = {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }

    # /     /     >---- فهارس الأساتذة والمقررات
    if 'teachers' in existing_tables:
        conn.execute('CREATE INDEX IF NOT EXISTS idx_teachers_department ON teachers(department)')
    if 'courses' in existing_tables:
        conn.execute('CREATE INDEX IF NOT EXISTS idx_courses_department_year ON courses(department, year)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_courses_code ON courses(code)')
    # /     /     >---- فهارس الجدول الدراسي
    if 'timetable' in existing_tables:
        conn.execute('CREATE INDEX IF NOT EXISTS idx_timetable_day_semester ON timetable(day, semester)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_timetable_course_id ON timetable(course_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_timetable_teacher_id ON timetable(teacher_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_timetable_room_id ON timetable(room_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_timetable_created_at ON timetable(created_at DESC)')
    # /     /     >---- فهارس المتطلبات السابقة
    if 'course_prerequisites' in existing_tables:
        conn.execute('CREATE INDEX IF NOT EXISTS idx_course_prerequisites_course ON course_prerequisites(course_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_course_prerequisites_prereq ON course_prerequisites(prerequisite_id)')
    # /     /     >---- فهارس المستخدمين
    if 'teachers' in existing_tables:
        conn.execute('CREATE INDEX IF NOT EXISTS idx_teachers_user_id ON teachers(user_id)')
    if 'users' in existing_tables:
        conn.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_users_department_id ON users(department_id)')
    # /     /     >---- فهارس جدول الامتحانات
    if 'exam_schedule' in existing_tables:
        conn.execute('CREATE INDEX IF NOT EXISTS idx_exam_schedule_department_id ON exam_schedule(department_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_exam_schedule_exam_date ON exam_schedule(exam_date)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_exam_schedule_course_id ON exam_schedule(course_id)')


# /     /     >---- نعيد بناء الجداول اللي حرجتها department_id مش SET NULL
def _migrate_department_fks(conn: sqlite3.Connection) -> None:
    """Recreate tables whose department_id FK is not ON DELETE SET NULL.

    Builds CREATE TABLE SQL programmatically from PRAGMA table_info and
    PRAGMA foreign_key_list instead of manipulating raw SQL text with regex.
    Discovers foreign keys referencing departments(id) dynamically.
    """
    # /     /     >---- نجمع الجداول اللي فيها FK للقسم بدون SET NULL
    tables_to_migrate = []
    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        table = row[0]
        for fk in conn.execute(f'PRAGMA foreign_key_list("{table}")'):
            if fk["table"] == "departments" and fk["on_delete"] != "SET NULL":
                tables_to_migrate.append(table)
                break

    if not tables_to_migrate:
        return 0

    # /     /     >---- نطفّي قيود FK مؤقتاً نهار إعادة البناء
    conn.execute("PRAGMA foreign_keys = OFF")
    migrated = 0

    for table in tables_to_migrate:
        # /     /     >---- نجيب تعريف الجدول القديم من PRAGMA
        col_rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        fk_rows = conn.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()
        idx_rows = conn.execute(f'PRAGMA index_list("{table}")').fetchall()

        old_sql_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        has_autoinc = 'AUTOINCREMENT' in (old_sql_row[0] or '').upper() if old_sql_row else False

        # Collect UNIQUE constraints and regular indexes from index_list
        unique_single_cols = set()
        unique_multi = []
        regular_indexes = []
        for idx in idx_rows:
            origin = idx['origin']
            if origin == 'u':
                idx_cols = conn.execute(f'PRAGMA index_xinfo("{idx["name"]}")').fetchall()
                cols = [ic['name'] for ic in idx_cols if ic['key']]
                if len(cols) == 1:
                    unique_single_cols.add(cols[0])
                else:
                    quoted = ', '.join(f'"{c}"' for c in cols)
                    unique_multi.append(f'UNIQUE({quoted})')
            elif origin == 'c':
                regular_indexes.append(idx)

        # /     /     >---- نبني تعريفات الأعمدة
        col_defs = []
        for col in col_rows:
            parts = [f'"{col["name"]}"']
            if col['type']:
                parts.append(col['type'])
            if col['notnull']:
                parts.append('NOT NULL')
            if col['dflt_value'] is not None:
                parts.append(f'DEFAULT {col["dflt_value"]}')
            if col['name'] in unique_single_cols:
                parts.append('UNIQUE')
            if col['pk']:
                parts.append('PRIMARY KEY')
                if has_autoinc:
                    parts.append('AUTOINCREMENT')
            col_defs.append(' '.join(parts))

        # /     /     >---- ندمج أعمدة الـ FK (مركبة محتملة)
        fk_groups = {}
        for fk in fk_rows:
            fk_groups.setdefault(fk['id'], []).append(fk)

        fk_defs = []
        for fk_id, fk_parts in fk_groups.items():
            from_cols = ', '.join(f'"{p["from"]}"' for p in fk_parts)
            to_table = fk_parts[0]['table']
            to_cols = ', '.join(f'"{p["to"]}"' for p in fk_parts)
            on_delete = fk_parts[0]['on_delete']

            # /     /     >---- FK القسم دائماً SET NULL
            if to_table == 'departments':
                fk_defs.append(
                    f'FOREIGN KEY ({from_cols}) REFERENCES "{to_table}" ({to_cols}) ON DELETE SET NULL'
                )
            elif on_delete and on_delete != 'NO ACTION':
                sql = f'FOREIGN KEY ({from_cols}) REFERENCES "{to_table}" ({to_cols}) ON DELETE {on_delete}'
                on_update = fk_parts[0]['on_update']
                if on_update and on_update != 'NO ACTION':
                    sql += f' ON UPDATE {on_update}'
                fk_defs.append(sql)
            else:
                fk_defs.append(
                    f'FOREIGN KEY ({from_cols}) REFERENCES "{to_table}" ({to_cols})'
                )

        # /     /     >---- ننشئ الجدول المؤقت بالتعريف الجديد
        all_defs = col_defs + fk_defs + unique_multi
        temp = f"_migrate_{table}"
        conn.execute(f'DROP TABLE IF EXISTS "{temp}"')
        conn.execute(f'CREATE TABLE "{temp}" ({", ".join(all_defs)})')

        # /     /     >---- ننقل البيانات ونتحقق من التطابق
        old_count = conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
        conn.execute(f'INSERT INTO "{temp}" SELECT * FROM "{table}"')
        new_count = conn.execute(f'SELECT count(*) FROM "{temp}"').fetchone()[0]
        if old_count != new_count:
            conn.execute(f'DROP TABLE "{temp}"')
            conn.execute("PRAGMA foreign_keys = ON")
            raise RuntimeError(
                f"Row count mismatch migrating table \"{table}\": {old_count} vs {new_count}"
            )

        old_ids = {r[0] for r in conn.execute(f'SELECT id FROM "{table}"').fetchall()}
        new_ids = {r[0] for r in conn.execute(f'SELECT id FROM "{temp}"').fetchall()}
        if old_ids != new_ids:
            conn.execute(f'DROP TABLE "{temp}"')
            conn.execute("PRAGMA foreign_keys = ON")
            raise RuntimeError(f"Primary key mismatch migrating table \"{table}\"")

        # /     /     >---- نتحقق الـ FK الجديد للقسم هو SET NULL
        fks_after = conn.execute(f'PRAGMA foreign_key_list("{temp}")').fetchall()
        dept_fk = next((fk for fk in fks_after if fk["table"] == "departments"), None)
        if not dept_fk or dept_fk["on_delete"] != "SET NULL":
            conn.execute(f'DROP TABLE "{temp}"')
            conn.execute("PRAGMA foreign_keys = ON")
            raise RuntimeError(f"FK verification failed for table \"{table}\"")

        # /     /     >---- نستبدل الجدول القديم بالجديد
        conn.execute(f'DROP TABLE "{table}"')
        conn.execute(f'ALTER TABLE "{temp}" RENAME TO "{table}"')

        # /     /     >---- نعيد بناء الفهارس العادية
        for idx in regular_indexes:
            idx_name = idx['name']
            idx_cols = conn.execute(f'PRAGMA index_xinfo("{idx_name}")').fetchall()
            cols = []
            for ic in idx_cols:
                if ic['key']:
                    name = f'"{ic["name"]}"'
                    if ic['desc']:
                        name += ' DESC'
                    cols.append(name)
            if cols:
                unique = 'UNIQUE' if idx['unique'] else ''
                conn.execute(f'CREATE {unique} INDEX IF NOT EXISTS "{idx_name}" ON "{table}" ({", ".join(cols)})')

        migrated += 1

    conn.execute("PRAGMA foreign_keys = ON")
    return migrated


# /     /     >---- نحسب السنة الأكاديمية الحالية من التاريخ
def _computed_academic_year() -> str:
    from datetime import date

    today = date.today()
    if today.month >= 9:
        return f'{today.year}-{today.year + 1}'
    return f'{today.year - 1}-{today.year}'


# /     /     >---- أفضل سنة أكاديمية معروفة لقسم + فصل
def _current_academic_year(conn: sqlite3.Connection, dept_id: int, semester: int) -> str:
    """Best-known current academic year for a department + semester."""
    # /     /     >---- نحاول من نسخ الجدول
    try:
        row = conn.execute(
            'SELECT MAX(academic_year) AS y FROM timetable_versions '
            'WHERE department_id = ? AND semester = ?',
            (dept_id, semester),
        ).fetchone()
        if row and row['y']:
            return row['y']
    except sqlite3.OperationalError:
        pass
    # /     /     >---- وإلا نحسبها من التاريخ
    return _computed_academic_year()


# /     /     >---- نتأكد نسخة الجدول موجودة للقسم+الفصل+السنة (وإلا ننشئها)
def _ensure_version(conn: sqlite3.Connection, dept_id: int, semester: int,
                    academic_year: str) -> int:
    row = conn.execute(
        'SELECT id FROM timetable_versions '
        'WHERE department_id = ? AND semester = ? AND academic_year = ?',
        (dept_id, semester, academic_year),
    ).fetchone()
    if row:
        return row['id']
    cur = conn.execute(
        'INSERT INTO timetable_versions (department_id, semester, academic_year, status) '
        'VALUES (?, ?, ?, ?)',
        (dept_id, semester, academic_year, 'active'),
    )
    return cur.lastrowid


# /     /     >---- نحسب رمز الفصل المسمّى من التاريخ
def _computed_semester_code() -> str:
    """Compute the current named semester code from today's date.

    Uses August 1 as the boundary: months >= 8 → fall, otherwise spring.
    This matches the typical academic calendar where fall starts in August/September.
    """
    from datetime import date

    today = date.today()
    if today.month >= 8:
        return f'fall_{today.year}'
    return f'spring_{today.year}'


# /     /     >---- نحول رقم الفصل (1-7) + السنة إلى رمز فصل مسمّى
def _semester_number_to_code(semester_number: int, academic_year: str) -> str:
    """Convert a semester_number (1-7) + academic_year string to a named semester code.

    Rule: odd semester_number → fall, even → spring.
    academic_year '2025-2026' means the year span; we derive the season year
    from the semester_number mapping:
      - odd (fall): year = second year of the span (2026)
      - even (spring): year = first year of the span (2025)
    """
    try:
        start_str, end_str = str(academic_year).split('-')
        end_year = int(end_str)
        start_year = int(start_str)
    except (ValueError, AttributeError):
        return _computed_semester_code()

    # /     /     >---- الفردي خريف (السنة الثانية)، الزوجي ربيع (السنة الأولى)
    if semester_number % 2 == 1:
        return f'fall_{end_year}'
    return f'spring_{start_year}'


# /     /     >---- نصلّح تكرار النسخ الفعالة: نسخة وحدة لكل قسم + فصل
def _migrate_single_active_timetable_version(conn: sqlite3.Connection) -> None:
    """Repair duplicated active timetable versions.

    Only one version may be active per department + semester. If legacy data
    left several rows marked 'active', keep the newest one active and mark
    the rest 'superseded' so the timetable page stays predictable.
    """
    if 'timetable_versions' not in {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }:
        return
    # /     /     >---- نجيب المجموعات اللي فيها أكثر من نسخة فعالة
    groups = conn.execute(
        'SELECT department_id, semester '
        'FROM timetable_versions '
        'WHERE status = \'active\' '
        'GROUP BY department_id, semester '
        'HAVING COUNT(*) > 1'
    ).fetchall()
    for group in groups:
        # /     /     >---- نرتب تنازلياً ونحتفظ بالأحدث
        rows = conn.execute(
            'SELECT id FROM timetable_versions '
            'WHERE department_id = ? AND semester = ? AND status = \'active\' '
            'ORDER BY id DESC',
            (group['department_id'], group['semester']),
        ).fetchall()
        if not rows:
            continue
        keep_id = rows[0]['id']
        # /     /     >---- البقية نعلّمها superseded
        conn.execute(
            'UPDATE timetable_versions SET status = \'superseded\' '
            'WHERE department_id = ? AND semester = ? AND status = \'active\' AND id != ?',
            (group['department_id'], group['semester'], keep_id),
        )


# /     /     >---- نضمن أن الأقسام الأكاديمية تصل للفصل الثامن (مرة وحدة بس)
def _migrate_department_semesters_eight(conn: sqlite3.Connection) -> None:
    """Raise academic departments' semester count to 8.

    التدريب الميداني ومشروع التخرج يقعان في الفصل الثامن، لذلك كل قسم أكاديمي
    (``semesters > 1``) يجب أن يعرض ثمانية فصول. القواعد القديمة بقيت على 7،
    فهذه الهجرة مرة واحدة ترفعها إلى 8 حتى يظهر الفصل الثامن في نماذج
    إضافة/تعديل المادة وفي عرض الخطة الدراسية.
    """
    _DEPT_SEMESTERS_MIGRATION = 'migrate_department_semesters_eight_v1'
    # /     /     >---- لو تمت قبل، نرجع فوراً
    if _migration_done(conn, _DEPT_SEMESTERS_MIGRATION):
        return

    if 'departments' not in {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }:
        _mark_migration_done(conn, _DEPT_SEMESTERS_MIGRATION)
        return

    conn.execute(
        'UPDATE departments SET semesters = 8 '
        'WHERE semesters IS NOT NULL AND semesters > 1 AND semesters < 8 '
        "AND (type IS NULL OR type != 'administrative') "
        'AND (hidden IS NULL OR hidden = 0)'
    )
    _mark_migration_done(conn, _DEPT_SEMESTERS_MIGRATION)


# /     /     >---- هجرة من السنة القديمة للفصول المسمّاة (مرة وحدة بس)
def _migrate_to_named_semesters(conn: sqlite3.Connection) -> None:
    """Migrate from academic_year (TEXT '2025-2026') to semester_code (TEXT 'fall_2026').

    Adds ``semester_code`` to ``timetable_versions``, converts existing
    rows, and enforces the (department_id, semester, semester_code) unique
    constraint. The ``semesters`` table (academic calendar) has been removed
    from the app and is no longer created or managed here.

    Guarded by the migration log so it runs exactly once.
    """
    _NAMED_SEMESTERS_MIGRATION = 'migrate_to_named_semesters_v1'
    # /     /     >---- مرّة وحدة بس (محمي بسجل الهجرات)
    if _migration_done(conn, _NAMED_SEMESTERS_MIGRATION):
        return

    # ── Add semester_code to timetable_versions ──────────────────────
    if 'timetable_versions' in {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }:
        tv_cols = {row[1] for row in conn.execute(
            'PRAGMA table_info(timetable_versions)'
        ).fetchall()}

        if 'semester_code' not in tv_cols:
            _safe_add_column(conn, 'timetable_versions', 'semester_code', 'TEXT DEFAULT ""')

        # ── 4. Convert existing academic_year → semester_code ──────────
        if 'academic_year' in tv_cols:
            rows = conn.execute(
                'SELECT id, department_id, semester, academic_year FROM timetable_versions '
                'WHERE (semester_code IS NULL OR semester_code = "") AND academic_year IS NOT NULL'
            ).fetchall()
            for r in rows:
                sem_code = _semester_number_to_code(r['semester'], r['academic_year'])
                conn.execute(
                    'UPDATE timetable_versions SET semester_code = ? WHERE id = ?',
                    (sem_code, r['id']),
                )

        # ── 5. Rebuild timetable_versions with new unique constraint ───
        # Drop old unique (department_id, semester, academic_year)
        # Create new unique (department_id, semester, semester_code)
        old_indexes = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'index' "
            "AND tbl_name = 'timetable_versions'"
        ).fetchall()
        for idx_name, _ in old_indexes:
            try:
                conn.execute(f'DROP INDEX IF EXISTS "{idx_name}"')
            except Exception:
                pass

        # /     /     >---- نعيد بناء الجدول بالقيود الصحيحة
        old_rows = conn.execute('SELECT * FROM timetable_versions').fetchall()
        old_cols = [d[1] for d in conn.execute('PRAGMA table_info(timetable_versions)').fetchall()]

        conn.execute('PRAGMA foreign_keys = OFF')
        try:
            conn.execute('DROP TABLE timetable_versions')
            conn.execute("""
                CREATE TABLE timetable_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
                    semester INTEGER NOT NULL,
                    semester_code TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(department_id, semester, semester_code)
                )
            """)

            # /     /     >---- نعيد إدخال السطور مع الرمز الجديد
            for row in old_rows:
                row_dict = dict(zip(old_cols, row))
                conn.execute(
                    'INSERT INTO timetable_versions '
                    '(id, department_id, semester, semester_code, status, created_at, updated_at) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (
                        row_dict['id'],
                        row_dict['department_id'],
                        row_dict['semester'],
                        row_dict.get('semester_code', ''),
                        row_dict.get('status', 'active'),
                        row_dict.get('created_at', ''),
                        row_dict.get('updated_at', ''),
                    ),
                )
        finally:
            conn.execute('PRAGMA foreign_keys = ON')

        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_tv_dept_sem_code '
            'ON timetable_versions(department_id, semester, semester_code)'
        )

    _mark_migration_done(conn, _NAMED_SEMESTERS_MIGRATION)
    conn.commit()


# /     /     >---- نتأكد نسخة الجدول بالصيغة الجديدة (semester_code)
def _ensure_version_v2(conn: sqlite3.Connection, dept_id: int, semester: int,
                       semester_code: str) -> int:
    """Ensure a timetable version exists using the new semester_code field."""
    row = conn.execute(
        'SELECT id FROM timetable_versions '
        'WHERE department_id = ? AND semester = ? AND semester_code = ?',
        (dept_id, semester, semester_code),
    ).fetchone()
    if row:
        return row['id']
    cur = conn.execute(
        'INSERT INTO timetable_versions (department_id, semester, semester_code, status) '
        'VALUES (?, ?, ?, ?)',
        (dept_id, semester, semester_code, 'active'),
    )
    return cur.lastrowid


# / /     /     >---- نجيب رمز الفصل الفعّال حالياً
def _current_semester_code(conn: sqlite3.Connection) -> str:
    """Return the currently active named semester code (computed from today)."""
    return _computed_semester_code()


# /     /     >---- نمسح جداول الطلاب القديمة (الدور انشال من النظام)
def _drop_student_schema(conn: sqlite3.Connection) -> None:
    """Remove student-related tables.

    Runs after the 'student' role was removed from the system (role overhaul).
    Idempotent: safe to run on every startup even when the tables are gone.
    Only drops tables — does NOT modify user data (see _cleanup_legacy_user_data).
    """
    conn.execute('PRAGMA foreign_keys = OFF')
    try:
        for table in (
            'student_enrollments',
            'student_login_requests',
            'student_verifications',
            'student_grades',
            'grade_schemes',
            'exam_marks',
            'attendance',
            'students',
        ):
            conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        conn.commit()
    finally:
        conn.execute('PRAGMA foreign_keys = ON')


# /     /     >---- نموذج الأدوار الجديد: فهرس يمنع أكثر من رئيس قسم لكل قسم
def _migrate_role_model(conn: sqlite3.Connection) -> None:
    """Create the unique index enforcing one HOD per department.

    Does NOT modify user data — data cleanup is in _cleanup_legacy_user_data.
    """
    conn.execute("DROP INDEX IF EXISTS idx_users_one_hod_per_department")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_one_hod_per_department "
        "ON users(department_id) WHERE role = 'head_of_department' AND department_id IS NOT NULL"
    )
    conn.commit()


# /     /     >---- نموذج الأدوار المتعددة: جدول user_roles
def _migrate_user_roles(conn: sqlite3.Connection) -> None:
    """Introduce the multi-role model: the ``user_roles`` join table.

    One person (a single ``users`` row) may hold several system roles at once
    (e.g. both ``teacher`` and ``head_of_department``).  ``users.role`` remains
    the person's *default landing role*; ``user_roles`` is the full set of
    roles the person holds.  ``users.is_active`` allows a soft-disable
    (deactivated users cannot log in) while keeping their data.

    Idempotent — safe to run on every startup.
    """
    # /     /     >---- ننشئ الجدول وفهرسه
    conn.execute(
        """CREATE TABLE IF NOT EXISTS user_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, role)
        )"""
    )
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id)'
    )

    # /     /     >---- نعبّي بأدوار المستخدمين الحالية كحد أدنى
    conn.execute(
        """INSERT OR IGNORE INTO user_roles (user_id, role)
           SELECT id, role FROM users"""
    )

    # /     /     >---- المرتبط بسجل أستاذ ياخد دور المدرس
    conn.execute(
        """INSERT OR IGNORE INTO user_roles (user_id, role)
           SELECT t.user_id, 'teacher' FROM teachers t
           WHERE t.user_id IS NOT NULL"""
    )

    # /     /     >---- الأساتذة المؤرشفين ما يقدروش يدخلوا (تعطيل ناعم)
    conn.execute(
        """UPDATE users SET is_active = COALESCE(is_active, 1)
           WHERE is_active IS NULL"""
    )
    if _column_exists(conn, 'teachers', 'deleted_at'):
        conn.execute(
            """UPDATE users SET is_active = 0
               WHERE id IN (
                   SELECT t.user_id FROM teachers t
                   WHERE t.user_id IS NOT NULL AND t.deleted_at IS NOT NULL
               ) AND is_active = 1"""
        )

    conn.commit()


# /     /     >---- نفحص هل عمود موجود في جدول
def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        rows = conn.execute(f'PRAGMA table_info({table})').fetchall()
    except sqlite3.OperationalError:
        return False
    return any(row[1] == column for row in rows)


# /     /     >---- نسمح بأن يكون teacher_id فاضي في نموذج المقرر
def _migrate_course_content_teacher_nullable(conn: sqlite3.Connection) -> None:
    """Rebuild ``course_content_submissions`` so ``teacher_id`` is nullable.

    Course-first workflow: the form (المقرر) is owned by the course. R&D
    fills it without picking a teacher, and courses absent from the
    timetable have no teacher to attach, so the column cannot stay NOT NULL.

    The new table is built from the *existing* table's definition
    (PRAGMA table_info / foreign_key_list / index_list) so every FK,
    UNIQUE constraint and index is preserved exactly; only the
    ``teacher_id`` NOT NULL flag is dropped.  Rebuilding from the
    hard-coded ``schema.sql`` DDL instead would revert e.g. the
    ``department_id ON DELETE SET NULL`` normalisation that
    ``_migrate_department_fks`` applies, forcing a second rebuild that
    drops child rows.
    """
    try:
        col_rows = conn.execute('PRAGMA table_info(course_content_submissions)').fetchall()
    except sqlite3.OperationalError:
        return
    cols = {r[1]: r for r in col_rows}
    # /     /     >---- لو العمود غير موجود أو أصلاً فاضي نرجع
    if 'teacher_id' not in cols or not cols['teacher_id'][3]:
        return

    fk_rows = conn.execute('PRAGMA foreign_key_list(course_content_submissions)').fetchall()
    idx_rows = conn.execute('PRAGMA index_list(course_content_submissions)').fetchall()
    old_sql_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='course_content_submissions'"
    ).fetchone()
    has_autoinc = 'AUTOINCREMENT' in (old_sql_row[0] or '').upper() if old_sql_row else False

    unique_single_cols = set()
    unique_multi = []
    regular_indexes = []
    for idx in idx_rows:
        if idx['origin'] == 'u':
            idx_cols = conn.execute(f'PRAGMA index_xinfo("{idx["name"]}")').fetchall()
            idxc = [ic['name'] for ic in idx_cols if ic['key']]
            if len(idxc) == 1:
                unique_single_cols.add(idxc[0])
            else:
                unique_multi.append('UNIQUE(' + ', '.join(f'"{c}"' for c in idxc) + ')')
        elif idx['origin'] == 'c':
            regular_indexes.append(idx)

    # /     /     >---- نبني الأعمدة ونحذف NOT NULL من teacher_id فقط
    col_defs = []
    for col in col_rows:
        parts = [f'"{col["name"]}"']
        if col['type']:
            parts.append(col['type'])
        if col['name'] != 'teacher_id' and col['notnull']:
            parts.append('NOT NULL')
        if col['dflt_value'] is not None:
            parts.append(f'DEFAULT {col["dflt_value"]}')
        if col['name'] in unique_single_cols:
            parts.append('UNIQUE')
        if col['pk']:
            parts.append('PRIMARY KEY')
            if has_autoinc:
                parts.append('AUTOINCREMENT')
        col_defs.append(' '.join(parts))

    # /     /     >---- نبني تعريفات الـ FK كما هي
    fk_groups = {}
    for fk in fk_rows:
        fk_groups.setdefault(fk['id'], []).append(fk)
    fk_defs = []
    for fk_id, fk_parts in fk_groups.items():
        from_cols = ', '.join(f'"{p["from"]}"' for p in fk_parts)
        to_table = fk_parts[0]['table']
        to_cols = ', '.join(f'"{p["to"]}"' for p in fk_parts)
        on_delete = fk_parts[0]['on_delete']
        if on_delete and on_delete != 'NO ACTION':
            sql = f'FOREIGN KEY ({from_cols}) REFERENCES "{to_table}" ({to_cols}) ON DELETE {on_delete}'
            on_update = fk_parts[0]['on_update']
            if on_update and on_update != 'NO ACTION':
                sql += f' ON UPDATE {on_update}'
            fk_defs.append(sql)
        else:
            fk_defs.append(f'FOREIGN KEY ({from_cols}) REFERENCES "{to_table}" ({to_cols})')

    # /     /     >---- ننشئ الجدول المؤقت وننقل البيانات
    temp = '_migrate_course_content_teacher_nullable'
    fk_was_on = conn.execute('PRAGMA foreign_keys').fetchone()[0]
    conn.execute('PRAGMA foreign_keys = OFF')
    try:
        conn.execute(f'DROP TABLE IF EXISTS "{temp}"')
        conn.execute(f'CREATE TABLE "{temp}" ({", ".join(col_defs + fk_defs + unique_multi)})')
        conn.execute(f'INSERT INTO "{temp}" SELECT * FROM "course_content_submissions"')
        # /     /     >---- نتحقق من سلامة النقل
        old_count = conn.execute('SELECT count(*) FROM "course_content_submissions"').fetchone()[0]
        new_count = conn.execute(f'SELECT count(*) FROM "{temp}"').fetchone()[0]
        if old_count != new_count:
            raise RuntimeError(
                f'Row count mismatch migrating course_content_submissions: {old_count} vs {new_count}'
            )
        old_ids = {r[0] for r in conn.execute('SELECT id FROM "course_content_submissions"').fetchall()}
        new_ids = {r[0] for r in conn.execute(f'SELECT id FROM "{temp}"').fetchall()}
        if old_ids != new_ids:
            raise RuntimeError('Primary key mismatch migrating course_content_submissions')
        conn.execute(f'DROP TABLE "course_content_submissions"')
        conn.execute(f'ALTER TABLE "{temp}" RENAME TO "course_content_submissions"')
        # /     /     >---- نعيد بناء الفهارس العادية
        for idx in regular_indexes:
            idx_name = idx['name']
            idx_cols = conn.execute(f'PRAGMA index_xinfo("{idx_name}")').fetchall()
            idx_col_parts = []
            for ic in idx_cols:
                if ic['key']:
                    name = f'"{ic["name"]}"'
                    if ic['desc']:
                        name += ' DESC'
                    idx_col_parts.append(name)
            if idx_col_parts:
                unique = 'UNIQUE' if idx['unique'] else ''
                conn.execute(
                    f'CREATE {unique} INDEX IF NOT EXISTS "{idx_name}" '
                    f'ON "course_content_submissions" ({", ".join(idx_col_parts)})'
                )
        conn.execute('CREATE INDEX IF NOT EXISTS idx_course_content_submissions_teacher ON course_content_submissions(teacher_id)')
        conn.execute('COMMIT')
    except Exception:
        conn.execute('ROLLBACK')
        raise
    finally:
        conn.execute(f'PRAGMA foreign_keys = {1 if fk_was_on else 0}')


# /     /     >---- نضيف عمود teacher_name (نص حر للعرض) لنموذج المقرر
def _migrate_course_content_teacher_name(conn: sqlite3.Connection) -> None:
    """Add the display-only ``teacher_name`` column to submissions.

    The form (المقرر) may be filled without an attached teacher
    (``teacher_id``), but the sheet shows «اسم عضو هيئة التدريس» as an
    editable field.  ``teacher_name`` persists that free-text entry so it
    survives re-edits and shows on the detail page; when empty, lookups
    fall back to the joined ``teachers.name``.
    """
    try:
        cols = {r[1] for r in conn.execute(
            'PRAGMA table_info(course_content_submissions)').fetchall()}
    except sqlite3.OperationalError:
        return
    if 'teacher_name' not in cols:
        _safe_add_column(conn, 'course_content_submissions', 'teacher_name',
                         "TEXT DEFAULT ''")


# /     /     >---- مخزن الملفات التابع للمقرر (course_files) + النقل من القديم
def _migrate_course_files(conn: sqlite3.Connection) -> None:
    """Create the course-owned ``course_files`` store and backfill it.

    The course owns every file; the uploader (teacher/R&D) is metadata
    only.  Legacy per-uploader tables (``teacher_course_files``,
    ``course_vocabulary``) and the file columns on
    ``course_content_submissions`` / ``courses`` are dropped by
    ``_drop_legacy_course_file_tables`` once every reader/writer reads
    only ``course_files``.
    """
    # /     /     >---- ننشئ الجدول وفهارسه
    conn.execute("""
        CREATE TABLE IF NOT EXISTS course_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
            file_type TEXT NOT NULL DEFAULT 'form',
            filename TEXT NOT NULL DEFAULT '',
            original_filename TEXT NOT NULL DEFAULT '',
            file_size INTEGER DEFAULT 0,
            uploaded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            teacher_id INTEGER REFERENCES teachers(id) ON DELETE SET NULL,
            submission_id INTEGER REFERENCES course_content_submissions(id) ON DELETE SET NULL,
            status TEXT NOT NULL DEFAULT 'approved',
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute('CREATE INDEX IF NOT EXISTS idx_course_files_course ON course_files(course_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_course_files_course_type_status ON course_files(course_id, file_type, status)')

    # /     /     >---- نضيف عمود course_file_id للنموذج
    if 'course_content_submissions' in {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }:
        cols = _get_column_names(conn, 'course_content_submissions')
        if 'course_file_id' not in cols:
            _safe_add_column(conn, 'course_content_submissions', 'course_file_id',
                             'INTEGER REFERENCES course_files(id) ON DELETE SET NULL')

    # /     /     >---- ننقل البيانات القديمة مرة وحدة (محمي: ما فيش سطور بعد)
    if conn.execute('SELECT COUNT(*) FROM course_files').fetchone()[0] == 0:
        # /     /     >---- ملفات المقررات من جدول الأستاذ القديم
        try:
            conn.execute("""
                INSERT OR IGNORE INTO course_files
                    (course_id, file_type, filename, original_filename, file_size,
                     uploaded_by, teacher_id, status, created_at, updated_at)
                SELECT tcf.course_id, 'syllabus', tcf.filename, tcf.original_filename,
                       COALESCE(tcf.file_size, 0), t.user_id, tcf.teacher_id, 'approved',
                       COALESCE(tcf.created_at, CURRENT_TIMESTAMP),
                       COALESCE(tcf.updated_at, CURRENT_TIMESTAMP)
                FROM teacher_course_files tcf
                LEFT JOIN teachers t ON t.id = tcf.teacher_id
            """)
        except sqlite3.OperationalError:
            pass  # legacy table absent on fresh installs
        # /     /     >---- ملفات المفردات القديمة
        try:
            conn.execute("""
                INSERT OR IGNORE INTO course_files
                    (course_id, file_type, filename, original_filename, file_size,
                     uploaded_by, status, created_at)
                SELECT course_id, 'vocabulary', filename, original_filename,
                       COALESCE(file_size, 0), uploaded_by, 'approved',
                       COALESCE(created_at, CURRENT_TIMESTAMP)
                FROM course_vocabulary
            """)
        except sqlite3.OperationalError:
            pass
        # /     /     >---- نماذج المقرر من جدول النماذج
        try:
            conn.execute("""
                INSERT OR IGNORE INTO course_files
                    (course_id, file_type, filename, original_filename, file_size,
                     uploaded_by, teacher_id, submission_id, status, created_at, updated_at)
                SELECT course_id, 'form', filename, original_filename,
                       COALESCE(file_size, 0), user_id, teacher_id, id, status,
                       COALESCE(submitted_at, CURRENT_TIMESTAMP),
                       COALESCE(updated_at, CURRENT_TIMESTAMP)
                FROM course_content_submissions
                WHERE filename IS NOT NULL AND filename != ''
            """)
        except sqlite3.OperationalError:
            pass
        # /     /     >---- نربط النموذج بأحدث ملف له
        try:
            conn.execute("""
                UPDATE course_content_submissions
                SET course_file_id = (
                    SELECT cf.id FROM course_files cf
                    WHERE cf.submission_id = course_content_submissions.id
                    ORDER BY cf.id DESC LIMIT 1
                )
                WHERE course_file_id IS NULL
                  AND filename IS NOT NULL AND filename != ''
            """)
        except sqlite3.OperationalError:
            pass


# /     /     >---- سجل انتقالات محتوى المقرر (مصدر الحقيقة للتاريخ)
def _ensure_course_content_transitions(conn: sqlite3.Connection) -> None:
    """Audit log for every course-content state transition.

    One row per applied step (save/submit/approve/reject/publish/archive and
    every step of the composite ``publish_directly`` chain).  Created
    idempotently so both fresh installs (schema.sql) and existing databases
    converge on the same shape.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS course_content_transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL
                REFERENCES course_content_submissions(id) ON DELETE CASCADE,
            from_status TEXT NOT NULL,
            to_status TEXT NOT NULL,
            action TEXT NOT NULL,
            actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute('CREATE INDEX IF NOT EXISTS '
                 'idx_course_content_transitions_submission '
                 'ON course_content_transitions(submission_id)')


# /     /     >---- بعد الفصل الدراسي (academic period) للمحتوى
def _migrate_academic_periods(conn: sqlite3.Connection) -> None:
    """Academic-period dimension (الفصل الدراسي) for course content.

    Content belongs to ``course + period`` — never to a bare filename.
    Legacy rows keep ``academic_period_id = NULL`` and surface under
    «بدون فصل دراسي محدد».  Surrounding years are seeded
    so the picker always has sensible options.
    """
    # /     /     >---- ننشئ الجدول وفهرسه
    conn.execute("""
        CREATE TABLE IF NOT EXISTS academic_periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER NOT NULL,
            term TEXT NOT NULL DEFAULT 'خريف',
            label TEXT NOT NULL DEFAULT '',
            UNIQUE(year, term)
        )
    """)
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_academic_periods_year ON academic_periods(year)'
    )

    # /     /     >---- نعبّي السنين المحيطة (خريف/ربيع)
    current_year = datetime.date.today().year
    for year in range(current_year - 2, current_year + 2):
        for term in ('خريف', 'ربيع'):
            conn.execute(
                'INSERT OR IGNORE INTO academic_periods (year, term, label) '
                'VALUES (?, ?, ?)',
                (year, term, f'{term} {year}'),
            )

    # /     /     >---- نضيف العمود للنموذج والملفات
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()}
    if 'course_content_submissions' in tables:
        _safe_add_column(conn, 'course_content_submissions', 'academic_period_id',
                         'INTEGER REFERENCES academic_periods(id) ON DELETE SET NULL')
    if 'course_files' in tables:
        _safe_add_column(conn, 'course_files', 'academic_period_id',
                         'INTEGER REFERENCES academic_periods(id) ON DELETE SET NULL')


# /     /     >---- نمسح الجداول والأعمدة القديمة بعد اعتماد course_files
def _drop_legacy_course_file_tables(conn: sqlite3.Connection) -> None:
    """Remove the legacy per-uploader file stores once course_files is live.

    Safe to run on an upgraded DB (SQLite >= 3.35 for DROP COLUMN).
    """
    for table in ('teacher_course_files', 'course_vocabulary'):
        try:
            conn.execute(f'DROP TABLE IF EXISTS {table}')
        except sqlite3.OperationalError:
            pass
    cols = _get_column_names(conn, 'course_content_submissions')
    for col in ('filename', 'original_filename', 'file_size'):
        if col in cols:
            conn.execute(f'ALTER TABLE course_content_submissions DROP COLUMN {col}')
    cols = _get_column_names(conn, 'courses')
    for col in ('vocabulary', 'syllabus_file'):
        if col in cols:
            conn.execute(f'ALTER TABLE courses DROP COLUMN {col}')


# ── One-time legacy cleanup (runs exactly once) ──────────────────────

_CLEANUP_MIGRATION_NAME = 'cleanup_legacy_user_data_v1'


# /     /     >---- ننشئ جدول سجل الهجرات
def _ensure_migration_log(conn: sqlite3.Connection) -> None:
    """Create the migration_log table if it does not exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migration_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            migration_name TEXT NOT NULL UNIQUE,
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


# /     /     >---- نشوف هل الهجرة تمت من قبل
def _migration_done(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        'SELECT 1 FROM _migration_log WHERE migration_name = ?', (name,)
    ).fetchone()
    return row is not None


# /     /     >---- نعلّم الهجرة كمنفّذة
def _mark_migration_done(conn: sqlite3.Connection, name: str) -> None:
    conn.execute(
        'INSERT OR IGNORE INTO _migration_log (migration_name) VALUES (?)', (name,)
    )
    conn.commit()


# /     /     >---- تنظيف البيانات القديمة (المستخدمين والأدوار) مرة وحدة
def _cleanup_legacy_user_data(conn: sqlite3.Connection) -> None:
    """One-time cleanup of legacy user/role data.

    This replaces the old _drop_student_schema role mutations and
    _migrate_role_model department wiping that used to run on every startup.
    Now runs exactly once via the _migration_log guard.
    """
    # /     /     >---- لو تم قبل، نرجع فوراً
    if _migration_done(conn, _CLEANUP_MIGRATION_NAME):
        return

    from werkzeug.security import generate_password_hash

    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
    has_users = 'users' in tables
    has_teachers = 'teachers' in tables
    has_user_roles = 'user_roles' in tables
    user_cols = _get_column_names(conn, 'users') if has_users else set()
    teacher_cols = _get_column_names(conn, 'teachers') if has_teachers else set()

    # /     /     >---- 1. ننظف روابط الأدوار القديمة المحذوفة من النظام
    if has_user_roles:
        conn.execute(
            "DELETE FROM user_roles WHERE role NOT IN "
            "('research_development', 'faculty_affairs', 'head_of_department', 'teacher', 'exam')"
        )

    # /     /     >---- 2. نحذف مستخدمي الطلاب ونفصل FKs للأساتذة
    if has_users and has_teachers and 'role' in user_cols and 'user_id' in teacher_cols:
        conn.execute(
            'UPDATE teachers SET user_id = NULL '
            "WHERE user_id IN (SELECT id FROM users WHERE role = 'student')"
        )
        conn.execute("DELETE FROM users WHERE role = 'student'")

    # /     /     >---- 3. الأدوار الإدارية ما تحملش قسم أكاديمي
    if has_users and 'department_id' in user_cols and 'role' in user_cols:
        conn.execute(
            "UPDATE users SET department_id = NULL "
            "WHERE role IN ('faculty_affairs', 'research_development', 'exam')"
        )

    # /     /     >---- 4. ننشف تكرار رؤساء الأقسام: نحتفظ بالأقدم والباقي مدرّس
    if has_users and 'department_id' in user_cols and 'role' in user_cols:
        duplicates = conn.execute(
            """
            SELECT department_id, MIN(id) AS keep_id
            FROM users
            WHERE role = 'head_of_department' AND department_id IS NOT NULL
            GROUP BY department_id
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        for row in duplicates:
            conn.execute(
                "UPDATE users SET role = 'teacher' "
                "WHERE role = 'head_of_department' AND department_id = ? AND id != ?",
                (row['department_id'], row['keep_id']),
            )

    # /     /     >---- 5. نفصل روابط أساتذة تشير لحسابات غير أستاذ/رئيس قسم
    if has_users and has_teachers and has_user_roles and 'user_id' in teacher_cols and 'role' in user_cols:
        conn.execute('''
            UPDATE teachers SET user_id = NULL
            WHERE user_id IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM users u
                LEFT JOIN user_roles ur ON ur.user_id = u.id
                WHERE u.id = teachers.user_id
                  AND (u.role IN ('teacher', 'head_of_department')
                       OR ur.role IN ('teacher', 'head_of_department'))
            )
        ''')

    # /     /     >---- 6. نتأكد من وجود حساب مدير المكتب الأساسي بالضبط
    if has_users and 'username' in user_cols and 'label' in user_cols:
        om = conn.execute(
            "SELECT id, label FROM users WHERE username = 'office_manager'"
        ).fetchone()
        if om and 'role' in user_cols:
            conn.execute(
                "UPDATE users SET role = 'faculty_affairs', label = 'مدير مكتب أعضاء هيئة التدريس' "
                "WHERE id = ?",
                (om['id'],),
            )
        elif 'role' in user_cols and 'password' in user_cols and 'label' in user_cols:
            # /     /     >---- ما فيش مدير: ننشئه (بكلمة مرور من البيئة أو مولّدة)
            # /     /     >---- ونحذف أي حسابات قديمة بدور super_admin نهائياً
            if has_teachers and 'user_id' in teacher_cols and 'role' in user_cols:
                conn.execute(
                    'UPDATE teachers SET user_id = NULL '
                    "WHERE user_id IN (SELECT id FROM users WHERE role = 'super_admin')"
                )
            if has_user_roles:
                conn.execute("DELETE FROM user_roles WHERE role = 'super_admin'")
            if 'role' in user_cols:
                conn.execute("DELETE FROM users WHERE role = 'super_admin'")
            admin_pw = os.environ.get('ADMIN_PASSWORD')
            if not admin_pw:
                admin_pw = secrets.token_urlsafe(12)
                print(f'[schema] No ADMIN_PASSWORD env set - generated office_manager password: {admin_pw}')
                print('[schema] Store it now; it will not be shown again.\n')
            conn.execute(
                "INSERT INTO users (username, password, role, label) VALUES (?, ?, ?, ?)",
                ('office_manager', generate_password_hash(admin_pw), 'faculty_affairs',
                 'مدير مكتب أعضاء هيئة التدريس'),
            )

    # /     /     >---- 7. نعيد تسمية أسماء مستخدمين teacher.* للأسماء العربية
    if has_users and has_teachers and 'username' in user_cols and 'user_id' in teacher_cols and 'name' in teacher_cols:
        teacher_users = conn.execute(
            "SELECT u.id, u.username, t.name FROM users u "
            "JOIN teachers t ON t.user_id = u.id "
            "WHERE u.username LIKE 'teacher.%'"
        ).fetchall()
        teacher_pw_hash = generate_password_hash(os.environ.get('TEACHER_DEFAULT_PASSWORD', '123456'))
        for tu in teacher_users:
            arabic_name = tu['name']
            if arabic_name and arabic_name != tu['username']:
                already = conn.execute(
                    'SELECT id FROM users WHERE username = ? AND id != ?',
                    (arabic_name, tu['id'])
                ).fetchone()
                if not already:
                    conn.execute(
                        'UPDATE users SET username = ? WHERE id = ?',
                        (arabic_name, tu['id'])
                    )
                    conn.execute(
                        'UPDATE users SET password = ? WHERE id = ?',
                        (teacher_pw_hash, tu['id'])
                    )

    # /     /     >---- 8. ننظف حسابات الاختبار والسجلات اليتيمة
    if has_users and has_teachers and 'username' in user_cols and 'name' in teacher_cols and 'user_id' in teacher_cols:
        t1_user = conn.execute(
            "SELECT id FROM users WHERE username = 'teacher1'"
        ).fetchone()
        if t1_user:
            conn.execute('DELETE FROM users WHERE id = ?', (t1_user['id'],))
        orphan_fake = conn.execute(
            "SELECT id FROM teachers WHERE name = 'أستاذ تجريبي'"
        ).fetchone()
        if orphan_fake:
            conn.execute('DELETE FROM teachers WHERE id = ?', (orphan_fake['id'],))
        orphan_pytest = conn.execute(
            "SELECT id FROM teachers WHERE name = 'Pytest Teacher' AND user_id IS NULL"
        ).fetchall()
        for op in orphan_pytest:
            conn.execute('DELETE FROM teachers WHERE id = ?', (op['id'],))

    conn.commit()
    _mark_migration_done(conn, _CLEANUP_MIGRATION_NAME)


_DEDUP_MIGRATION_NAME = 'deduplicate_teachers_v1'

# Tables with FK to teachers(id), grouped by ON DELETE behavior.
# Tables with UNIQUE(teacher_id, ...) need INSERT OR IGNORE during migration.
_FK_TABLES_NO_UNIQUE = [
    'timetable', 'faculty_attendance', 'course_files',
    'course_content_submissions', 'teacher_messages', 'teacher_documents',
    'teacher_materials', 'teacher_requests',
    'faculty_research_activities', 'faculty_admin_assignments', 'faculty_leaves',
]
_FK_TABLES_WITH_UNIQUE = [
    'teacher_taught_courses', 'teacher_departments', 'teacher_course_files',
]
_ALL_FK_TABLES = _FK_TABLES_NO_UNIQUE + _FK_TABLES_WITH_UNIQUE

# Fields to merge from duplicate -> canonical (fill NULLs only)
_MERGE_FIELDS = [
    'email', 'phone', 'academic_number', 'national_id',
    'department', 'qualification', 'academic_rank', 'classification',
    'department_id', 'qualification_id', 'rank_id', 'classification_id',
    'contract_date', 'tasks', 'specialization', 'position', 'photo_filename',
]


# /     /     >---- دمج الأساتذة المكررين (مرّة وحدة، من ملف المعتمد)
def _deduplicate_teachers_v1(conn: sqlite3.Connection) -> None:
    """One-time migration: merge approved teacher duplicates.

    Reads approved merges from scripts/approved_teacher_merges.json.
    Only processes groups explicitly listed in the JSON — never auto-detects.
    Each group runs inside a single transaction for atomicity.
    """
    # /     /     >---- لو تم قبل، نرجع فوراً
    if _migration_done(conn, _DEDUP_MIGRATION_NAME):
        return

    import json as _json
    import os

    # /     /     >---- نجيب ملف الدمج المعتمد
    merges_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'scripts', 'approved_teacher_merges.json',
    )
    if not os.path.exists(merges_path):
        # No merges file — nothing to do
        return

    with open(merges_path, encoding='utf-8') as f:
        config = _json.load(f)

    groups = config.get('groups', [])
    if not groups:
        return

    # /     /     >---- جدول تدقيق لعملية الدمج
    conn.execute('''
        CREATE TABLE IF NOT EXISTS teacher_dedup_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_teacher_id INTEGER NOT NULL,
            duplicate_teacher_id INTEGER NOT NULL,
            matched_by TEXT NOT NULL,
            original_name TEXT,
            original_academic_number TEXT,
            original_email TEXT,
            original_user_id INTEGER,
            fk_refs_migrated INTEGER DEFAULT 0,
            fields_merged TEXT,
            migrated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    total_migrated = 0

    for group in groups:
        # /     /     >---- نتجاهل المجموعات الغير معتمدة
        if not group.get('approved', False):
            continue

        canonical_id = group['canonical_teacher_id']
        duplicate_ids = group.get('duplicate_teacher_ids', [])
        matched_by = group.get('matched_by', 'unknown')

        if not duplicate_ids:
            continue

        # /     /     >---- نتأكد من وجود الأساس
        canon = conn.execute(
            'SELECT id, name, email, academic_number, user_id FROM teachers WHERE id = ?',
            (canonical_id,),
        ).fetchone()
        if not canon:
            continue

        # /     /     >---- نتأكد من وجود كل المكررين
        valid_duplicates = []
        for dup_id in duplicate_ids:
            dup = conn.execute(
                'SELECT id, name, email, academic_number, user_id FROM teachers WHERE id = ?',
                (dup_id,),
            ).fetchone()
            if dup:
                valid_duplicates.append(dup)

        if not valid_duplicates:
            continue

        # ── Begin transaction for this group ───────────────────────────
        conn.execute('SAVEPOINT sp_dedup')

        try:
            for dup in valid_duplicates:
                dup_id = dup['id']

                # /     /     >---- نسجّل لقطة للتدقيق
                conn.execute(
                    '''INSERT INTO teacher_dedup_audit
                       (canonical_teacher_id, duplicate_teacher_id, matched_by,
                        original_name, original_academic_number, original_email,
                        original_user_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (canonical_id, dup_id, matched_by,
                     dup['name'], dup['academic_number'], dup['email'],
                     dup['user_id']),
                )

                # Migrate FKs — tables without UNIQUE constraint
                fk_count = 0
                for table in _FK_TABLES_NO_UNIQUE:
                    try:
                        conn.execute(
                            f'UPDATE {table} SET teacher_id = ? WHERE teacher_id = ?',
                            (canonical_id, dup_id),
                        )
                        fk_count += conn.execute(
                            f'SELECT CHANGES()'
                        ).fetchone()[0]
                    except Exception:
                        pass

                # Migrate FKs — tables with UNIQUE constraint
                # Strategy: UPDATE teacher_id directly (fastest, preserves row).
                # If UNIQUE conflict, the duplicate row is redundant — DELETE it.
                for table in _FK_TABLES_WITH_UNIQUE:
                    try:
                        dup_count = conn.execute(
                            f'SELECT COUNT(*) FROM {table} WHERE teacher_id = ?',
                            (dup_id,),
                        ).fetchone()[0]

                        if dup_count == 0:
                            continue

                        # /     /     >---- ننقل كل السطور بتحديث teacher_id
                        conn.execute(
                            f'UPDATE {table} SET teacher_id = ? WHERE teacher_id = ?',
                            (canonical_id, dup_id),
                        )

                        # /     /     >---- بقي سطور؟ تعارض UNIQUE → نحذفها (زائدة)
                        remaining = conn.execute(
                            f'SELECT COUNT(*) FROM {table} WHERE teacher_id = ?',
                            (dup_id,),
                        ).fetchone()[0]

                        if remaining > 0:
                            # These rows conflict with existing canonical rows
                            # — safe to delete (canonical already has equivalent data)
                            conn.execute(
                                f'DELETE FROM {table} WHERE teacher_id = ?',
                                (dup_id,),
                            )

                        fk_count += dup_count
                    except Exception:
                        pass

                # /     /     >---- نحدّث سجل التدقيق بعدد المراجع
                conn.execute(
                    'UPDATE teacher_dedup_audit SET fk_refs_migrated = ? '
                    'WHERE canonical_teacher_id = ? AND duplicate_teacher_id = ?',
                    (fk_count, canonical_id, dup_id),
                )

                # /     /     >---- ندمج الحقول: نملأ الفراغات في الأساس من المكرر
                merged_fields = []
                for field in _MERGE_FIELDS:
                    try:
                        canon_val = conn.execute(
                            f'SELECT {field} FROM teachers WHERE id = ?',
                            (canonical_id,),
                        ).fetchone()[0]
                        dup_val = conn.execute(
                            f'SELECT {field} FROM teachers WHERE id = ?',
                            (dup_id,),
                        ).fetchone()[0]
                        if canon_val in (None, '', 0) and dup_val not in (None, '', 0):
                            conn.execute(
                                f'UPDATE teachers SET {field} = ? WHERE id = ?',
                                (dup_val, canonical_id),
                            )
                            merged_fields.append(field)
                    except Exception:
                        pass

                # /     /     >---- نسجّل الحقول المدمجة
                conn.execute(
                    'UPDATE teacher_dedup_audit SET fields_merged = ? '
                    'WHERE canonical_teacher_id = ? AND duplicate_teacher_id = ?',
                    (_json.dumps(merged_fields), canonical_id, dup_id),
                )

                # /     /     >---- نحذف الأستاذ المكرر
                conn.execute('DELETE FROM teachers WHERE id = ?', (dup_id,))
                total_migrated += 1

            conn.execute('RELEASE sp_dedup')

        except Exception:
            conn.execute('ROLLBACK TO sp_dedup')
            continue

    conn.commit()
    if total_migrated > 0:
        _mark_migration_done(conn, _DEDUP_MIGRATION_NAME)


# /     /     >---- نتحقق من سلامة مراجع teacher_id عبر كل الجداول
def _verify_teacher_fk_integrity(conn: sqlite3.Connection) -> None:
    """Verify no orphaned teacher_id references exist across all FK tables.

    Logs warnings but never raises — this is a diagnostic, not a blocker.
    """
    import logging
    _log = logging.getLogger(__name__)

    existing_tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }

    if 'teachers' not in existing_tables:
        return

    # /     /     >---- نعد المراجع اليتيمة (نحذّر فقط، ما نوقفش)
    total_orphans = 0
    for table in _ALL_FK_TABLES:
        if table not in existing_tables:
            continue
        try:
            row = conn.execute(
                f'SELECT COUNT(*) FROM {table} t '
                f'WHERE t.teacher_id IS NOT NULL '
                f'AND NOT EXISTS (SELECT 1 FROM teachers WHERE id = t.teacher_id)'
            ).fetchone()
            orphaned = row[0] if row else 0
            if orphaned > 0:
                _log.warning(
                    "FK integrity: %d orphaned teacher_id reference(s) in %s",
                    orphaned, table,
                )
                total_orphans += orphaned
        except Exception:
            pass

    if total_orphans > 0:
        _log.warning(
            "FK integrity check found %d total orphaned teacher references. "
            "These rows have teacher_id pointing to deleted/non-existent teachers.",
            total_orphans,
        )


# /     /     >---- نطبّع الرقم الأكاديمي ونضيف فهرس فريد جزئي
def _ensure_academic_number_index(conn: sqlite3.Connection) -> None:
    """Normalize sentinel values in academic_number and add a partial UNIQUE index.

    Sentinels like '', '0', 'غير محدد', '—', '-', 'N/A', 'null' are collapsed
    to NULL so the UNIQUE index only enforces real academic numbers.
    """
    existing_tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if 'teachers' not in existing_tables:
        return

    teacher_cols = _get_column_names(conn, 'teachers')
    if 'academic_number' not in teacher_cols:
        return

    # /     /     >---- نحول القيم الوهمية إلى NULL
    conn.execute('''
        UPDATE teachers SET academic_number = NULL
        WHERE academic_number IN ('', '0', 'غير محدد', '—', '-', 'N/A', 'null')
           OR TRIM(academic_number) = ''
    ''')

    # /     /     >---- فهرس فريد على الأرقام الحقيقية فقط
    conn.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS uq_teachers_academic_number
        ON teachers(academic_number)
        WHERE academic_number IS NOT NULL
    ''')
    conn.commit()


# /     /     >---- جداول تقييم أداء هيئة التدريس (كشف العبء التدريسي)
def _ensure_faculty_performance_tables(conn: sqlite3.Connection, existing_tables: set) -> None:
    """Create tables for the faculty performance evaluation (كشف العبء التدريسي)."""

    conn.execute("""
        CREATE TABLE IF NOT EXISTS faculty_course_student_counts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
            course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
            academic_year TEXT NOT NULL,
            semester INTEGER NOT NULL,
            student_count INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(teacher_id, course_id, academic_year, semester)
        )
    """)
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_fcsc_teacher_term '
        'ON faculty_course_student_counts(teacher_id, academic_year, semester)'
    )

    # /     /     >---- قواعد العبء التدريسي
    if 'faculty_workload_rules' not in existing_tables:
        conn.execute("""
            CREATE TABLE faculty_workload_rules (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                rank_id         INTEGER NOT NULL REFERENCES academic_ranks(id),
                category        TEXT NOT NULL,
                min_hours       INTEGER NOT NULL DEFAULT 0,
                max_hours       INTEGER NOT NULL DEFAULT 0,
                academic_year   TEXT NOT NULL DEFAULT '',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                deleted_at      TIMESTAMP
            )
        """)
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_fwlr_unique ON faculty_workload_rules(rank_id, category, academic_year)')
        _seed_workload_rules(conn)

    # /     /     >---- النشاطات البحثية
    if 'faculty_research_activities' not in existing_tables:
        conn.execute("""
            CREATE TABLE faculty_research_activities (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id      INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
                academic_year   TEXT NOT NULL,
                semester        INTEGER NOT NULL,
                activity_type   TEXT NOT NULL,
                hours           INTEGER NOT NULL DEFAULT 0,
                notes           TEXT,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                deleted_at      TIMESTAMP
            )
        """)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_fra_teacher ON faculty_research_activities(teacher_id)')

    # /     /     >---- المهام الإدارية
    if 'faculty_admin_assignments' not in existing_tables:
        conn.execute("""
            CREATE TABLE faculty_admin_assignments (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id      INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
                task_name       TEXT NOT NULL,
                auto_hours      INTEGER,
                manual_hours    INTEGER DEFAULT 0,
                assignment_date TEXT DEFAULT '',
                start_date      TEXT NOT NULL,
                end_date        TEXT,
                notes           TEXT,
                academic_year   TEXT DEFAULT '',
                semester        INTEGER DEFAULT 0,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                deleted_at      TIMESTAMP
            )
        """)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_faa_teacher ON faculty_admin_assignments(teacher_id)')

    # /     /     >---- الإجازات
    if 'faculty_leaves' not in existing_tables:
        conn.execute("""
            CREATE TABLE faculty_leaves (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id        INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
                leave_type        TEXT NOT NULL,
                decision_number   TEXT,
                decision_authority TEXT,
                decision_date     TEXT,
                start_date        TEXT NOT NULL,
                end_date          TEXT,
                hours             INTEGER NOT NULL DEFAULT 0,
                notes             TEXT,
                created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                deleted_at        TIMESTAMP
            )
        """)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_fl_teacher ON faculty_leaves(teacher_id)')

    # /     /     >---- أنواع النشاطات البحثية
    if 'research_activity_types' not in existing_tables:
        conn.execute("""
            CREATE TABLE research_activity_types (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                is_active   INTEGER NOT NULL DEFAULT 1,
                sort_order  INTEGER NOT NULL DEFAULT 0
            )
        """)
        _seed_research_activity_types(conn)

    # /     /     >---- أنواع المهام الإدارية
    if 'admin_assignment_types' not in existing_tables:
        conn.execute("""
            CREATE TABLE admin_assignment_types (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL UNIQUE,
                default_hours   INTEGER NOT NULL DEFAULT 0,
                is_active       INTEGER NOT NULL DEFAULT 1,
                sort_order      INTEGER NOT NULL DEFAULT 0
            )
        """)
        _seed_admin_assignment_types(conn)

    # /     /     >---- نضيف الأعمدة الناقصة للجداول الموجودة
    if 'faculty_admin_assignments' in existing_tables:
        faa_cols = _get_column_names(conn, 'faculty_admin_assignments')
        if 'assignment_date' not in faa_cols:
            _safe_add_column(conn, 'faculty_admin_assignments', 'assignment_date', 'TEXT DEFAULT \'\'')
        if 'academic_year' not in faa_cols:
            _safe_add_column(conn, 'faculty_admin_assignments', 'academic_year', 'TEXT DEFAULT \'\'')
        if 'semester' not in faa_cols:
            _safe_add_column(conn, 'faculty_admin_assignments', 'semester', 'INTEGER DEFAULT 0')

    if 'faculty_leaves' in existing_tables:
        fl_cols = _get_column_names(conn, 'faculty_leaves')
        if 'hours' not in fl_cols:
            _safe_add_column(conn, 'faculty_leaves', 'hours', 'INTEGER NOT NULL DEFAULT 0')


# /     /     >---- نعبّي أنوع النشاطات البحثية الافتراضية
def _seed_research_activity_types(conn: sqlite3.Connection) -> None:
    """Seed default research activity types."""
    existing = conn.execute('SELECT COUNT(*) FROM research_activity_types').fetchone()[0]
    if existing > 0:
        return
    types = [
        ('مشروع تخرج', 1),
        ('دراسة ميدانية', 2),
        ('مجموعات بحثية', 3),
        ('دراسة حقلية', 4),
        ('بحث علمي', 5),
        ('إرشاد كلية', 6),
    ]
    for name, order in types:
        conn.execute(
            'INSERT INTO research_activity_types (name, is_active, sort_order) VALUES (?, 1, ?)',
            (name, order),
        )


# /     /     >---- نعبّي أنواع المهام الإدارية الافتراضية بساعاتها
def _seed_admin_assignment_types(conn: sqlite3.Connection) -> None:
    """Seed default admin assignment types with hours."""
    existing = conn.execute('SELECT COUNT(*) FROM admin_assignment_types').fetchone()[0]
    if existing > 0:
        return
    types = [
        ('رئيس قسم', 18, 1),
        ('رئيس قسم البحث والتطوير', 18, 2),
        ('رئيس قسم الامتحانات', 18, 3),
        ('مدير مكتب أعضاء هيئة التدريس', 12, 4),
        ('مدير مكتب الشؤون العلمية', 12, 5),
        ('منسق القاعات', 6, 6),
        ('عميد الكلية', 18, 7),
        ('مدير مكتب الجودة', 12, 8),
        ('مدير مكتب الدراسة العالية', 12, 9),
        ('رئيس القسم العلمي', 18, 10),
        ('رئيس قسم الشؤون الفنية والمعامل', 12, 11),
        ('رئيس قسم البحث والتطوير والمناهج', 18, 12),
        ('رئيس قسم التدريب الميداني', 12, 13),
        ('رئيس قسم الدبلوم المهني', 12, 14),
        ('منسق الشعبة العلمية', 6, 15),
        ('منسق الجودة بالقسم', 6, 16),
        ('منسق الدراسة العالية بالقسم', 6, 17),
        ('منسق المواد العامة بالقسم العلمي', 6, 18),
        ('منسق تدريب ميداني', 6, 19),
        ('عضو تحرير مجلة علمية', 6, 20),
    ]
    for name, hours, order in types:
        conn.execute(
            'INSERT INTO admin_assignment_types (name, default_hours, is_active, sort_order) VALUES (?, ?, 1, ?)',
            (name, hours, order),
        )


# /     /     >---- نعبّي قواعد العبء الافتراضية لكل الرتب
def _seed_workload_rules(conn: sqlite3.Connection) -> None:
    """Seed default workload rules for academic ranks."""
    rank_rows = conn.execute('SELECT id, name_ar FROM academic_ranks').fetchall()
    if not rank_rows:
        return
    existing = conn.execute('SELECT COUNT(*) FROM faculty_workload_rules').fetchone()[0]
    if existing > 0:
        return
    categories = [('basic', 4, 10), ('research', 4, 10), ('additional', 1, 6)]
    for rank_row in rank_rows:
        rank_id = rank_row[0]
        for cat, min_h, max_h in categories:
            conn.execute(
                'INSERT INTO faculty_workload_rules (rank_id, category, min_hours, max_hours, academic_year) '
                'VALUES (?, ?, ?, ?, ?)',
                (rank_id, cat, min_h, max_h, '2025-2026'),
            )


# /     /     >---- نقصّر أنواع القاعات على القاعات الرسمية (قاعة + معملين)
def _migrate_canonical_room_types(conn: sqlite3.Connection) -> None:
    """Restrict room types to: قاعة دراسية / معمل إلكترونات / معمل حاسوب.

    - Ensures the canonical types exist.
    - Remaps rooms that reference obsolete types (مرسم/مدرج/آخر/معمل عام)
      onto a canonical type inferred from the room name when possible.
    - Deletes obsolete type rows once unreferenced.  Idempotent.
    """
    from database.seed_data import CANONICAL_ROOM_TYPES

    if 'room_types' not in {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }:
        return

    def _type_id(name):
        row = conn.execute('SELECT id FROM room_types WHERE name_ar = ?', (name,)).fetchone()
        return row[0] if row else None

    # 1) Ensure canonical types exist (insert missing ones).
    defaults = {
        'قاعة دراسية': ('Lecture Hall', '🏫', 'hall', 1),
        'معمل إلكترونات': ('Electronics Lab', '🔌', 'lab', 2),
        'معمل حاسوب': ('Computer Lab', '💻', 'lab', 3),
    }
    for name, (en, icon, css, order) in defaults.items():
        if _type_id(name) is None:
            conn.execute(
                'INSERT INTO room_types (name_ar, name_en, icon, css_class, sort_order) '
                'VALUES (?, ?, ?, ?, ?)',
                (name, en, icon, css, order),
            )

    hall_id = _type_id('قاعة دراسية')
    elab_id = _type_id('معمل إلكترونات')
    clab_id = _type_id('معمل حاسوب')

    # 2) Backfill rooms with no type but lab-ish names.
    if clab_id is not None:
        conn.execute(
            "UPDATE rooms SET room_type_id = ? WHERE room_type_id IS NULL "
            "AND name LIKE '%حاسوب%'",
            (clab_id,),
        )
    if elab_id is not None:
        conn.execute(
            "UPDATE rooms SET room_type_id = ? WHERE room_type_id IS NULL "
            "AND name LIKE '%إلكتروني%'",
            (elab_id,),
        )

    # 3) Remap rooms referencing obsolete types.
    conn.execute(
        """
        UPDATE rooms SET room_type_id = CASE
            WHEN name LIKE '%حاسوب%' THEN ?
            WHEN name LIKE '%إلكتروني%' THEN ?
            ELSE COALESCE(?, ?)
        END
        WHERE room_type_id IN (
            SELECT id FROM room_types WHERE name_ar NOT IN (?, ?, ?)
        )
        """,
        (clab_id, elab_id, elab_id, hall_id,
         CANONICAL_ROOM_TYPES[0], CANONICAL_ROOM_TYPES[1], CANONICAL_ROOM_TYPES[2]),
    )

    # 4) Drop obsolete types once nothing references them anymore.
    conn.execute(
        """
        DELETE FROM room_types
        WHERE name_ar NOT IN (?, ?, ?)
          AND id NOT IN (SELECT DISTINCT room_type_id FROM rooms WHERE room_type_id IS NOT NULL)
        """,
        (CANONICAL_ROOM_TYPES[0], CANONICAL_ROOM_TYPES[1], CANONICAL_ROOM_TYPES[2]),
    )
    conn.commit()


# /     /     >---- نغني سجل الإسناد التدريسي بتفاصيل الجدول كاملة
def _migrate_teacher_taught_courses(conn: sqlite3.Connection) -> None:
    """Enrich teacher_taught_courses with full schedule details for the
    teaching-assignment history feature."""
    existing_tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if 'teacher_taught_courses' not in existing_tables:
        return

    # /     /     >---- نضيف الأعمدة الجديدة (idempotent)
    _safe_add_column(conn, 'teacher_taught_courses', 'day', "TEXT NOT NULL DEFAULT ''")
    _safe_add_column(conn, 'teacher_taught_courses', 'start_time', "TEXT NOT NULL DEFAULT ''")
    _safe_add_column(conn, 'teacher_taught_courses', 'end_time', "TEXT NOT NULL DEFAULT ''")
    _safe_add_column(conn, 'teacher_taught_courses', 'period', "TEXT NOT NULL DEFAULT ''")
    _safe_add_column(conn, 'teacher_taught_courses', 'room_id',
                     "INTEGER REFERENCES rooms(id) ON DELETE SET NULL")
    _safe_add_column(conn, 'teacher_taught_courses', 'student_section',
                     "TEXT NOT NULL DEFAULT 'أ'")
    _safe_add_column(conn, 'teacher_taught_courses', 'lecture_type',
                     "TEXT NOT NULL DEFAULT 'theory'")
    _safe_add_column(conn, 'teacher_taught_courses', 'hours', "INTEGER NOT NULL DEFAULT 0")
    _safe_add_column(conn, 'teacher_taught_courses', 'timetable_entry_id', "INTEGER")
    # /     /     >---- هجرة المحتوى مرة وحدة بس
    if _migration_done(conn, 'enrich_teacher_taught_courses'):
        return

    conn.execute('PRAGMA foreign_keys = OFF')
    try:
        # /     /     >---- نربط كل سطر بحصة الجدول المطابقة
        if 'timetable' in existing_tables:
            conn.execute("""
                UPDATE teacher_taught_courses SET
                    timetable_entry_id = (
                        SELECT t.id FROM timetable t
                        LEFT JOIN timetable_versions v ON v.id = t.version_id
                        WHERE t.teacher_id = teacher_taught_courses.teacher_id
                          AND t.course_id = teacher_taught_courses.course_id
                          AND COALESCE(t.department_id, 0) = COALESCE(teacher_taught_courses.department_id, 0)
                          AND COALESCE(t.semester, 1) = teacher_taught_courses.semester
                          AND COALESCE(v.semester_code, '') = teacher_taught_courses.semester_code
                          AND t.deleted_at IS NULL
                        LIMIT 1
                    )
            """)

            # /     /     >---- ننقل تفاصيل الحصة للسجل
            conn.execute("""
                UPDATE teacher_taught_courses SET
                    day = COALESCE((SELECT t.day FROM timetable t WHERE t.id = timetable_entry_id), ''),
                    start_time = COALESCE((SELECT t.start_time FROM timetable t WHERE t.id = timetable_entry_id), ''),
                    end_time = COALESCE((SELECT t.end_time FROM timetable t WHERE t.id = timetable_entry_id), ''),
                    period = COALESCE((SELECT t.period FROM timetable t WHERE t.id = timetable_entry_id), ''),
                    room_id = (SELECT t.room_id FROM timetable t WHERE t.id = timetable_entry_id),
                    student_section = COALESCE((SELECT t.student_section FROM timetable t WHERE t.id = timetable_entry_id), 'أ'),
                    lecture_type = COALESCE((SELECT t.lecture_type FROM timetable t WHERE t.id = timetable_entry_id), 'theory'),
                    hours = COALESCE((SELECT t.hours FROM timetable t WHERE t.id = timetable_entry_id), 0)
                WHERE timetable_entry_id IS NOT NULL
                  AND (day = '' OR day IS NULL)
            """)

        # /     /     >---- نشيل الفهارس القديمة
        old_indexes = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'index' "
            "AND tbl_name = 'teacher_taught_courses'"
        ).fetchall()
        for idx_name, _ in old_indexes:
            try:
                conn.execute(f'DROP INDEX IF EXISTS "{idx_name}"')
            except Exception:
                pass

        # /     /     >---- نجيب السطور القديمة قبل ما نعيد بناء الجدول
        old_rows = conn.execute('SELECT * FROM teacher_taught_courses').fetchall()
        old_cols = [d[1] for d in conn.execute(
            'PRAGMA table_info(teacher_taught_courses)'
        ).fetchall()]

        # /     /     >---- نعيد بناء الجدول بالتفاصيل الجديدة
        conn.execute('DROP TABLE teacher_taught_courses')
        conn.execute("""
            CREATE TABLE teacher_taught_courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
                course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
                semester INTEGER NOT NULL DEFAULT 1,
                semester_code TEXT NOT NULL DEFAULT '',
                version_id INTEGER,
                day TEXT NOT NULL DEFAULT '',
                start_time TEXT NOT NULL DEFAULT '',
                end_time TEXT NOT NULL DEFAULT '',
                period TEXT NOT NULL DEFAULT '',
                room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL,
                student_section TEXT NOT NULL DEFAULT 'أ',
                lecture_type TEXT NOT NULL DEFAULT 'theory',
                hours INTEGER NOT NULL DEFAULT 0,
                timetable_entry_id INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(teacher_id, course_id, department_id, semester, semester_code, day, period, student_section)
            )
        """)

        # /     /     >---- نعيد إدخال السطور مع القيم المفترضة
        for row in old_rows:
            row_dict = dict(zip(old_cols, row))
            conn.execute(
                'INSERT INTO teacher_taught_courses '
                '(id, teacher_id, course_id, department_id, semester, semester_code, version_id, '
                ' day, start_time, end_time, period, room_id, student_section, lecture_type, '
                ' hours, timetable_entry_id, created_at) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    row_dict['id'],
                    row_dict['teacher_id'],
                    row_dict['course_id'],
                    row_dict.get('department_id'),
                    row_dict.get('semester', 1),
                    row_dict.get('semester_code', ''),
                    row_dict.get('version_id'),
                    row_dict.get('day', ''),
                    row_dict.get('start_time', ''),
                    row_dict.get('end_time', ''),
                    row_dict.get('period', ''),
                    row_dict.get('room_id'),
                    row_dict.get('student_section', 'أ'),
                    row_dict.get('lecture_type', 'theory'),
                    row_dict.get('hours', 0),
                    row_dict.get('timetable_entry_id'),
                    row_dict.get('created_at', ''),
                ),
            )
    finally:
        conn.execute('PRAGMA foreign_keys = ON')

    # /     /     >---- فهارس جديدة للسجل
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_ttc_teacher_semester '
        'ON teacher_taught_courses (teacher_id, semester_code)'
    )
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_ttc_entry '
        'ON teacher_taught_courses (timetable_entry_id)'
    )

    _mark_migration_done(conn, 'enrich_teacher_taught_courses')
    conn.commit()


# /     /     >---- رمز الدخول المؤقت لأعضاء هيئة التدريس (ينشئه مكتب أعضاء الهيئة)
def _migrate_initial_login_columns(conn: sqlite3.Connection) -> None:
    """Add temporary initial-login columns to ``users``.

    When the Faculty Office creates a new faculty member, the system mints a
    one-time initial login code that is emailed to the member.  The code is
    stored in hashed form (never plain text), expires after a short window,
    and is invalidated on the first successful login (``initial_login_code_used``).
    """
    cols = _get_column_names(conn, 'users')
    if not cols:
        return
    for col, ddl in [
        # /     /     >---- رمز الدخول المؤقت (يُحفظ مُشفّراً — لا نصوص صريحة)
        ('initial_login_code_hash', 'TEXT'),
        # /     /     >---- هل استعمل الرمز فعلاً؟ (يفسد بعد أول دخول ناجح)
        ('initial_login_code_used', 'INTEGER NOT NULL DEFAULT 0'),
        # /     /     >---- تنتهي صلاحية الرمز بعد هذه اللحظة
        ('initial_login_code_expires', 'TIMESTAMP'),
        # /     /     >---- هل أُرسل البريد بالرمز؟ (لمنع إعادة إرسال متكررة)
        ('initial_login_code_email_sent_at', 'TIMESTAMP'),
    ]:
        if col not in cols:
            _safe_add_column(conn, 'users', col, ddl)


# /     /     >---- الشعبة (A/B/C) للقسم العام في الجدول الدراسي
def _migrate_timetable_section(conn: sqlite3.Connection) -> None:
    """Add ``section`` to ``timetable`` for General Department sections A/B/C.

    The General Department (``القسم العام``) has ONE main semester but several
    parallel sections (شعبة أ/ب/ج); those are SECTIONS, not additional
    semesters.  The column is nullable and only meaningful for that department.
    """
    cols = _get_column_names(conn, 'timetable')
    if not cols:
        return
    if 'section' not in cols:
        _safe_add_column(conn, 'timetable', 'section', "TEXT DEFAULT ''")


# /     /     >---- توسيع جدول الامتحانات: شعب/مجموعات وموقع وتعدد أسابيع
def _migrate_exam_schedule_columns(conn: sqlite3.Connection) -> None:
    """Extend ``exam_schedule`` for the second administrative exam stage.

    After the department creates its exam timetable, the examination
    administration can edit it: change course/date/day/time/room/location,
    split exams into groups/parts, and spread schedules over 2+ weeks.
    These columns support that workflow.
    """
    cols = _get_column_names(conn, 'exam_schedule')
    if not cols:
        return
    for col, ddl in [
        # /     /     >---- قسمة الامتحان لمجموعات/أجزاء
        ('group_number', 'INTEGER NOT NULL DEFAULT 1'),
        ('group_label', "TEXT DEFAULT ''"),
        # /     /     >---- الموقع (مبنى/قاعة بديلة عند التعديل)
        ('location', "TEXT DEFAULT ''"),
        # /     /     >---- أسبوع الامتحان (دعم جدول يمتد لأسبوعين أو أكثر)
        ('week_number', 'INTEGER NOT NULL DEFAULT 1'),
        # /     /     >---- مدة الامتحان بالدقائق (قابلة للتعديل)
        ('duration_minutes', 'INTEGER DEFAULT 0'),
        # /     /     >---- جهة/مكتب آخر تعديل (تدقيق سير العمل)
        ('last_edited_by', "TEXT DEFAULT ''"),
        ('last_edited_at', 'TIMESTAMP'),
    ]:
        if col not in cols:
            _safe_add_column(conn, 'exam_schedule', col, ddl)


# /     /     >---- تحصين الرموز: إخفاء أي رمز دخول مؤقت قديم غير مهشم
def _migrate_obscure_legacy_initial_codes(conn: sqlite3.Connection) -> None:
    """Best-effort cleanup: never leave plain initial codes visible.

    If a legacy path stored a raw code string (in case it was ever written),
    blank it out here so the Faculty Office view can never display a plain
    credential again.  Idempotent and additive — no user data is touched.
    """
    cols = _get_column_names(conn, 'users')
    if not cols or 'initial_login_code_hash' not in cols:
        return
    for legacy in ('initial_login_code', 'initial_code', 'initial_login_code_plain_latest'):
        if legacy in cols:
            conn.execute(
                f'UPDATE users SET {legacy} = NULL WHERE {legacy} IS NOT NULL'
            )


def _split_top_level_commas(sql: str) -> list[str]:
    """Split SQL declarations on commas at the top level only."""
    parts: list[str] = []
    current = []
    depth = 0
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if ch in '([':
                depth += 1
            elif ch in ')]':
                depth = max(0, depth - 1)
            elif ch == ',' and depth == 0:
                part = ''.join(current).strip()
                if part:
                    parts.append(part)
                current = []
                i += 1
                continue
        current.append(ch)
        i += 1
    tail = ''.join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _schema_column_map() -> dict[str, dict[str, str]]:
    """Extract column definitions from database/schema.sql for legacy backfills."""
    schema_path = Path(__file__).with_name('schema.sql')
    if not schema_path.exists():
        return {}

    text = schema_path.read_text(encoding='utf-8')
    tables: dict[str, dict[str, str]] = {}
    matches = re.finditer(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\)\s*;',
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in matches:
        table_name = match.group(1).lower()
        body = match.group(2)
        columns: dict[str, str] = {}
        for chunk in _split_top_level_commas(body):
            stripped = chunk.strip()
            if not stripped or stripped.upper().startswith(('PRIMARY', 'UNIQUE', 'FOREIGN', 'CHECK', 'CONSTRAINT')):
                continue
            column_match = re.match(r'"?([A-Za-z_][A-Za-z0-9_]*)"?\s+(.+)', stripped, flags=re.IGNORECASE)
            if not column_match:
                continue
            columns[column_match.group(1).lower()] = column_match.group(2).strip()
        tables[table_name] = columns
    return tables


_SCHEMA_COLUMN_MAP = _schema_column_map()


def _ensure_core_identity_schema(conn: sqlite3.Connection) -> None:
    """Backfill core identity tables for older SQLite databases created before
    the full schema.sql was applied.
    """
    existing_tables = {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }

    if 'users' not in existing_tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'teacher',
                label TEXT DEFAULT '',
                department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
                email TEXT,
                phone TEXT,
                password_changed_at TIMESTAMP,
                is_active INTEGER NOT NULL DEFAULT 1,
                force_password_change INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    if 'user_roles' not in existing_tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, role)
            )
        """)
    if 'teachers' not in existing_tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS teachers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                department TEXT,
                academic_number TEXT,
                national_id TEXT,
                qualification TEXT,
                academic_rank TEXT,
                classification TEXT,
                contract_date TEXT,
                tasks TEXT,
                department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
                hod_department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
                qualification_id INTEGER REFERENCES qualifications(id) ON DELETE SET NULL,
                rank_id INTEGER REFERENCES academic_ranks(id) ON DELETE SET NULL,
                classification_id INTEGER REFERENCES classifications(id) ON DELETE SET NULL,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    for table_name, columns in _SCHEMA_COLUMN_MAP.items():
        if table_name not in {t.lower() for t in existing_tables}:
            continue
        for column_name, ddl in columns.items():
            if column_name.lower() not in {c.lower() for c in _get_column_names(conn, table_name)}:
                _safe_add_column(conn, table_name, column_name, ddl)


# /     /     >---- الوظيفة الرئيسية: نضمن كل الجداول والهجرات
def ensure_schema(conn: sqlite3.Connection) -> None:
    _ensure_core_identity_schema(conn)
    _ensure_migration_log(conn)
    _cleanup_legacy_user_data(conn)
    _deduplicate_teachers_v1(conn)
    _verify_teacher_fk_integrity(conn)
    _ensure_academic_number_index(conn)

    _migrate_course_content_teacher_nullable(conn)
    _migrate_course_content_teacher_name(conn)
    existing_tables = {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    # /     /     >---- نشيل جداول الطلاب القديمة
    _drop_student_schema(conn)
    existing_tables = {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    # /     /     >---- نضيف deleted_at للجداول ذات الحذف الناعم
    from database.constants import SOFT_DELETE_TABLES
    for table in SOFT_DELETE_TABLES:
        if table in existing_tables:
            cols = _get_column_names(conn, table)
            if 'deleted_at' not in cols:
                _safe_add_column(conn, table, 'deleted_at', 'TIMESTAMP')

    # /     /     >---- تخصصات الأقسام (لقواعد البيانات القديمة)
    if 'department_majors' not in existing_tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS department_majors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                department_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    # Migration: add status column to exam_schedule for workflow (draft/submitted/received/merged/published)
    if 'exam_schedule' in existing_tables:
        exam_columns = _get_column_names(conn, 'exam_schedule')
        if 'status' not in exam_columns:
            _safe_add_column(conn, 'exam_schedule', 'status', "TEXT NOT NULL DEFAULT 'draft'")
        if 'merged_at' not in exam_columns:
            _safe_add_column(conn, 'exam_schedule', 'merged_at', 'TIMESTAMP')
        if 'published_at' not in exam_columns:
            _safe_add_column(conn, 'exam_schedule', 'published_at', 'TIMESTAMP')

    # /     /     >---- جدول المتطلبات السابقة
    if 'course_prerequisites' not in existing_tables:
        conn.execute("""
            CREATE TABLE course_prerequisites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                prerequisite_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(course_id, prerequisite_id)
            )
        """)

    # /     /     >---- جدول أقسام المقرر (أي مقرر في عدة أقسام)
    if 'course_departments' not in existing_tables:
        conn.execute("""
            CREATE TABLE course_departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                department_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
                semester INTEGER DEFAULT 1,
                UNIQUE(course_id, department_id)
            )
        """)

    # Per-department semester: allow the same course to sit in different
    # semesters in different departments. Backfill existing rows from the
    # (still global) courses.semester value.
    if 'course_departments' in existing_tables or 'course_departments' in {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }:
        cd_cols = _get_column_names(conn, 'course_departments')
        if 'semester' not in cd_cols:
            _safe_add_column(conn, 'course_departments', 'semester', 'INTEGER DEFAULT 1')
        conn.execute(
            'UPDATE course_departments '
            'SET semester = (SELECT c.semester FROM courses c WHERE c.id = course_departments.course_id) '
            'WHERE semester IS NULL'
        )
    conn.commit()

    # /     /     >---- عضوية الأستاذ في عدة أقسام
    if 'teacher_departments' not in existing_tables:
        conn.execute("""
            CREATE TABLE teacher_departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
                department_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
                UNIQUE(teacher_id, department_id)
            )
        """)
        # /     /     >---- نعبّي من القسم الأساسي للأساتذة
        conn.execute("""
            INSERT OR IGNORE INTO teacher_departments (teacher_id, department_id)
            SELECT id, department_id FROM teachers
            WHERE department_id IS NOT NULL
        """)
        conn.commit()

    # /     /     >---- سجل الإسناد التدريسي التلقائي لكل حصة
    if 'teacher_taught_courses' not in existing_tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS teacher_taught_courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
                course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
                semester INTEGER NOT NULL DEFAULT 1,
                semester_code TEXT NOT NULL DEFAULT '',
                version_id INTEGER,
                day TEXT NOT NULL DEFAULT '',
                start_time TEXT NOT NULL DEFAULT '',
                end_time TEXT NOT NULL DEFAULT '',
                period TEXT NOT NULL DEFAULT '',
                room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL,
                student_section TEXT NOT NULL DEFAULT 'أ',
                lecture_type TEXT NOT NULL DEFAULT 'theory',
                hours INTEGER NOT NULL DEFAULT 0,
                timetable_entry_id INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(teacher_id, course_id, department_id, semester, semester_code, day, period, student_section)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ttc_teacher_semester
            ON teacher_taught_courses (teacher_id, semester_code)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ttc_entry
            ON teacher_taught_courses (timetable_entry_id)
        """)
        # Backfill from every saved timetable entry (older versions keep
        # their own semester_code; legacy rows fall back to '').
        # Skipped on fresh databases where timetable_versions does not exist
        # yet (it is created further below) — there is no timetable data to
        # backfill on a fresh install anyway.
        if 'timetable_versions' in existing_tables:
            conn.execute("""
                INSERT OR IGNORE INTO teacher_taught_courses
                    (teacher_id, course_id, department_id, semester, semester_code, version_id)
                SELECT t.teacher_id, t.course_id, t.department_id,
                       COALESCE(t.semester, 1),
                       COALESCE(v.semester_code, ''),
                       t.version_id
                FROM timetable t
                LEFT JOIN timetable_versions v ON v.id = t.version_id
                WHERE t.teacher_id IS NOT NULL AND t.course_id IS NOT NULL
            """)
            conn.commit()

    # /     /     >---- نضيف أعمدة المقررات الناقصة
    if 'courses' in existing_tables:
        course_columns = _get_column_names(conn, 'courses')
        if 'year' not in course_columns:
            _safe_add_column(conn, 'courses', 'year', 'INTEGER NOT NULL DEFAULT 1')
        if 'notes' not in course_columns:
            _safe_add_column(conn, 'courses', 'notes', 'TEXT')
        if 'theoretical_hours' not in course_columns:
            _safe_add_column(conn, 'courses', 'theoretical_hours', 'INTEGER NOT NULL DEFAULT 0')
        if 'practical_hours' not in course_columns:
            _safe_add_column(conn, 'courses', 'practical_hours', 'INTEGER NOT NULL DEFAULT 0')
        if 'total_hours' not in course_columns:
            _safe_add_column(conn, 'courses', 'total_hours', 'INTEGER NOT NULL DEFAULT 0')
        if 'accreditation' not in course_columns:
            _safe_add_column(conn, 'courses', 'accreditation', 'TEXT')
        if 'vocabulary' not in course_columns:
            _safe_add_column(conn, 'courses', 'vocabulary', 'TEXT')
        if 'syllabus_file' not in course_columns:
            _safe_add_column(conn, 'courses', 'syllabus_file', 'TEXT')
        if 'semester' not in course_columns:
            _safe_add_column(conn, 'courses', 'semester', 'INTEGER DEFAULT 1')
        if 'icon' not in course_columns:
            _safe_add_column(conn, 'courses', 'icon', "TEXT DEFAULT '📖'")

    # /     /     >---- نحدّث أيقونات المقررات حسب أسمائها
    if 'courses' in existing_tables:
        courses_without_icons = conn.execute(
            "SELECT id, name FROM courses WHERE icon = '📖' OR icon IS NULL"
        ).fetchall()
        for course in courses_without_icons:
            icon = COURSE_ICON_MAP.get(course['name'], DEFAULT_COURSE_ICON)
            conn.execute('UPDATE courses SET icon = ? WHERE id = ?', (icon, course['id']))
        if courses_without_icons:
            conn.commit()

    conn.commit()

    # /     /     >---- نضيف أعمدة الأساتذة الناقصة
    if 'teachers' in existing_tables:
        teacher_columns = _get_column_names(conn, 'teachers')
        if 'academic_number' not in teacher_columns:
            _safe_add_column(conn, 'teachers', 'academic_number', 'TEXT')
        if 'national_id' not in teacher_columns:
            _safe_add_column(conn, 'teachers', 'national_id', 'TEXT')
        if 'qualification' not in teacher_columns:
            _safe_add_column(conn, 'teachers', 'qualification', 'TEXT')
        if 'academic_rank' not in teacher_columns:
            _safe_add_column(conn, 'teachers', 'academic_rank', 'TEXT')
        if 'classification' not in teacher_columns:
            _safe_add_column(conn, 'teachers', 'classification', 'TEXT')
        if 'phone' not in teacher_columns:
            _safe_add_column(conn, 'teachers', 'phone', 'TEXT')
        if 'contract_date' not in teacher_columns:
            _safe_add_column(conn, 'teachers', 'contract_date', 'TEXT')
        if 'tasks' not in teacher_columns:
            _safe_add_column(conn, 'teachers', 'tasks', 'TEXT')
        if 'specialization' not in teacher_columns:
            _safe_add_column(conn, 'teachers', 'specialization', 'TEXT')
        if 'photo_filename' not in teacher_columns:
            _safe_add_column(conn, 'teachers', 'photo_filename', 'TEXT')
        if 'position' not in teacher_columns:
            _safe_add_column(conn, 'teachers', 'position', 'TEXT')
        if 'semester' not in teacher_columns:
            _safe_add_column(conn, 'teachers', 'semester', 'TEXT')
        if 'section' not in teacher_columns:
            _safe_add_column(conn, 'teachers', 'section', 'TEXT')
        if 'first_lecture_date' not in teacher_columns:
            _safe_add_column(conn, 'teachers', 'first_lecture_date', 'TEXT')
        if 'work_start_date' not in teacher_columns:
            _safe_add_column(conn, 'teachers', 'work_start_date', 'TEXT')
        if 'general_notes' not in teacher_columns:
            _safe_add_column(conn, 'teachers', 'general_notes', 'TEXT')
        if 'department_id' not in teacher_columns:
            _safe_add_column(conn, 'teachers', 'department_id', 'INTEGER REFERENCES departments(id) ON DELETE SET NULL')
        if 'specialization_id' not in teacher_columns:
            _safe_add_column(conn, 'teachers', 'specialization_id', 'INTEGER REFERENCES specializations(id) ON DELETE SET NULL')
        if 'hod_department_id' not in teacher_columns:
            _safe_add_column(conn, 'teachers', 'hod_department_id', 'INTEGER REFERENCES departments(id) ON DELETE SET NULL')

    # /     /     >---- نضيف أعمدة المستخدمين الناقصة
    if 'users' in existing_tables:
        user_columns = _get_column_names(conn, 'users')
        if 'department_id' not in user_columns:
            _safe_add_column(conn, 'users', 'department_id', 'INTEGER REFERENCES departments(id) ON DELETE SET NULL')
        if 'email' not in user_columns:
            _safe_add_column(conn, 'users', 'email', 'TEXT')
        if 'password_changed_at' not in user_columns:
            _safe_add_column(conn, 'users', 'password_changed_at', 'TIMESTAMP')
        if 'force_password_change' not in user_columns:
            _safe_add_column(conn, 'users', 'force_password_change',
                             'INTEGER NOT NULL DEFAULT 0')
        if 'phone' not in user_columns:
            _safe_add_column(conn, 'users', 'phone', 'TEXT')
        if 'theme' not in user_columns:
            _safe_add_column(conn, 'users', 'theme', "TEXT DEFAULT 'light'")
        if 'administrative_department_id' not in user_columns:
            _safe_add_column(conn, 'users', 'administrative_department_id',
                             'INTEGER REFERENCES departments(id) ON DELETE SET NULL')
            # /     /     >---- ننقل قسم الأدوار الإدارية للعمود الإداري
            for role in ('research_development', 'faculty_affairs'):
                conn.execute(
                    """UPDATE users SET administrative_department_id = department_id,
                       department_id = NULL
                       WHERE role = ? AND department_id IS NOT NULL""",
                    (role,),
                )
        if 'supervisor_admin_dept' not in user_columns:
            _safe_add_column(conn, 'users', 'supervisor_admin_dept', "TEXT DEFAULT ''")
        if 'is_active' not in user_columns:
            _safe_add_column(conn, 'users', 'is_active', 'INTEGER NOT NULL DEFAULT 1')
        # /     /     >---- نموذج الأدوار الجديد
        _migrate_role_model(conn)
        _migrate_user_roles(conn)
        # /     /     >---- رمز الدخول المؤقت لأعضاء هيئة التدريس
        _migrate_initial_login_columns(conn)
        _migrate_obscure_legacy_initial_codes(conn)

    # /     /     >---- طلبات استرجاع كلمة المرور
    if 'password_resets' not in existing_tables:
        conn.execute("""
            CREATE TABLE password_resets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_password_resets_token ON password_resets(token)')

    # /     /     >---- نضيف أعمدة القاعات الناقصة
    if 'rooms' in existing_tables:
        room_columns = _get_column_names(conn, 'rooms')
        if 'department_id' not in room_columns:
            _safe_add_column(conn, 'rooms', 'department_id', 'INTEGER REFERENCES departments(id) ON DELETE SET NULL')
        if 'building' not in room_columns:
            _safe_add_column(conn, 'rooms', 'building', 'TEXT DEFAULT ""')
        for col, ddl in [
            ('computers', 'INTEGER DEFAULT 0'),
            ('electronic_devices', 'INTEGER DEFAULT 0'),
            ('easels', 'INTEGER DEFAULT 0'),
            ('whiteboards', 'INTEGER DEFAULT 0'),
            ('projectors', 'INTEGER DEFAULT 0'),
            ('lab_type', 'TEXT DEFAULT ""'),
            ('has_stage', 'INTEGER DEFAULT 0'),
            ('theater_seats', 'INTEGER DEFAULT 0'),
            ('workstations', 'INTEGER DEFAULT 0'),
            ('bookable', 'INTEGER DEFAULT 1'),
        ]:
            if col not in room_columns:
                _safe_add_column(conn, 'rooms', col, ddl)

    # /     /     >---- نضيف أعمدة سجل الحركات المستخدم
    if 'history' in existing_tables:
        history_columns = _get_column_names(conn, 'history')
        if 'actor_user_id' not in history_columns:
            _safe_add_column(conn, 'history', 'actor_user_id', 'INTEGER')
        if 'actor_username' not in history_columns:
            _safe_add_column(conn, 'history', 'actor_username', 'TEXT')
        if 'message' not in history_columns:
            _safe_add_column(conn, 'history', 'message', 'TEXT')

    _ensure_periods_table(conn)

    # /     /     >---- القسم العام فصل واحد، والباقي أقصى 8 (حق التدريب الميداني ومشروع التخرج)
    if 'departments' in existing_tables:
        conn.execute("UPDATE departments SET semesters = 1 WHERE name = 'القسم العام'")
        conn.execute("UPDATE departments SET semesters = 8 WHERE name != 'القسم العام' AND semesters > 8")

    # /     /     >---- نضيف أعمدة الأقسام الناقصة
    if 'departments' in existing_tables:
        dept_columns = _get_column_names(conn, 'departments')
        if 'hidden' not in dept_columns:
            _safe_add_column(conn, 'departments', 'hidden', 'INTEGER NOT NULL DEFAULT 0')
        if 'has_sections' not in dept_columns:
            _safe_add_column(conn, 'departments', 'has_sections', 'INTEGER NOT NULL DEFAULT 1')
        if 'type' not in dept_columns:
            _safe_add_column(conn, 'departments', 'type', "TEXT NOT NULL DEFAULT 'academic'")
            # /     /     >---- نملأ النوع من hidden
            conn.execute("UPDATE departments SET type = 'administrative' WHERE hidden = 1")
            conn.execute("UPDATE departments SET type = 'academic' WHERE hidden = 0 AND type = 'academic'")
        if 'icon' not in dept_columns:
            _safe_add_column(conn, 'departments', 'icon', "TEXT DEFAULT ''")
        if 'accent_color' not in dept_columns:
            _safe_add_column(conn, 'departments', 'accent_color', "TEXT DEFAULT ''")
        if 'description' not in dept_columns:
            _safe_add_column(conn, 'departments', 'description', 'TEXT')
        if 'display_name' not in dept_columns:
            _safe_add_column(conn, 'departments', 'display_name', 'TEXT')
        if 'abbreviation' not in dept_columns:
            _safe_add_column(conn, 'departments', 'abbreviation', 'TEXT')
        # /     /     >---- ترحيل الأنظمة القديمة: الأقسام الأكاديمية المقيدة بـ 7 فصول تُرفع إلى 8
        if 'type' in _get_column_names(conn, 'departments'):
            conn.execute("UPDATE departments SET semesters = 8 WHERE name != 'القسم العام' AND type = 'academic' AND semesters = 7")

    # /     /     >---- ملفات الأقسام العامة (نبذة/رؤية/رسالة...)
    if 'department_profiles' not in existing_tables:
        conn.execute("""
            CREATE TABLE department_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                department_id INTEGER NOT NULL UNIQUE REFERENCES departments(id) ON DELETE CASCADE,
                about TEXT,
                vision TEXT,
                mission TEXT,
                objectives TEXT,
                study_fields TEXT,
                skills TEXT,
                labs TEXT,
                labs_note TEXT,
                practical_training TEXT,
                careers TEXT,
                further_study TEXT,
                word TEXT,
                requirements TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    # /     /     >---- نطابق المفردات المرجعية مع القوائم الحالية
    _migrate_lookup_vocabulary(conn)
    # /     /     >---- نتأكد الجداول المرجعية موجودة ومتعبّاة
    _ensure_lookup_tables(conn)
    # /     /     >---- نملأ الفهارس الخارجية للقاعات والأساتذة من النصوص
    _backfill_room_fks(conn)
    _backfill_teacher_fks(conn)

    # /     /     >---- نضيف عمود القسم للجدول (لعزل الأقسام)
    if 'timetable' in existing_tables:
        tt_columns = _get_column_names(conn, 'timetable')
        if 'department_id' not in tt_columns:
            _safe_add_column(conn, 'timetable', 'department_id', 'INTEGER REFERENCES departments(id) ON DELETE SET NULL')
        if 'student_section' not in tt_columns:
            _safe_add_column(conn, 'timetable', 'student_section', "TEXT DEFAULT 'أ'")
        if 'start_time' not in tt_columns:
            _safe_add_column(conn, 'timetable', 'start_time', 'TEXT DEFAULT ""')
        if 'end_time' not in tt_columns:
            _safe_add_column(conn, 'timetable', 'end_time', 'TEXT DEFAULT ""')
        # /     /     >---- شعبة أ/ب/ج للقسم العام (شعب وليست فصولاً)
        _migrate_timetable_section(conn)

    # /     /     >---- أعمدة التوقيع لجدول الامتحانات
    if 'exam_schedule' in existing_tables:
        es_columns = _get_column_names(conn, 'exam_schedule')
        if 'signed_by_hod' not in es_columns:
            _safe_add_column(conn, 'exam_schedule', 'signed_by_hod', 'INTEGER NOT NULL DEFAULT 0')
        if 'signed_at' not in es_columns:
            _safe_add_column(conn, 'exam_schedule', 'signed_at', 'TIMESTAMP')
        if 'exam_date' not in es_columns:
            _safe_add_column(conn, 'exam_schedule', 'exam_date', 'TEXT DEFAULT ""')
        if 'signed_by_user_id' not in es_columns:
            _safe_add_column(conn, 'exam_schedule', 'signed_by_user_id', 'INTEGER')
        if 'signed_by_username' not in es_columns:
            _safe_add_column(conn, 'exam_schedule', 'signed_by_username', 'TEXT DEFAULT ""')
        if 'created_by_user_id' not in es_columns:
            _safe_add_column(conn, 'exam_schedule', 'created_by_user_id', 'INTEGER REFERENCES users(id) ON DELETE SET NULL')
        if 'exam_type' not in es_columns:
            _safe_add_column(conn, 'exam_schedule', 'exam_type', "TEXT DEFAULT ''")
        if 'week' not in es_columns:
            _safe_add_column(conn, 'exam_schedule', 'week', 'INTEGER NOT NULL DEFAULT 1')
        if 'day_ar' not in es_columns:
            _safe_add_column(conn, 'exam_schedule', 'day_ar', "TEXT NOT NULL DEFAULT ''")

    # /     /     >---- المرحلة الإدارية الثانية لجدول الامتحانات (تعديل/تقسيم/توزيع)
    _migrate_exam_schedule_columns(conn)

    # /     /     >---- نملأ يوم الأسبوع العربي من تاريخ الامتحان
    if 'exam_schedule' in existing_tables:
        conn.execute("""UPDATE exam_schedule SET day_ar = CASE CAST(strftime('%w', exam_date) AS INTEGER)
            WHEN 0 THEN 'الأحد' WHEN 1 THEN 'الاثنين' WHEN 2 THEN 'الثلاثاء'
            WHEN 3 THEN 'الأربعاء' WHEN 4 THEN 'الخميس'
            ELSE day_ar END
            WHERE exam_date != '' AND day_ar = ''""")

    _migrate_department_fks(conn)
    # /     /     >---- كل قسم أكاديمي يوصل للفصل الثامن (تدريب ميداني/مشروع تخرج)
    _migrate_department_semesters_eight(conn)
    _ensure_runtime_indexes(conn)
    conn.execute('CREATE INDEX IF NOT EXISTS idx_history_created_at ON history(created_at DESC)')
    if 'faculty_attendance' in {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }:
        conn.execute('CREATE INDEX IF NOT EXISTS idx_faculty_attendance_teacher ON faculty_attendance(teacher_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_faculty_attendance_date ON faculty_attendance(date)')

    # ── Messaging / Objection System tables ──────────────────────────
    # /     /     >---- رسائل/اعتراضات الأساتذة
    if 'teacher_messages' not in existing_tables:
        conn.execute("""
            CREATE TABLE teacher_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
                department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
                subject TEXT NOT NULL,
                message TEXT NOT NULL,
                message_type TEXT DEFAULT 'objection',
                related_lecture_id INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                resolved_by INTEGER REFERENCES users(id)
            )
        """)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_teacher_messages_teacher ON teacher_messages(teacher_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_teacher_messages_dept ON teacher_messages(department_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_teacher_messages_status ON teacher_messages(status)')

    # /     /     >---- وثائق الأساتذة
    if 'teacher_documents' not in existing_tables:
        conn.execute("""
            CREATE TABLE teacher_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                original_name TEXT NOT NULL,
                file_size INTEGER,
                file_type TEXT,
                description TEXT,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_teacher_documents_teacher ON teacher_documents(teacher_id)')

    # /     /     >---- ردود الرسائل
    if 'message_replies' not in existing_tables:
        conn.execute("""
            CREATE TABLE message_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL REFERENCES teacher_messages(id) ON DELETE CASCADE,
                sender_id INTEGER REFERENCES users(id),
                reply_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_message_replies_message ON message_replies(message_id)')

    # /     /     >---- مواد الأساتذة (رفع ملفات للمقررات)
    if 'teacher_materials' not in existing_tables:
        conn.execute("""
            CREATE TABLE teacher_materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
                course_id INTEGER REFERENCES courses(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                file_size INTEGER DEFAULT 0,
                file_type TEXT DEFAULT '',
                is_visible INTEGER NOT NULL DEFAULT 1,
                download_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_teacher_materials_teacher ON teacher_materials(teacher_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_teacher_materials_dept ON teacher_materials(department_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_teacher_materials_course ON teacher_materials(course_id)')

    # /     /     >---- الإشعارات
    if 'notifications' not in existing_tables:
        conn.execute("""
            CREATE TABLE notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'info',
                related_type TEXT DEFAULT '',
                related_id INTEGER DEFAULT 0,
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(user_id, is_read)')

    # /     /     >---- طلبات الأساتذة (رسائل/اعتراضات/طلبات)
    if 'teacher_requests' not in existing_tables:
        conn.execute("""
            CREATE TABLE teacher_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
                request_type TEXT NOT NULL DEFAULT 'general',
                subject TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                admin_reply TEXT DEFAULT '',
                reviewed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                reviewed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_teacher_requests_teacher ON teacher_requests(teacher_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_teacher_requests_dept ON teacher_requests(department_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_teacher_requests_status ON teacher_requests(status)')

    # /     /     >---- إعلانات الأقسام
    if 'department_announcements' not in existing_tables:
        conn.execute("""
            CREATE TABLE department_announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                department_id INTEGER REFERENCES departments(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'normal',
                is_published INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_dept_announcements_dept ON department_announcements(department_id)')

    # /     /     >---- إزالة طلبات تبديل القاعات (ميزة محذوفة من النظام)
    if 'classroom_change_requests' in existing_tables:
        conn.execute('DROP TABLE IF EXISTS classroom_change_requests')
        conn.execute("DELETE FROM history WHERE entity_type = 'classroom_change_request'")

    # /     /     >---- إعدادات الامتحانات
    if 'exam_settings' not in existing_tables:
        conn.execute("""
            CREATE TABLE exam_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_start_date TEXT DEFAULT '',
                exam_end_date TEXT DEFAULT '',
                session_a TEXT DEFAULT '08:30',
                session_b TEXT DEFAULT '11:30',
                session_c TEXT DEFAULT '14:30',
                proctors_per_room INTEGER DEFAULT 2,
                avoid_relatives INTEGER DEFAULT 1,
                auto_notify INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("INSERT INTO exam_settings (id) VALUES (1)")

    if 'exam_settings' in existing_tables:
        exam_set_cols = _get_column_names(conn, 'exam_settings')
        if 'exam_start_time' not in exam_set_cols:
            _safe_add_column(conn, 'exam_settings', 'exam_start_time', "TEXT DEFAULT '09:00'")
        if 'exam_end_time' not in exam_set_cols:
            _safe_add_column(conn, 'exam_settings', 'exam_end_time', "TEXT DEFAULT '17:00'")
        if 'period_status' not in exam_set_cols:
            _safe_add_column(conn, 'exam_settings', 'period_status', "TEXT DEFAULT 'draft'")
        if 'last_modified_by' not in exam_set_cols:
            _safe_add_column(conn, 'exam_settings', 'last_modified_by', "TEXT DEFAULT ''")
        if 'last_modified_at' not in exam_set_cols:
            _safe_add_column(conn, 'exam_settings', 'last_modified_at', "TEXT DEFAULT ''")

    # ── Named semesters migration ───────────────────────────────────────
    # Migrate from academic_year (TEXT '2025-2026') to semester_code (TEXT 'fall_2026')
    # and add semester_code to timetable_versions.
    _migrate_to_named_semesters(conn)

    # ── Timetable versions: ensure columns + backfill ──────────────────
    if 'timetable' in existing_tables:
        if 'timetable_versions' not in existing_tables:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS timetable_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
                    semester INTEGER NOT NULL,
                    semester_code TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(department_id, semester, semester_code)
                )
            """)

        tt_columns = _get_column_names(conn, 'timetable')
        if 'version_id' not in tt_columns:
            _safe_add_column(conn, 'timetable', 'version_id', 'INTEGER')
        if 'lecture_type' not in tt_columns:
            _safe_add_column(conn, 'timetable', 'lecture_type', "TEXT DEFAULT 'theory'")
        if 'hours' not in tt_columns:
            _safe_add_column(conn, 'timetable', 'hours', 'INTEGER NOT NULL DEFAULT 0')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_timetable_version_id ON timetable(version_id)')

        # /     /     >---- نربط السطور القديمة (بدون نسخة) بنسخة حالية
        unassigned = conn.execute(
            'SELECT DISTINCT department_id, semester FROM timetable '
            'WHERE version_id IS NULL AND department_id IS NOT NULL'
        ).fetchall()
        for row in unassigned:
            dept_id, semester = row['department_id'], row['semester']
            semester_code = _current_semester_code(conn)
            version_id = _ensure_version_v2(conn, dept_id, semester, semester_code)
            conn.execute(
                'UPDATE timetable SET version_id = ? '
                'WHERE department_id = ? AND semester = ? AND version_id IS NULL',
                (version_id, dept_id, semester),
            )
        # /     /     >---- القديم بدون نوع ياخد theory
        conn.execute(
            "UPDATE timetable SET lecture_type = 'theory' WHERE lecture_type IS NULL"
        )
        conn.commit()

    # ── Teacher ↔ department membership backfill ──────────────────────
    # A department applies to a teacher when ANY of these holds:
    #   (a) it is the teacher's primary department (teachers.department_id),
    #   (b) the teacher was chosen in a lecture-assignment stage (active
    #       timetable entries / teacher_taught_courses),
    #   (c) the teacher heads the department (teachers.hod_department_id).
    # teacher_departments is the many-to-many source of truth used by the HOD
    # member lists, _can_hod_view_teacher and the teacher profile.  This block
    # is fully idempotent (INSERT OR IGNORE, UPDATE only NULLs) so it can run
    # on every startup and heal databases that were never backfilled.
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='teacher_departments'"
    ).fetchone():
        # /     /     >---- (أ) القسم الأساسي للأستاذ
        conn.execute(
            'INSERT OR IGNORE INTO teacher_departments (teacher_id, department_id) '
            'SELECT id, department_id FROM teachers '
            'WHERE department_id IS NOT NULL AND deleted_at IS NULL'
        )
        # /     /     >---- (ب) الأقسام المستنتجة من السجل التدريسي
        if 'teacher_taught_courses' in {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }:
            conn.execute(
                'INSERT OR IGNORE INTO teacher_departments (teacher_id, department_id) '
                'SELECT DISTINCT teacher_id, department_id FROM teacher_taught_courses '
                'WHERE department_id IS NOT NULL AND teacher_id IS NOT NULL'
            )
        # /     /     >---- (ب) الأقسام من حصص الجدول الفعّال
        if 'timetable' in {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }:
            conn.execute(
                'INSERT OR IGNORE INTO teacher_departments (teacher_id, department_id) '
                'SELECT DISTINCT t.teacher_id, t.department_id '
                'FROM timetable t '
                'WHERE t.teacher_id IS NOT NULL AND t.department_id IS NOT NULL '
                'AND t.deleted_at IS NULL '
                'AND (t.version_id IS NULL OR t.version_id IN '
                '(SELECT id FROM timetable_versions WHERE status = \'active\'))'
            )
        # /     /     >---- (ج) رؤساء الأقسام دائماً ضمن قسمهم
        conn.execute(
            'INSERT OR IGNORE INTO teacher_departments (teacher_id, department_id) '
            'SELECT id, hod_department_id FROM teachers '
            'WHERE hod_department_id IS NOT NULL AND deleted_at IS NULL'
        )
        # /     /     >---- نزامن القسم الأساسي الناقص لأي أستاذ
        conn.execute(
            'UPDATE teachers SET department_id = COALESCE(hod_department_id, ('
            'SELECT MIN(department_id) FROM teacher_departments td '
            'WHERE td.teacher_id = teachers.id)) '
            'WHERE department_id IS NULL AND deleted_at IS NULL'
        )
        # /     /     >---- نزامن users.department_id من قسم الأستاذ المرتبط
        conn.execute(
            'UPDATE users SET department_id = ('
            'SELECT t.department_id FROM teachers t '
            'WHERE t.user_id = users.id AND t.deleted_at IS NULL '
            'ORDER BY (t.department_id IS NULL), t.id LIMIT 1) '
            'WHERE users.department_id IS NULL AND EXISTS ('
            'SELECT 1 FROM teachers t '
            'WHERE t.user_id = users.id AND t.department_id IS NOT NULL '
            'AND t.deleted_at IS NULL)'
        )
        conn.commit()

    # ── Course Plans (removed feature — drop legacy tables) ───────────
    conn.execute('DROP TABLE IF EXISTS course_plan_weeks')
    conn.execute('DROP TABLE IF EXISTS course_plans')

    # ── Course content submissions: course link + PDF file columns ────
    _cc_cols = _get_column_names(conn, 'course_content_submissions')
    if _cc_cols:
        if 'course_id' not in _cc_cols:
            _safe_add_column(
                conn, 'course_content_submissions', 'course_id',
                'INTEGER REFERENCES courses(id) ON DELETE SET NULL',
            )
        if 'filename' not in _cc_cols:
            _safe_add_column(conn, 'course_content_submissions', 'filename', 'TEXT DEFAULT ""')
        if 'original_filename' not in _cc_cols:
            _safe_add_column(conn, 'course_content_submissions', 'original_filename', 'TEXT DEFAULT ""')
        if 'file_size' not in _cc_cols:
            _safe_add_column(conn, 'course_content_submissions', 'file_size', 'INTEGER DEFAULT 0')
        # /     /     >---- أعمدة الترجمة الإنجليزية التلقائية
        for _cc_en_col, _cc_en_ddl in [
            ('course_name_en', 'TEXT DEFAULT ""'),
            ('course_objective_en', 'TEXT DEFAULT ""'),
            ('prerequisites_en', 'TEXT DEFAULT ""'),
            ('textbooks_en', 'TEXT DEFAULT ""'),
            ('notes_en', 'TEXT DEFAULT ""'),
            ('practical_content', 'TEXT DEFAULT ""'),
            ('practical_content_en', 'TEXT DEFAULT ""'),
            ('department_name_en', 'TEXT DEFAULT ""'),
            ('study_type_en', 'TEXT DEFAULT ""'),
            ('translated_at', 'TIMESTAMP'),
        ]:
            if _cc_en_col not in _cc_cols:
                _safe_add_column(conn, 'course_content_submissions', _cc_en_col, _cc_en_ddl)
        # /     /     >---- أعمدة الإصدارات النسخة (نسخ/نشر/أرشفة)
        for _cc_ver_col, _cc_ver_ddl in [
            ('version_label', 'TEXT DEFAULT ""'),
            ('parent_submission_id',
             'INTEGER REFERENCES course_content_submissions(id) ON DELETE SET NULL'),
            ('published_at', 'TIMESTAMP'),
            ('archived_at', 'TIMESTAMP'),
        ]:
            if _cc_ver_col not in _cc_cols:
                _safe_add_column(conn, 'course_content_submissions', _cc_ver_col, _cc_ver_ddl)
    _cc_curriculum_cols = _get_column_names(conn, 'course_content_curriculum')
    if _cc_curriculum_cols:
        if 'topic_en' not in _cc_curriculum_cols:
            _safe_add_column(conn, 'course_content_curriculum', 'topic_en', 'TEXT DEFAULT ""')
        if 'content_en' not in _cc_curriculum_cols:
            _safe_add_column(conn, 'course_content_curriculum', 'content_en', 'TEXT DEFAULT ""')
        if 'section' not in _cc_curriculum_cols:
            _safe_add_column(conn, 'course_content_curriculum', 'section', "TEXT DEFAULT 'theoretical'")
    if 'course_content_submissions' in existing_tables:
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_course_content_submissions_course '
            'ON course_content_submissions(course_id)'
        )

    # /     /     >---- تهيئة الإصدارات للبيانات القائمة (idempotent، لا يمسّ المحتوى)
    # /     /     >---- يُعدّ المنشور/المعتمد الحالي «الإصدار 1» ويُعبّئ published_at.
    _cc_ver_cols = _get_column_names(conn, 'course_content_submissions')
    if 'version_label' in _cc_ver_cols:
        conn.execute(
            """UPDATE course_content_submissions
               SET version_label = 'الإصدار 1'
               WHERE status IN ('published', 'approved')
                 AND (version_label IS NULL OR version_label = '')"""
        )
    if 'published_at' in _cc_ver_cols:
        conn.execute(
            """UPDATE course_content_submissions
               SET published_at = COALESCE(published_at, updated_at)
               WHERE status IN ('published', 'approved') AND published_at IS NULL"""
        )

    # ── Course vocabulary (R&D upload, course-level) ─────────────────
    if 'course_vocabulary' not in existing_tables:
        conn.execute("""
            CREATE TABLE course_vocabulary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL UNIQUE REFERENCES courses(id) ON DELETE CASCADE,
                filename TEXT NOT NULL DEFAULT '',
                original_filename TEXT NOT NULL DEFAULT '',
                file_size INTEGER DEFAULT 0,
                uploaded_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    # ── Teacher course files (syllabus PDF, immediate publish) ───────
    if 'teacher_course_files' not in existing_tables:
        conn.execute("""
            CREATE TABLE teacher_course_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
                course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                filename TEXT NOT NULL DEFAULT '',
                original_filename TEXT NOT NULL DEFAULT '',
                file_size INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(teacher_id, course_id)
            )
        """)


    # ── Course-owned file store (course_files) + backfill ─────────────
    _migrate_course_files(conn)

    # ── Course-content transition audit log ─────────────────────────
    _ensure_course_content_transitions(conn)

    # ── Academic periods (الفصل الدراسي) for course content ──────────
    _migrate_academic_periods(conn)

    # ── Faculty Performance Evaluation (كشف العبء التدريسي) ─────────
    _ensure_faculty_performance_tables(conn, existing_tables)

    # ── Canonical room types (قاعات + معملان فقط) ────────────────────
    _migrate_canonical_room_types(conn)

    # ── Enrich teacher_taught_courses with schedule details ─────────
    _migrate_teacher_taught_courses(conn)

    # ── Enforce a single active timetable version per dept + semester ──
    _migrate_single_active_timetable_version(conn)

    # ── Persist the logical domain registry (Identity/Academic/Scheduling/... ) ──
    sync_domain_registry(conn)

    conn.commit()