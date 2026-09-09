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
import sqlite3

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


def _get_column_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    try:
        rows = conn.execute(f'PRAGMA table_info({table_name})').fetchall()
    except sqlite3.OperationalError:
        return set()
    return {row[1] for row in rows}


def _safe_add_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    try:
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}')
    except sqlite3.OperationalError:
        pass


def _ensure_periods_table(conn: sqlite3.Connection) -> None:
    try:
        rows = conn.execute('SELECT code, label FROM period_settings').fetchall()
    except sqlite3.OperationalError:
        return
    existing_codes = {row[0] for row in rows}

    for code, label, start_time, end_time, is_enabled, sort_order in DEFAULT_PERIODS:
        if code not in existing_codes:
            conn.execute(
                """
                INSERT INTO period_settings (code, label, start_time, end_time, is_enabled, sort_order)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (code, label, start_time, end_time, is_enabled, sort_order),
            )


def _ensure_lookup_tables(conn: sqlite3.Connection) -> None:
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

    # Seed rank_rules from qual/rank names
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

    # Specializations: academic field per (primary) department. A member may
    # hold several linked departments, but a specialization always belongs to
    # exactly one department, and is selected only after the primary one.
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


def _rename_lookup_value(conn: sqlite3.Connection, table: str, name_col: str,
                         teacher_fk_col: str, teacher_text_col: str,
                         old_name: str, new_name: str, links=()) -> None:
    """Rename a lookup value in place (keeps its id) or merge it into an
    existing target row.

    Teacher FK/text columns and lookup junction rows (e.g. ``rank_rules``)
    are updated so every reference keeps working after the rename.
    """
    old = conn.execute(
        f'SELECT id FROM "{table}" WHERE "{name_col}" = ? LIMIT 1', (old_name,)
    ).fetchone()
    if not old:
        return
    old_id = old[0]
    target = conn.execute(
        f'SELECT id FROM "{table}" WHERE "{name_col}" = ? LIMIT 1', (new_name,)
    ).fetchone()
    if target:
        new_id = target[0]
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
        conn.execute(
            f'UPDATE "{table}" SET "{name_col}" = ? WHERE id = ?', (new_name, old_id)
        )
    # Keep the denormalised teacher text column in sync either way.
    conn.execute(
        f'UPDATE teachers SET "{teacher_text_col}" = ? WHERE "{teacher_text_col}" = ?',
        (new_name, old_name),
    )


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

    if 'qualifications' in tables:
        _rename_lookup_value(conn, 'qualifications', 'name_ar',
                             'qualification_id', 'qualification',
                             'دبلوم', 'دبلوم عالي', links=qual_links)
    if 'academic_ranks' in tables:
        _rename_lookup_value(conn, 'academic_ranks', 'name_ar',
                             'rank_id', 'academic_rank',
                             'محاضر مساعد', 'مساعد محاضر', links=rank_links)
        _rename_lookup_value(conn, 'academic_ranks', 'name_ar',
                             'rank_id', 'academic_rank',
                             'أستاذ متعاون', 'معيد', links=rank_links)
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
        # Collapse any duplicates the merges above may have created.
        conn.execute('''
            DELETE FROM rank_rules WHERE id NOT IN (
                SELECT MIN(id) FROM rank_rules
                GROUP BY qualification_id, rank_id
            )
        ''')
    conn.commit()


def _backfill_room_fks(conn: sqlite3.Connection) -> None:
    for col, fk_table, src_col in [
        ('room_type_id', 'room_types', 'type'),
        ('status_id', 'room_statuses', 'status'),
        ('floor_id', 'floors', 'location'),
    ]:
        existing_cols = _get_column_names(conn, 'rooms')
        if col not in existing_cols:
            _safe_add_column(conn, 'rooms', col, f'INTEGER REFERENCES "{fk_table}"(id) ON DELETE SET NULL')
        conn.execute(f'''
            UPDATE rooms SET {col} = (
                SELECT id FROM "{fk_table}" WHERE name_ar = rooms."{src_col}" LIMIT 1
            ) WHERE {col} IS NULL
        ''')


def _backfill_teacher_fks(conn: sqlite3.Connection) -> None:
    for col, fk_table, src_col in [
        ('qualification_id', 'qualifications', 'qualification'),
        ('rank_id', 'academic_ranks', 'academic_rank'),
        ('classification_id', 'classifications', 'classification'),
    ]:
        existing_cols = _get_column_names(conn, 'teachers')
        if col not in existing_cols:
            _safe_add_column(conn, 'teachers', col, f'INTEGER REFERENCES "{fk_table}"(id) ON DELETE SET NULL')
        conn.execute(f'''
            UPDATE teachers SET {col} = (
                SELECT id FROM "{fk_table}" WHERE name_ar = teachers."{src_col}" LIMIT 1
            ) WHERE {col} IS NULL
        ''')


def _ensure_runtime_indexes(conn: sqlite3.Connection) -> None:
    conn.execute('CREATE INDEX IF NOT EXISTS idx_teachers_department ON teachers(department)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_courses_department_year ON courses(department, year)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_courses_code ON courses(code)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_timetable_day_semester ON timetable(day, semester)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_timetable_course_id ON timetable(course_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_timetable_teacher_id ON timetable(teacher_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_timetable_room_id ON timetable(room_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_timetable_created_at ON timetable(created_at DESC)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_course_prerequisites_course ON course_prerequisites(course_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_course_prerequisites_prereq ON course_prerequisites(prerequisite_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_teachers_user_id ON teachers(user_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_users_department_id ON users(department_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_exam_schedule_department_id ON exam_schedule(department_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_exam_schedule_exam_date ON exam_schedule(exam_date)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_exam_schedule_course_id ON exam_schedule(course_id)')


def _migrate_department_fks(conn: sqlite3.Connection) -> None:
    """Recreate tables whose department_id FK is not ON DELETE SET NULL.

    Builds CREATE TABLE SQL programmatically from PRAGMA table_info and
    PRAGMA foreign_key_list instead of manipulating raw SQL text with regex.
    Discovers foreign keys referencing departments(id) dynamically.
    """
    tables_to_migrate = []
    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        table = row[0]
        for fk in conn.execute(f'PRAGMA foreign_key_list("{table}")'):
            if fk["table"] == "departments" and fk["on_delete"] != "SET NULL":
                tables_to_migrate.append(table)
                break

    if not tables_to_migrate:
        return 0

    conn.execute("PRAGMA foreign_keys = OFF")
    migrated = 0

    for table in tables_to_migrate:
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

        fk_groups = {}
        for fk in fk_rows:
            fk_groups.setdefault(fk['id'], []).append(fk)

        fk_defs = []
        for fk_id, fk_parts in fk_groups.items():
            from_cols = ', '.join(f'"{p["from"]}"' for p in fk_parts)
            to_table = fk_parts[0]['table']
            to_cols = ', '.join(f'"{p["to"]}"' for p in fk_parts)
            on_delete = fk_parts[0]['on_delete']

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

        all_defs = col_defs + fk_defs + unique_multi
        temp = f"_migrate_{table}"
        conn.execute(f'DROP TABLE IF EXISTS "{temp}"')
        conn.execute(f'CREATE TABLE "{temp}" ({", ".join(all_defs)})')

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

        fks_after = conn.execute(f'PRAGMA foreign_key_list("{temp}")').fetchall()
        dept_fk = next((fk for fk in fks_after if fk["table"] == "departments"), None)
        if not dept_fk or dept_fk["on_delete"] != "SET NULL":
            conn.execute(f'DROP TABLE "{temp}"')
            conn.execute("PRAGMA foreign_keys = ON")
            raise RuntimeError(f"FK verification failed for table \"{table}\"")

        conn.execute(f'DROP TABLE "{table}"')
        conn.execute(f'ALTER TABLE "{temp}" RENAME TO "{table}"')

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


def _computed_academic_year() -> str:
    from datetime import date

    today = date.today()
    if today.month >= 9:
        return f'{today.year}-{today.year + 1}'
    return f'{today.year - 1}-{today.year}'


def _current_academic_year(conn: sqlite3.Connection, dept_id: int, semester: int) -> str:
    """Best-known current academic year for a department + semester."""
    try:
        row = conn.execute(
            'SELECT academic_year FROM semesters '
            'WHERE department_id = ? AND semester_number = ? AND is_active = 1 '
            'AND academic_year IS NOT NULL AND academic_year != "" LIMIT 1',
            (dept_id, semester),
        ).fetchone()
        if row and row['academic_year']:
            return row['academic_year']
    except sqlite3.OperationalError:
        pass
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
    return _computed_academic_year()


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

    if semester_number % 2 == 1:
        return f'fall_{end_year}'
    return f'spring_{start_year}'


def _migrate_single_active_timetable_version(conn: sqlite3.Connection) -> None:
    """Repair duplicated active timetable versions.

    Only one version may be active per department + semester. If legacy data
    left several rows marked 'active', keep the newest one active and archive
    the rest so the timetable page and the archive buttons behave predictably.
    """
    groups = conn.execute(
        'SELECT department_id, semester '
        'FROM timetable_versions '
        'WHERE status = \'active\' '
        'GROUP BY department_id, semester '
        'HAVING COUNT(*) > 1'
    ).fetchall()
    for group in groups:
        rows = conn.execute(
            'SELECT id FROM timetable_versions '
            'WHERE department_id = ? AND semester = ? AND status = \'active\' '
            'ORDER BY id DESC',
            (group['department_id'], group['semester']),
        ).fetchall()
        if not rows:
            continue
        keep_id = rows[0]['id']
        conn.execute(
            'UPDATE timetable_versions SET status = \'archived\' '
            'WHERE department_id = ? AND semester = ? AND status = \'active\' AND id != ?',
            (group['department_id'], group['semester'], keep_id),
        )


def _migrate_to_named_semesters(conn: sqlite3.Connection) -> None:
    """Migrate from academic_year (TEXT '2025-2026') to semester_code (TEXT 'fall_2026').

    1. Rebuild the semesters table with the new global structure.
    2. Add semester_code to timetable_versions and convert existing data.
    3. Seed the initial named semesters.

    Guarded by the migration log: it DROPs and rebuilds the ``semesters``
    table, so it must run exactly once, not on every startup (running it
    repeatedly wiped admin-added semesters and orphaned references).
    """
    _NAMED_SEMESTERS_MIGRATION = 'migrate_to_named_semesters_v1'
    if _migration_done(conn, _NAMED_SEMESTERS_MIGRATION):
        return

    from werkzeug.security import generate_password_hash

    # ── 1. Rebuild the semesters table ──────────────────────────────────
    # The old table was per-department (department_id, semester_number).
    # The new table is global: (season, year) → unique code.
    conn.execute('PRAGMA foreign_keys = OFF')
    try:
        conn.execute('DROP TABLE IF EXISTS semesters')
        conn.execute("""
            CREATE TABLE semesters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                season TEXT NOT NULL,
                year INTEGER NOT NULL,
                name_ar TEXT NOT NULL,
                name_en TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 0,
                start_date TEXT DEFAULT '',
                end_date TEXT DEFAULT '',
                exam_start_date TEXT DEFAULT '',
                exam_end_date TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                deleted_at TIMESTAMP,
                UNIQUE(season, year)
            )
        """)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_semesters_code ON semesters(code)')
    finally:
        conn.execute('PRAGMA foreign_keys = ON')

    # ── 2. Seed initial named semesters ─────────────────────────────────
    now_year = __import__('datetime').date.today().year
    seed_semesters = []
    for y in range(now_year - 1, now_year + 2):
        seed_semesters.extend([
            ('fall', y, f'خريف {y}', f'Fall {y}'),
            ('spring', y, f'ربيع {y}', f'Spring {y}'),
        ])
    for season, year, name_ar, name_en in seed_semesters:
        code = f'{season}_{year}'
        if season == 'fall':
            start_date = f'{year}-09-01'
            end_date = f'{year + 1}-01-31'
            exam_start = f'{year + 1}-01-10'
            exam_end = f'{year + 1}-01-25'
        else:
            start_date = f'{year}-02-15'
            end_date = f'{year}-06-30'
            exam_start = f'{year}-06-01'
            exam_end = f'{year}-06-20'
        conn.execute(
            'INSERT OR IGNORE INTO semesters '
            '(code, season, year, name_ar, name_en, start_date, end_date, exam_start_date, exam_end_date) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (code, season, year, name_ar, name_en, start_date, end_date, exam_start, exam_end),
        )

    # Mark the current semester as active
    current_code = _computed_semester_code()
    conn.execute('UPDATE semesters SET is_active = 0')
    conn.execute('UPDATE semesters SET is_active = 1 WHERE code = ?', (current_code,))

    # ── 3. Add semester_code to timetable_versions ──────────────────────
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

        # Recreate the table with correct constraints
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

            # Re-insert rows
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


def _current_semester_code(conn: sqlite3.Connection) -> str:
    """Return the currently active named semester code."""
    row = conn.execute(
        'SELECT code FROM semesters WHERE is_active = 1 LIMIT 1'
    ).fetchone()
    if row and row['code']:
        return row['code']
    return _computed_semester_code()


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


def _migrate_user_roles(conn: sqlite3.Connection) -> None:
    """Introduce the multi-role model: the ``user_roles`` join table.

    One person (a single ``users`` row) may hold several system roles at once
    (e.g. both ``teacher`` and ``head_of_department``).  ``users.role`` remains
    the person's *default landing role*; ``user_roles`` is the full set of
    roles the person holds.  ``users.is_active`` allows a soft-disable
    (deactivated users cannot log in) while keeping their data.

    Idempotent — safe to run on every startup.
    """
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

    # Backfill: every user's current landing role is the minimum set.
    conn.execute(
        """INSERT OR IGNORE INTO user_roles (user_id, role)
           SELECT id, role FROM users"""
    )

    # A user linked to a teachers row is also a faculty member → teacher role.
    conn.execute(
        """INSERT OR IGNORE INTO user_roles (user_id, role)
           SELECT t.user_id, 'teacher' FROM teachers t
           WHERE t.user_id IS NOT NULL"""
    )

    # Archived teacher users cannot log in anymore (soft-disable).
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


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        rows = conn.execute(f'PRAGMA table_info({table})').fetchall()
    except sqlite3.OperationalError:
        return False
    return any(row[1] == column for row in rows)


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

    temp = '_migrate_course_content_teacher_nullable'
    fk_was_on = conn.execute('PRAGMA foreign_keys').fetchone()[0]
    conn.execute('PRAGMA foreign_keys = OFF')
    try:
        conn.execute(f'DROP TABLE IF EXISTS "{temp}"')
        conn.execute(f'CREATE TABLE "{temp}" ({", ".join(col_defs + fk_defs + unique_multi)})')
        conn.execute(f'INSERT INTO "{temp}" SELECT * FROM "course_content_submissions"')
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


def _migrate_course_files(conn: sqlite3.Connection) -> None:
    """Create the course-owned ``course_files`` store and backfill it.

    The course owns every file; the uploader (teacher/R&D) is metadata
    only.  Legacy per-uploader tables (``teacher_course_files``,
    ``course_vocabulary``) and the file columns on
    ``course_content_submissions`` / ``courses`` are dropped by
    ``_drop_legacy_course_file_tables`` once every reader/writer reads
    only ``course_files``.
    """
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

    if 'course_content_submissions' in {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }:
        cols = _get_column_names(conn, 'course_content_submissions')
        if 'course_file_id' not in cols:
            _safe_add_column(conn, 'course_content_submissions', 'course_file_id',
                             'INTEGER REFERENCES course_files(id) ON DELETE SET NULL')

    # Backfill only once (guard: no rows yet) so restarts stay idempotent.
    if conn.execute('SELECT COUNT(*) FROM course_files').fetchone()[0] == 0:
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


def _migrate_academic_periods(conn: sqlite3.Connection) -> None:
    """Academic-period dimension (الفصل الدراسي) for course content.

    Content belongs to ``course + period`` — never to a bare filename.
    Legacy rows keep ``academic_period_id = NULL`` and surface under
    «بدون فصل دراسي محدد» in the archive.  Surrounding years are seeded
    so the picker always has sensible options.
    """
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

    current_year = datetime.date.today().year
    for year in range(current_year - 2, current_year + 2):
        for term in ('خريف', 'ربيع'):
            conn.execute(
                'INSERT OR IGNORE INTO academic_periods (year, term, label) '
                'VALUES (?, ?, ?)',
                (year, term, f'{term} {year}'),
            )

    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()}
    if 'course_content_submissions' in tables:
        _safe_add_column(conn, 'course_content_submissions', 'academic_period_id',
                         'INTEGER REFERENCES academic_periods(id) ON DELETE SET NULL')
    if 'course_files' in tables:
        _safe_add_column(conn, 'course_files', 'academic_period_id',
                         'INTEGER REFERENCES academic_periods(id) ON DELETE SET NULL')
    # الأرشيف يحفظ الفصل الدراسي الذي كانت تنتمي إليه النسخة
    if 'syllabus_archive' in tables:
        _safe_add_column(conn, 'syllabus_archive', 'academic_period_id', 'INTEGER')
    if 'course_form_archive' in tables:
        _safe_add_column(conn, 'course_form_archive', 'academic_period_id', 'INTEGER')


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


def _migration_done(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        'SELECT 1 FROM _migration_log WHERE migration_name = ?', (name,)
    ).fetchone()
    return row is not None


def _mark_migration_done(conn: sqlite3.Connection, name: str) -> None:
    conn.execute(
        'INSERT OR IGNORE INTO _migration_log (migration_name) VALUES (?)', (name,)
    )
    conn.commit()


def _cleanup_legacy_user_data(conn: sqlite3.Connection) -> None:
    """One-time cleanup of legacy user/role data.

    This replaces the old _drop_student_schema role mutations and
    _migrate_role_model department wiping that used to run on every startup.
    Now runs exactly once via the _migration_log guard.
    """
    if _migration_done(conn, _CLEANUP_MIGRATION_NAME):
        return

    from werkzeug.security import generate_password_hash

    # 1. Role remapping: sub_admin -> support_admin -> super_admin
    conn.execute("UPDATE users SET role = 'support_admin' WHERE role = 'sub_admin'")
    conn.execute("UPDATE users SET role = 'super_admin' WHERE role = 'support_admin'")

    # 2. Remove leftover student users and unlink teacher FKs
    conn.execute(
        'UPDATE teachers SET user_id = NULL '
        "WHERE user_id IN (SELECT id FROM users WHERE role = 'student')"
    )
    conn.execute("DELETE FROM users WHERE role = 'student'")

    # 3. Administrative roles should not carry an academic department
    conn.execute(
        "UPDATE users SET department_id = NULL "
        "WHERE role IN ('super_admin', 'faculty_affairs', 'research_development', 'exam')"
    )

    # 4. Deduplicate HODs: keep the earliest per department, demote the rest
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

    # 5. Fix teacher user_id: sever links pointing at accounts that are
    # neither a teacher nor a head of department.  teachers.user_id is the
    # canonical user→teacher link, so HOD accounts (who are teachers, too) must
    # keep it — they are how authenticate() resolves hod_department_id.
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

    # 6. Fix superadmin: ensure exactly one super_admin exists
    sa = conn.execute(
        "SELECT id FROM users WHERE role = 'super_admin'"
    ).fetchone()
    if sa:
        conn.execute(
            "UPDATE users SET username = 'superadmin' WHERE id = ?",
            (sa['id'],)
        )
    else:
        admin_pw = os.environ.get('ADMIN_PASSWORD', 'admin123')
        conn.execute(
            "INSERT INTO users (username, password, role, label) VALUES (?, ?, ?, ?)",
            ('superadmin', generate_password_hash(admin_pw), 'super_admin', 'مدير النظام')
        )

    # 7. Rename legacy teacher.* usernames to Arabic teacher names
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

    # 8. Cleanup test accounts and orphaned test records
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
    'teacher_materials', 'teacher_requests', 'classroom_change_requests',
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


def _deduplicate_teachers_v1(conn: sqlite3.Connection) -> None:
    """One-time migration: merge approved teacher duplicates.

    Reads approved merges from scripts/approved_teacher_merges.json.
    Only processes groups explicitly listed in the JSON — never auto-detects.
    Each group runs inside a single transaction for atomicity.
    """
    if _migration_done(conn, _DEDUP_MIGRATION_NAME):
        return

    import json as _json
    import os

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

    # Create audit table
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
        if not group.get('approved', False):
            continue

        canonical_id = group['canonical_teacher_id']
        duplicate_ids = group.get('duplicate_teacher_ids', [])
        matched_by = group.get('matched_by', 'unknown')

        if not duplicate_ids:
            continue

        # Validate canonical exists
        canon = conn.execute(
            'SELECT id, name, email, academic_number, user_id FROM teachers WHERE id = ?',
            (canonical_id,),
        ).fetchone()
        if not canon:
            continue

        # Validate all duplicates exist
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

                # Snapshot to audit
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

                        # Try to move all rows by updating teacher_id
                        conn.execute(
                            f'UPDATE {table} SET teacher_id = ? WHERE teacher_id = ?',
                            (canonical_id, dup_id),
                        )

                        # Check if any rows still point to the duplicate
                        # (UNIQUE constraint prevented the UPDATE from some rows)
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

                # Update audit with FK count
                conn.execute(
                    'UPDATE teacher_dedup_audit SET fk_refs_migrated = ? '
                    'WHERE canonical_teacher_id = ? AND duplicate_teacher_id = ?',
                    (fk_count, canonical_id, dup_id),
                )

                # Merge fields: fill NULLs on canonical from duplicate
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

                # Update audit with merged fields
                conn.execute(
                    'UPDATE teacher_dedup_audit SET fields_merged = ? '
                    'WHERE canonical_teacher_id = ? AND duplicate_teacher_id = ?',
                    (_json.dumps(merged_fields), canonical_id, dup_id),
                )

                # Delete the duplicate teacher row
                conn.execute('DELETE FROM teachers WHERE id = ?', (dup_id,))
                total_migrated += 1

            conn.execute('RELEASE sp_dedup')

        except Exception:
            conn.execute('ROLLBACK TO sp_dedup')
            continue

    conn.commit()
    if total_migrated > 0:
        _mark_migration_done(conn, _DEDUP_MIGRATION_NAME)


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

    conn.execute('''
        UPDATE teachers SET academic_number = NULL
        WHERE academic_number IN ('', '0', 'غير محدد', '—', '-', 'N/A', 'null')
           OR TRIM(academic_number) = ''
    ''')

    conn.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS uq_teachers_academic_number
        ON teachers(academic_number)
        WHERE academic_number IS NOT NULL
    ''')
    conn.commit()


def _ensure_faculty_performance_tables(conn: sqlite3.Connection, existing_tables: set) -> None:
    """Create tables for the faculty performance evaluation (كشف العبء التدريسي)."""

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
    ]
    for name, hours, order in types:
        conn.execute(
            'INSERT INTO admin_assignment_types (name, default_hours, is_active, sort_order) VALUES (?, ?, 1, ?)',
            (name, hours, order),
        )


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


def _migrate_academic_calendar(conn: sqlite3.Connection) -> None:
    """Enrich ``semesters`` with start/end and exam date boundaries.

    Makes the semesters table the single source of truth for:
    - semester start/end dates (used by timetable, archive, printing)
    - exam period boundaries per semester (used by exams)

    Idempotent: safe to run on every startup.
    """
    try:
        sem_cols = _get_column_names(conn, 'semesters')
    except Exception:
        return

    # Add columns if missing
    for col, ddl in [
        ('start_date', "TEXT DEFAULT ''"),
        ('end_date', "TEXT DEFAULT ''"),
        ('exam_start_date', "TEXT DEFAULT ''"),
        ('exam_end_date', "TEXT DEFAULT ''"),
    ]:
        if col not in sem_cols:
            _safe_add_column(conn, 'semesters', col, ddl)

    # Seed default dates for rows that have empty start_date
    rows = conn.execute(
        'SELECT id, season, year, start_date FROM semesters WHERE deleted_at IS NULL'
    ).fetchall()
    for row in rows:
        if row['start_date']:
            continue
        season = row['season']
        year = row['year']
        if season == 'fall':
            start = f'{year}-09-01'
            end = f'{year + 1}-01-31'
            exam_start = f'{year + 1}-01-10'
            exam_end = f'{year + 1}-01-25'
        else:
            start = f'{year}-02-15'
            end = f'{year}-06-30'
            exam_start = f'{year}-06-01'
            exam_end = f'{year}-06-20'
        conn.execute(
            'UPDATE semesters SET start_date = ?, end_date = ?, '
            'exam_start_date = ?, exam_end_date = ? WHERE id = ?',
            (start, end, exam_start, exam_end, row['id']),
        )

    # Copy exam_settings dates into active semester if its exam dates are empty
    try:
        active = conn.execute(
            'SELECT id, exam_start_date FROM semesters WHERE is_active = 1 LIMIT 1'
        ).fetchone()
        if active and not active['exam_start_date']:
            settings = conn.execute('SELECT exam_start_date, exam_end_date FROM exam_settings LIMIT 1').fetchone()
            if settings and settings['exam_start_date']:
                conn.execute(
                    'UPDATE semesters SET exam_start_date = ?, exam_end_date = ? WHERE id = ?',
                    (settings['exam_start_date'], settings['exam_end_date'], active['id']),
                )
    except sqlite3.OperationalError:
        pass

    conn.commit()


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

    # Columns are added unconditionally — _safe_add_column is idempotent.
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
    if _migration_done(conn, 'enrich_teacher_taught_courses'):
        return

    conn.execute('PRAGMA foreign_keys = OFF')
    try:
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

            conn.execute("""
                
            """)

        old_indexes = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'index' "
            "AND tbl_name = 'teacher_taught_courses'"
        ).fetchall()
        for idx_name, _ in old_indexes:
            try:
                conn.execute(f'DROP INDEX IF EXISTS "{idx_name}"')
            except Exception:
                pass

        old_rows = conn.execute('SELECT * FROM teacher_taught_courses').fetchall()
        old_cols = [d[1] for d in conn.execute(
            'PRAGMA table_info(teacher_taught_courses)'
        ).fetchall()]

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
                archived INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(teacher_id, course_id, department_id, semester, semester_code, day, period, student_section)
            )
        """)

        for row in old_rows:
            row_dict = dict(zip(old_cols, row))
            conn.execute(
                'INSERT INTO teacher_taught_courses '
                '(id, teacher_id, course_id, department_id, semester, semester_code, version_id, '
                ' day, start_time, end_time, period, room_id, student_section, lecture_type, '
                ' hours, timetable_entry_id, archived, created_at) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
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
                    row_dict.get('archived', 0),
                    row_dict.get('created_at', ''),
                ),
            )
    finally:
        conn.execute('PRAGMA foreign_keys = ON')

    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_ttc_teacher_semester '
        'ON teacher_taught_courses (teacher_id, semester_code)'
    )
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_ttc_entry '
        'ON teacher_taught_courses (timetable_entry_id)'
    )
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_ttc_archived '
        'ON teacher_taught_courses (archived)'
    )

    _mark_migration_done(conn, 'enrich_teacher_taught_courses')
    conn.commit()


