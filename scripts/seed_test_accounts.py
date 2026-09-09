"""Create test accounts for every system role (idempotent).

Adds a login-able account for each role so the whole system can be tried:

  - teacher              (أستاذ)
  - head_of_department   (رئيس القسم) — one per academic department
  - research_development (قسم البحث والتطوير)
  - exam                 (الامتحانات)
  - faculty_affairs      (شؤون هيئة التدريس)

Existing usernames are skipped.  All new accounts share the password
``test123``.  Pre-existing seed accounts keep their credentials
(``superadmin``/``admin`` = ``admin123``, teachers = ``123456``).

Usage:  python scripts/seed_test_accounts.py
"""

from __future__ import annotations

import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from database.connection import connect
from database.schema import ensure_schema
from services import user_service

DATABASE = 'database/data.db'
TEST_PASSWORD = 'test123'

HOD_ACCOUNTS = [
    ('hod_computer', 'قسم الحاسوب', 'رئيس قسم الحاسوب'),
    ('hod_general', 'القسم العام', 'رئيس القسم العام'),
    ('hod_comms', 'قسم الاتصالات', 'رئيس قسم الاتصالات'),
    ('hod_civil', 'قسم المدني', 'رئيس قسم المدني'),
    ('hod_arch', 'قسم المعماري', 'رئيس قسم المعماري'),
    ('hod_oil', 'قسم النفط', 'رئيس قسم النفط'),
    ('hod_apps', 'تطبيقات الحاسوب', 'رئيس قسم تطبيقات الحاسوب'),
]

ADMIN_ACCOUNTS = [
    ('rnd', 'research_development', 'قسم البحث والتطوير'),
    ('exams', 'exam', 'إدارة الامتحانات'),
    ('faculty', 'faculty_affairs', 'شؤون هيئة التدريس'),
]


def _department_id(db, name):
    row = db.execute('SELECT id FROM departments WHERE name = ?', (name,)).fetchone()
    return row['id'] if row else None


def _has_hod(db, department_id):
    row = db.execute(
        "SELECT 1 FROM users WHERE role = 'head_of_department' AND department_id = ?",
        (department_id,),
    ).fetchone()
    return row is not None


def main() -> None:
    db = connect(DATABASE)
    ensure_schema(db)

    created = []

    if user_service.username_exists(db, 'teacher'):
        print('[تخطي] مستخدم موجود: teacher')
    else:
        dept_id = _department_id(db, 'قسم الحاسوب')
        user_service.create_user_with_profile(
            db, 'teacher', TEST_PASSWORD, 'teacher', dept_id,
            email='teacher@test.local', label='أستاذ تجريبي',
        )
        created.append('teacher')
        print('[إنشاء] teacher (أستاذ)')

    for username, dept_name, label in HOD_ACCOUNTS:
        if user_service.username_exists(db, username):
            print(f'[تخطي] مستخدم موجود: {username}')
            continue
        dept_id = _department_id(db, dept_name)
        if dept_id is None:
            print(f'[تخطي] قسم غير موجود: {dept_name}')
            continue
        if _has_hod(db, dept_id):
            print(f'[تخطي] {dept_name} لديه رئيس قسم مسبقاً ({username})')
            continue
        user_service.create_user_with_profile(
            db, username, TEST_PASSWORD, 'head_of_department', dept_id,
            email=f'{username}@test.local', label=label,
        )
        created.append(username)
        print(f'[إنشاء] {username} (رئيس {dept_name})')

    for username, role, label in ADMIN_ACCOUNTS:
        if user_service.username_exists(db, username):
            print(f'[تخطي] مستخدم موجود: {username}')
            continue
        user_service.create_user_with_profile(
            db, username, TEST_PASSWORD, role, None,
            email=f'{username}@test.local', label=label,
        )
        created.append(username)
        print(f'[إنشاء] {username} ({label})')

    db.commit()
    db.close()

    print()
    print(f'=== حسابات التجربة الجديدة (كلمة السر: {TEST_PASSWORD}) ===')
    for username in created:
        print(f'  {username}  /  {TEST_PASSWORD}')
    if not created:
        print('  (لا حسابات جديدة — جميعها موجودة مسبقاً)')


if __name__ == '__main__':
    main()
