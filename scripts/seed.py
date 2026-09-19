"""Seeding a fresh database with default users, departments, rooms, courses,
and teachers.

``bootstrap_defaults`` mirrors the legacy ``data/db.py`` behaviour: it opens a
connection to *path*, runs ``ensure_schema`` and inserts the default records.
The timetable is intentionally never seeded — it must be created manually.
"""

from __future__ import annotations

import os
import sqlite3

from database.connection import connect
from database.schema import ensure_schema
from database.seed_data import (
    COURSE_ICON_MAP,
    DEFAULT_COURSE_DEPARTMENT_OVERRIDES,
    DEFAULT_COURSE_ICON,
    DEFAULT_DEPARTMENTS,
    DEFAULT_ROOMS,
    DEFAULT_TEACHERS,
    HIDDEN_DEPARTMENTS,
)


def _course_category_letter(department_name: str) -> str:
    normalized = (department_name or '').strip()
    if normalized in {'قسم النفط', 'قسم المدني', 'قسم المعماري'}:
        return 'ه'
    if normalized in {'قسم الحاسوب', 'قسم الاتصالات'}:
        return 'ت'
    return 'ع'


def _seed_default_courses(conn: sqlite3.Connection) -> int:
    from database.seed_data import DEFAULT_COURSE_CATALOG

    existing_names = {
        row['name']
        for row in conn.execute('SELECT name FROM courses').fetchall()
    }
    existing_codes = {
        row['code'].replace('هـ', 'ه')
        for row in conn.execute('SELECT code FROM courses').fetchall()
    }
    next_sequence_by_prefix = {}
    inserted = 0

    for department, year, course_names in DEFAULT_COURSE_CATALOG:
        prefix = f'{_course_category_letter(department)}{year}'
        next_sequence = next_sequence_by_prefix.get(prefix, 1)

        for name in course_names:
            if name in existing_names:
                continue

            while True:
                code = f'{prefix}{next_sequence:02d}'
                next_sequence += 1
                if code not in existing_codes:
                    break

            dept_id = conn.execute(
                'SELECT id FROM departments WHERE name = ?', (department,)
            ).fetchone()
            dept_id = dept_id['id'] if dept_id else None

            conn.execute(
                '''
                INSERT INTO courses (name, code, department, department_id, year, notes, icon)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                (name, code, department, dept_id, year, None, COURSE_ICON_MAP.get(name, DEFAULT_COURSE_ICON)),
            )
            existing_names.add(name)
            existing_codes.add(code)
            inserted += 1

        next_sequence_by_prefix[prefix] = next_sequence

    return inserted


def _rebalance_default_courses(conn: sqlite3.Connection) -> int:
    updated = 0
    for course_name, department in DEFAULT_COURSE_DEPARTMENT_OVERRIDES.items():
        dept_id = conn.execute(
            'SELECT id FROM departments WHERE name = ?', (department,)
        ).fetchone()
        dept_id = dept_id['id'] if dept_id else None
        cursor = conn.execute(
            '''
            UPDATE courses
            SET department = ?, department_id = ?
            WHERE name = ?
            ''',
            (department, dept_id, course_name),
        )
        updated += cursor.rowcount if cursor.rowcount is not None else 0
    return updated


def _seed_default_teachers(conn: sqlite3.Connection, owner_user_id: int) -> int:
    existing_names = {
        row['name']
        for row in conn.execute(
            'SELECT name FROM teachers',
        ).fetchall()
    }
    inserted = 0

    for entry in DEFAULT_TEACHERS:
        if isinstance(entry, str):
            name = entry
            department = ''
            qualification = ''
            academic_rank = ''
            phone = ''
        else:
            name = entry[0]
            department = entry[1] if len(entry) > 1 else ''
            qualification = entry[3] if len(entry) > 3 else ''
            academic_rank = entry[4] if len(entry) > 4 else ''
            phone = entry[5] if len(entry) > 5 else ''

        if name in existing_names:
            continue
        conn.execute(
            '''
            INSERT INTO teachers (user_id, name, department, qualification, academic_rank, phone)
            VALUES (NULL, ?, ?, ?, ?, ?)
            ''',
            (name, department, qualification, academic_rank, phone),
        )
        inserted += 1

    return inserted


def bootstrap_defaults(path: str) -> None:
    """Seed default users, departments, rooms, courses, and teachers."""
    import secrets
    from werkzeug.security import generate_password_hash

    db = connect(path)
    ensure_schema(db)

    admin_pw = os.environ.get('ADMIN_PASSWORD')
    if not admin_pw:
        admin_pw = secrets.token_urlsafe(12)
        generated_pw = admin_pw
    else:
        generated_pw = None

    users = [
        ('superadmin', generate_password_hash(admin_pw)),
        ('admin', generate_password_hash(admin_pw)),
    ]
    created_any = False
    for username, password in users:
        exists = db.execute('SELECT 1 FROM users WHERE username = ?', (username,)).fetchone()
        if not exists:
            role = 'super_admin' if username == 'superadmin' else 'head_of_department'
            label = 'General Department' if username == 'superadmin' else 'Default Department'
            db.execute(
                'INSERT INTO users (username, password, role, label) VALUES (?, ?, ?, ?)',
                (username, password, role, label),
            )
            created_any = True

    if created_any and generated_pw:
        print(f'[seed] No ADMIN_PASSWORD env set - generated login superadmin/admin password: {generated_pw}')
        print('[seed] Store it now; it will not be shown again.\n')

    for name, semesters, majors in DEFAULT_DEPARTMENTS:
        exists = db.execute('SELECT 1 FROM departments WHERE name = ?', (name,)).fetchone()
        if not exists:
            db.execute(
                'INSERT INTO departments (name, semesters, majors, hidden, has_sections, type) VALUES (?, ?, ?, 0, 1, ?)',
                (name, semesters, majors, 'academic'),
            )

    for item in HIDDEN_DEPARTMENTS:
        name = item[0]
        semesters = item[1] if len(item) > 1 else ''
        majors = item[2] if len(item) > 2 else ''
        exists = db.execute('SELECT 1 FROM departments WHERE name = ?', (name,)).fetchone()
        if exists:
            db.execute(
                'UPDATE departments SET hidden=1, has_sections=0, type=? WHERE name=?',
                ('administrative', name),
            )
        else:
            db.execute(
                'INSERT INTO departments (name, semesters, majors, hidden, has_sections, type) VALUES (?, ?, ?, 1, 0, ?)',
                (name, semesters, majors, 'administrative'),
            )

    # Semester codes (fall_2026 …) are computed from the current date;
    # there is no semesters table anymore (academic calendar removed).

    default_department = db.execute(
        'SELECT id, name FROM departments ORDER BY id LIMIT 1'
    ).fetchone()
    if default_department is not None:
        unassigned_hods = db.execute(
            "SELECT id FROM users WHERE role = 'head_of_department' AND (department_id IS NULL OR department_id = '')"
        ).fetchall()
        for hod in unassigned_hods:
            fallback = db.execute(
                'SELECT id, name FROM departments WHERE id NOT IN '
                "(SELECT department_id FROM users WHERE role = 'head_of_department' AND department_id IS NOT NULL) "
                'ORDER BY id LIMIT 1'
            ).fetchone()
            if fallback:
                db.execute(
                    'UPDATE users SET department_id = ?, label = ? WHERE id = ?',
                    (fallback['id'], fallback['name'], hod['id']),
                )

    for name, name_ar, type_, status, capacity, location in DEFAULT_ROOMS:
        exists = db.execute('SELECT 1 FROM rooms WHERE name = ?', (name,)).fetchone()
        if not exists:
            db.execute(
                '''
                INSERT INTO rooms (name, type, status, capacity, location, department_id)
                VALUES (?, ?, ?, ?, ?, 1)
                ''',
                (name, type_, status, capacity, location),
            )

    _seed_default_courses(db)
    _rebalance_default_courses(db)
    owner = db.execute("SELECT id FROM users WHERE username = 'superadmin'").fetchone()
    owner_user_id = owner['id'] if owner else 1
    _seed_default_teachers(db, owner_user_id)

    db.commit()
    db.close()
