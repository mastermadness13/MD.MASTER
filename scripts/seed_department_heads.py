"""Create the department-head accounts with a shared short password (idempotent).

The real department heads and administrative managers:

  amal     / 123123  -> رئيس قسم الحاسوب
  ilham    / 123123  -> مدير مكتب أعضاء هيئة التدريس
  hanan    / 123123  -> رئيس قسم العمارة
  yasser   / 123123  -> رئيس قسم المدني
  murad    / 123123  -> رئيس قسم النفط
  fawzi    / 123123  -> رئيس قسم الاتصالات
  ghaliya  / 123123  -> رئيس قسم البحث والتطوير والمناهج
  abdo     / 123123  -> رئيس قسم الدراسة والامتحانات

Existing usernames and already-assigned HOD departments are skipped.

Usage:  python scripts/seed_department_heads.py
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
PASSWORD = '123123'

# (username, role, academic_department, label, administrative_department)
ACCOUNTS = [
    ('amal', 'head_of_department', 'قسم الحاسوب', 'رئيس قسم الحاسوب', None),
    ('ilham', 'faculty_affairs', None, 'مدير مكتب أعضاء هيئة التدريس', None),
    ('hanan', 'head_of_department', 'قسم المعماري', 'رئيس قسم العمارة', None),
    ('yasser', 'head_of_department', 'قسم المدني', 'رئيس قسم المدني', None),
    ('murad', 'head_of_department', 'قسم النفط', 'رئيس قسم النفط', None),
    ('fawzi', 'head_of_department', 'قسم الاتصالات', 'رئيس قسم الاتصالات', None),
    ('ghaliya', 'research_development', None, 'رئيس قسم البحث والتطوير والمناهج', 'قسم البحث والتطوير'),
    ('abdo', 'exam', None, 'رئيس قسم الدراسة والامتحانات', 'إدارة الامتحانات'),
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
    for username, role, dept_name, label, admin_dept_name in ACCOUNTS:
        if user_service.username_exists(db, username):
            print(f'[تخطي] مستخدم موجود: {username}')
            continue

        dept_id = _department_id(db, dept_name) if dept_name else None
        if dept_name and dept_id is None:
            print(f'[تخطي] قسم غير موجود: {dept_name}')
            continue
        if dept_name and _has_hod(db, dept_id):
            print(f'[تخطي] {dept_name} لديه رئيس قسم مسبقاً ({username})')
            continue

        admin_dept_id = _department_id(db, admin_dept_name) if admin_dept_name else None
        if admin_dept_name and admin_dept_id is None:
            print(f'[تخطي] قسم إداري غير موجود: {admin_dept_name}')
            continue

        user_service.create_user_with_profile(
            db, username, PASSWORD, role, dept_id,
            email=f'{username}@zuwaratc.edu.ly', label=label,
            administrative_department_id=admin_dept_id,
        )
        created.append(username)
        print(f'[إنشاء] {username} ({label})')

    db.commit()
    db.close()

    print()
    print(f'=== حسابات رؤساء الأقسام (كلمة السر: {PASSWORD}) ===')
    for username in created:
        print(f'  {username}  /  {PASSWORD}')
    if not created:
        print('  (لا حسابات جديدة — جميعها موجودة مسبقاً)')


if __name__ == '__main__':
    main()