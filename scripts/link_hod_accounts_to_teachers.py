"""Link the seeded head-of-department accounts to real teacher records.

Every ``users`` row with ``role='head_of_department'`` that has no linked
teacher gets a matching ``teachers`` row (name derived from its label),
so the department head appears in /teachers with the proper heads-up badge
and receives message notifications correctly.

Idempotent: accounts already linked to a teacher are skipped.

Usage:  python scripts/link_hod_accounts_to_teachers.py
"""

from __future__ import annotations

import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from database.connection import connect
from database.schema import ensure_schema

DATABASE = 'database/data.db'


def _next_available_number(db, base: str) -> str:
    existing = {r['academic_number'] for r in db.execute(
        'SELECT academic_number FROM teachers WHERE academic_number IS NOT NULL'
    ).fetchall()}
    candidate = base
    i = 1
    while candidate in existing or (candidate or '').strip() == '':
        i += 1
        candidate = f'{base}-{i}'
    return candidate


def main() -> None:
    db = connect(DATABASE)
    ensure_schema(db)

    nodes = db.execute(
        '''SELECT u.id AS user_id, u.username, u.label, u.email, u.department_id,
                  d.name AS dept_name
           FROM users u
           LEFT JOIN departments d ON d.id = u.department_id
           WHERE u.role = 'head_of_department' AND u.department_id IS NOT NULL
           ORDER BY u.department_id'''
    ).fetchall()

    linked = {r['user_id'] for r in db.execute(
        'SELECT user_id FROM teachers WHERE user_id IS NOT NULL'
    ).fetchall()}

    created = 0
    for row in nodes:
        user_id = row['user_id']
        if user_id in linked:
            print(f'[تخطي] {row["username"]} مرتبط بأستاذ مسبقاً')
            continue
        label = (row['label'] or '').strip()
        name = label if label.startswith('رئيس') else f'رئيس {row["dept_name"] or label or "القسم"}'
        email = (row['email'] or '').strip() or f'{row["username"]}@test.local'
        dept_id = row['department_id']
        an = _next_available_number(db, f'HOD-{dept_id}')
        db.execute(
            '''INSERT INTO teachers
               (name, email, phone, department_id, hod_department_id,
                academic_number, position, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (name, email, '', dept_id, dept_id, an, 'رئيس قسم', user_id),
        )
        created += 1
        print(f'[ربط] {row["username"]} → أستاذ "{name}" في {row["dept_name"]}')

    db.commit()
    db.close()
    print()
    print(f'=== تم ربط {created} حساب رئيس قسم بأساتذة ===')
    if not created:
        print('  (لا حسابات جديدة — جميعها مرتبطة مسبقاً)')


if __name__ == '__main__':
    main()