def ensure_schema(conn: sqlite3.Connection) -> None:
    _ensure_migration_log(conn)
    _cleanup_legacy_user_data(conn)
    _deduplicate_teachers_v1(conn)
    _verify_teacher_fk_integrity(conn)
    _ensure_academic_number_index(conn)

    _migrate_course_content_teacher_nullable(conn)
    existing_tables = {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    _drop_student_schema(conn)
    existing_tables = {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    # Soft-delete columns on the standard archiveable tables.
    from database.constants import SOFT_DELETE_TABLES
    for table in SOFT_DELETE_TABLES:
        if table in existing_tables:
            cols = _get_column_names(conn, table)
            if 'deleted_at' not in cols:
                _safe_add_column(conn, table, 'deleted_at', 'TIMESTAMP')

    # department_majors — created on older databases that predate the column.
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

    if 'teacher_departments' not in existing_tables:
        conn.execute("""
            CREATE TABLE teacher_departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
                department_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
                UNIQUE(teacher_id, department_id)
            )
        """)
        conn.execute("""
            INSERT OR IGNORE INTO teacher_departments (teacher_id, department_id)
            SELECT id, department_id FROM teachers
            WHERE department_id IS NOT NULL
        """)
        conn.commit()

    # Auto-recorded taught courses: one row per (teacher, course, department,
    # semester level, semester term) captured whenever a timetable entry that
    # assigns the course to the teacher is saved.
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
                archived INTEGER NOT NULL DEFAULT 0,
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
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ttc_archived
            ON teacher_taught_courses (archived)
        """)
        # Backfill from every saved timetable entry (archived versions keep
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

    # Migration: update existing courses with appropriate icons
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

    if 'users' in existing_tables:
        user_columns = _get_column_names(conn, 'users')
        if 'department_id' not in user_columns:
            _safe_add_column(conn, 'users', 'department_id', 'INTEGER REFERENCES departments(id) ON DELETE SET NULL')
        if 'email' not in user_columns:
            _safe_add_column(conn, 'users', 'email', 'TEXT')
        if 'password_changed_at' not in user_columns:
            _safe_add_column(conn, 'users', 'password_changed_at', 'TIMESTAMP')
        if 'phone' not in user_columns:
            _safe_add_column(conn, 'users', 'phone', 'TEXT')
        if 'theme' not in user_columns:
            _safe_add_column(conn, 'users', 'theme', "TEXT DEFAULT 'light'")
        if 'administrative_department_id' not in user_columns:
            _safe_add_column(conn, 'users', 'administrative_department_id',
                             'INTEGER REFERENCES departments(id) ON DELETE SET NULL')
            # Backfill: for administrative roles, move department_id → administrative_department_id
            # and clear department_id (which should be academic only)
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
        _migrate_role_model(conn)
        _migrate_user_roles(conn)

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

    if 'history' in existing_tables:
        history_columns = _get_column_names(conn, 'history')
        if 'actor_user_id' not in history_columns:
            _safe_add_column(conn, 'history', 'actor_user_id', 'INTEGER')
        if 'actor_username' not in history_columns:
            _safe_add_column(conn, 'history', 'actor_username', 'TEXT')
        if 'message' not in history_columns:
            _safe_add_column(conn, 'history', 'message', 'TEXT')

    _ensure_periods_table(conn)

    # Lock القسم العام to 1 semester only; clamp others to max 7
    if 'departments' in existing_tables:
        conn.execute("UPDATE departments SET semesters = 1 WHERE name = 'القسم العام'")
        conn.execute("UPDATE departments SET semesters = 7 WHERE name != 'القسم العام' AND semesters > 7")

    # Add hidden, has_sections, and type columns to departments if missing
    if 'departments' in existing_tables:
        dept_columns = _get_column_names(conn, 'departments')
        if 'hidden' not in dept_columns:
            _safe_add_column(conn, 'departments', 'hidden', 'INTEGER NOT NULL DEFAULT 0')
        if 'has_sections' not in dept_columns:
            _safe_add_column(conn, 'departments', 'has_sections', 'INTEGER NOT NULL DEFAULT 1')
        if 'type' not in dept_columns:
            _safe_add_column(conn, 'departments', 'type', "TEXT NOT NULL DEFAULT 'academic'")
            # Backfill: hidden=1 → 'administrative', hidden=0 → 'academic'
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

    # Department public profiles (about/vision/mission/etc.) — structured DB storage
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

    # Align lookup vocabulary with the current pickers (legacy renames)
    _migrate_lookup_vocabulary(conn)
    # Ensure new lookup tables exist + seed data
    _ensure_lookup_tables(conn)
    # Backfill FK columns on rooms / teachers from existing text values
    _backfill_room_fks(conn)
    _backfill_teacher_fks(conn)

    # Ensure timetable has department_id to enforce department isolation
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

    # Add signing columns to exam_schedule
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

    # Backfill day_ar from exam_date for legacy exam rows
    if 'exam_schedule' in existing_tables:
        conn.execute("""UPDATE exam_schedule SET day_ar = CASE CAST(strftime('%w', exam_date) AS INTEGER)
            WHEN 0 THEN 'الأحد' WHEN 1 THEN 'الاثنين' WHEN 2 THEN 'الثلاثاء'
            WHEN 3 THEN 'الأربعاء' WHEN 4 THEN 'الخميس'
            ELSE day_ar END
            WHERE exam_date != '' AND day_ar = ''""")

    _migrate_department_fks(conn)
    _ensure_runtime_indexes(conn)
    conn.execute('CREATE INDEX IF NOT EXISTS idx_history_created_at ON history(created_at DESC)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_faculty_attendance_teacher ON faculty_attendance(teacher_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_faculty_attendance_date ON faculty_attendance(date)')

    # ── Messaging / Objection System tables ──────────────────────────
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

    # Phase 2: teacher_materials table for file uploads with course/department tracking
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

    # Phase 2: notifications table
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

    # Phase 2: teacher_requests table for messages/objections/requests
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

    # Phase 2: department_announcements table
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

    # classroom_change_requests table for classroom change workflow
    if 'classroom_change_requests' not in existing_tables:
        conn.execute("""
            CREATE TABLE classroom_change_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
                schedule_id INTEGER NOT NULL REFERENCES timetable(id) ON DELETE CASCADE,
                current_classroom_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
                requested_classroom_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                hod_comment TEXT DEFAULT '',
                reviewed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                reviewed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_ccr_teacher ON classroom_change_requests(teacher_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_ccr_dept ON classroom_change_requests(department_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_ccr_status ON classroom_change_requests(status)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_ccr_timetable ON classroom_change_requests(schedule_id)')

    # exam_settings table for exam configuration
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
    # Migrate from academic_year (TEXT '2025-2026') to semester_code (TEXT 'fall_2026').
    # Rebuilds the semesters table with the new global structure and adds
    # semester_code to timetable_versions.
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

        # Backfill: assign legacy rows (no version yet) to a current version.
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
        # Backfill: legacy rows without a type default to 'theory'.
        # Idempotent — only touches NULL values, never existing ones.
        conn.execute(
            "UPDATE timetable SET lecture_type = 'theory' WHERE lecture_type IS NULL"
        )
        conn.commit()

    # ── Teacher ↔ department membership backfill ──────────────────────
    # A department applies to a teacher when ANY of these holds:
    #   (a) it is the teacher's primary department (teachers.department_id),
    #   (b) the teacher was chosen in a lecture-assignment stage (active
    #       timetable entries / non-archived teacher_taught_courses),
    #   (c) the teacher heads the department (teachers.hod_department_id).
    # teacher_departments is the many-to-many source of truth used by the HOD
    # member lists, _can_hod_view_teacher and the teacher profile.  This block
    # is fully idempotent (INSERT OR IGNORE, UPDATE only NULLs) so it can run
    # on every startup and heal databases that were never backfilled.
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='teacher_departments'"
    ).fetchone():
        # (a) primary department assignments (master list already on file).
        conn.execute(
            'INSERT OR IGNORE INTO teacher_departments (teacher_id, department_id) '
            'SELECT id, department_id FROM teachers '
            'WHERE department_id IS NOT NULL AND deleted_at IS NULL'
        )
        # (b) departments implied by recorded teaching assignments.
        conn.execute(
            'INSERT OR IGNORE INTO teacher_departments (teacher_id, department_id) '
            'SELECT DISTINCT teacher_id, department_id FROM teacher_taught_courses '
            'WHERE department_id IS NOT NULL AND archived = 0 AND teacher_id IS NOT NULL'
        )
        # (b) departments implied by active timetable entries (chosen during
        # lecture determination).  Needs timetable_versions — guaranteed to
        # exist by this point in ensure_schema.
        conn.execute(
            'INSERT OR IGNORE INTO teacher_departments (teacher_id, department_id) '
            'SELECT DISTINCT t.teacher_id, t.department_id '
            'FROM timetable t '
            'WHERE t.teacher_id IS NOT NULL AND t.department_id IS NOT NULL '
            'AND t.deleted_at IS NULL '
            'AND (t.version_id IS NULL OR t.version_id IN '
            '(SELECT id FROM timetable_versions WHERE status = \'active\'))'
        )
        # (c) heads of department always belong to the department they head.
        conn.execute(
            'INSERT OR IGNORE INTO teacher_departments (teacher_id, department_id) '
            'SELECT id, hod_department_id FROM teachers '
            'WHERE hod_department_id IS NOT NULL AND deleted_at IS NULL'
        )
        # Sync the derived primary teachers.department_id (smallest membership)
        # for every teacher still lacking one — mirrors _reconcile_primary_dept.
        # Head-of-department teachers keep the department they head.
        conn.execute(
            'UPDATE teachers SET department_id = COALESCE(hod_department_id, ('
            'SELECT MIN(department_id) FROM teacher_departments td '
            'WHERE td.teacher_id = teachers.id)) '
            'WHERE department_id IS NULL AND deleted_at IS NULL'
        )
        # Mirror users.department_id from the linked teacher's primary dept.
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
        # English auto-translation columns (generated when the sheet is sent).
        for _cc_en_col, _cc_en_ddl in [
            ('course_name_en', 'TEXT DEFAULT ""'),
            ('course_objective_en', 'TEXT DEFAULT ""'),
            ('prerequisites_en', 'TEXT DEFAULT ""'),
            ('textbooks_en', 'TEXT DEFAULT ""'),
            ('notes_en', 'TEXT DEFAULT ""'),
            ('department_name_en', 'TEXT DEFAULT ""'),
            ('study_type_en', 'TEXT DEFAULT ""'),
            ('translated_at', 'TIMESTAMP'),
        ]:
            if _cc_en_col not in _cc_cols:
                _safe_add_column(conn, 'course_content_submissions', _cc_en_col, _cc_en_ddl)
    _cc_curriculum_cols = _get_column_names(conn, 'course_content_curriculum')
    if _cc_curriculum_cols:
        if 'topic_en' not in _cc_curriculum_cols:
            _safe_add_column(conn, 'course_content_curriculum', 'topic_en', 'TEXT DEFAULT ""')
        if 'content_en' not in _cc_curriculum_cols:
            _safe_add_column(conn, 'course_content_curriculum', 'content_en', 'TEXT DEFAULT ""')
    if 'course_content_submissions' in existing_tables:
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_course_content_submissions_course '
            'ON course_content_submissions(course_id)'
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

    # ── Syllabus archive (منهج) — old versions kept on replacement ───
    if 'syllabus_archive' not in existing_tables:
        conn.execute("""
            CREATE TABLE syllabus_archive (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER REFERENCES teachers(id) ON DELETE SET NULL,
                course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                filename TEXT NOT NULL DEFAULT '',
                original_filename TEXT NOT NULL DEFAULT '',
                file_size INTEGER DEFAULT 0,
                archived_by INTEGER REFERENCES users(id),
                archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_syllabus_archive_course ON syllabus_archive(course_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_syllabus_archive_teacher ON syllabus_archive(teacher_id)')

    # ── Course form archive (المقرر) — old versions kept on update ───
    if 'course_form_archive' not in existing_tables:
        conn.execute("""
            CREATE TABLE course_form_archive (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                submission_id INTEGER REFERENCES course_content_submissions(id) ON DELETE SET NULL,
                filename TEXT NOT NULL DEFAULT '',
                original_filename TEXT NOT NULL DEFAULT '',
                file_size INTEGER DEFAULT 0,
                archived_by INTEGER REFERENCES users(id),
                archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_course_form_archive_course ON course_form_archive(course_id)')

    # ── Course-owned file store (course_files) + backfill ─────────────
    _migrate_course_files(conn)

    # ── Academic periods (الفصل الدراسي) for course content ──────────
    _migrate_academic_periods(conn)

    # ── Faculty Performance Evaluation (كشف العبء التدريسي) ─────────
    _ensure_faculty_performance_tables(conn, existing_tables)

    # ── Canonical room types (قاعات + معملان فقط) ────────────────────
    _migrate_canonical_room_types(conn)

    # ── Academic calendar: date boundaries on semesters ──────────────
    _migrate_academic_calendar(conn)

    # ── Enrich teacher_taught_courses with schedule details ─────────
    _migrate_teacher_taught_courses(conn)

    # ── Enforce a single active timetable version per dept + semester ──
    _migrate_single_active_timetable_version(conn)

    # ── Persist the logical domain registry (Identity/Academic/Scheduling/... ) ──
    sync_domain_registry(conn)

    conn.commit()
