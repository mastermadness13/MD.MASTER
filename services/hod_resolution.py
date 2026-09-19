"""تحديد رئيس القسم الحالي بطريقة موحّدة.

الترتيب المتبنى في النظام:
1. أستاذ حاصل على القسم عبر ``teachers.hod_department_id`` (غير محذوف).
2. احتياطي: حساب مستخدم بدور ``head_of_department`` مربوط بالقسم
   عبر ``users.department_id`` (الاسم يُقرأ من الأستاذ المرتبط أو من الوسم).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def get_current_hod(db, department_id) -> Optional[Dict[str, Any]]:
    """رئيس القسم الحالي لقسم معيّن، أو ``None`` إن لم يُعيَّن.

    يعيد قاموساً بالشكل:
    ``{'name': str, 'teacher_id': Optional[int], 'user_id': Optional[int],
       'source': 'teacher' | 'account'}``
    """
    if not department_id:
        return None

    teacher = db.execute(
        '''SELECT t.id AS teacher_id, t.name AS name, t.user_id
           FROM teachers t
           WHERE t.hod_department_id = ? AND t.deleted_at IS NULL
           ORDER BY t.id ASC LIMIT 1''',
        (department_id,),
    ).fetchone()
    if teacher:
        return {
            'name': teacher['name'],
            'teacher_id': teacher['teacher_id'],
            'user_id': teacher['user_id'],
            'source': 'teacher',
        }

    account = db.execute(
        '''SELECT u.id AS user_id, u.label,
                  t.name AS teacher_name, t.id AS teacher_id
           FROM users u
           LEFT JOIN teachers t ON t.user_id = u.id AND t.deleted_at IS NULL
           WHERE u.role = 'head_of_department' AND u.department_id = ?
           ORDER BY u.id ASC LIMIT 1''',
        (department_id,),
    ).fetchone()
    if account:
        return {
            'name': account['teacher_name'] or (account['label'] or 'رئيس القسم'),
            'teacher_id': account['teacher_id'],
            'user_id': account['user_id'],
            'source': 'account',
        }
    return None


def department_hod_map(db, department_ids: Optional[List[int]] = None) -> Dict[int, Dict[str, Any]]:
    """خريطة ``{department_id: {...}}`` لرؤساء الأقسام المطلوبة.

    تُبنى بمسحيَّن (الأساتذة ثم الاحتياطي) بحيث يفوز الأستاذ دائماً.
    """
    result: Dict[int, Dict[str, Any]] = {}
    if department_ids:
        marks = ','.join('?' * len(department_ids))
        teacher_where = f'AND t.hod_department_id IN ({marks})'
        user_where = f'AND u.department_id IN ({marks})'
    else:
        teacher_where = ''
        user_where = ''

    rows = db.execute(
        f'''SELECT t.hod_department_id AS dept_id, t.id AS teacher_id,
                   t.name AS name, t.user_id
            FROM teachers t
            WHERE t.hod_department_id IS NOT NULL AND t.deleted_at IS NULL
                  {teacher_where}''',
        tuple(department_ids or ()),
    ).fetchall()
    for row in rows:
        result[row['dept_id']] = {
            'name': row['name'],
            'teacher_id': row['teacher_id'],
            'user_id': row['user_id'],
            'source': 'teacher',
        }

    accounts = db.execute(
        f'''SELECT u.department_id AS dept_id, u.id AS user_id, u.label,
                   t.name AS teacher_name, t.id AS teacher_id
            FROM users u
            LEFT JOIN teachers t ON t.user_id = u.id AND t.deleted_at IS NULL
            WHERE u.role = 'head_of_department' AND u.department_id IS NOT NULL
                  {user_where}
            ORDER BY u.id ASC''',
        tuple(department_ids or ()),
    ).fetchall()
    for row in accounts:
        if row['dept_id'] in result:
            continue  # /     /     >---- الأستاذ أولى من الاحتياطي
        result[row['dept_id']] = {
            'name': row['teacher_name'] or (row['label'] or 'رئيس القسم'),
            'teacher_id': row['teacher_id'],
            'user_id': row['user_id'],
            'source': 'account',
        }
    return result