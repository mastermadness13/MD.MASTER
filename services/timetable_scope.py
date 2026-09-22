"""صلاحيات الجدول الدراسي + قاعدة القسم العام — مصدر الحقيقة الواحد.

Phase 0: قاعدة الفصول المسموحة والدوال المساعدة فقط.
الوصل بالمسارات (routes) يتم في المرحلة الثانية.

كل قرار يتعلق "بأي فصل مسموح لأي قسم" يمر من هنا — لا تكرار بعد الآن في
المسارات ولا في الخدمة. القسم العام يُكتشف بالبيانات (الاسم أو عدد الفصول)
وليست بمعرّف ثابت حتى لا تنكسر القاعدة عند تغيّر المعرفات.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from security.authorization import has_permission

# ─────────────────────────────────────────────
# قاعدة الفصول: القسم العام = الفصل 1 فقط
#                 باقي الأقسام = [2 .. عدد فصول القسم] (الأقصى 8)
# ─────────────────────────────────────────────
GENERAL_DEPT_NAME = 'القسم العام'
INVALID_SEMESTER_MESSAGE = 'الفصل المختار غير مسموح لهذا القسم'


class InvalidSemesterError(Exception):
    """تُرمى عندما يكون الفصل المطلوب غير مسموح لقسم الحصة."""


def _col(row, key, default):
    """قراءة عمود من قاموس أو صف قاعدة بيانات (sqlite3.Row)."""
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


# ─────────────────────────────────────────────

# /     /     >---- كشف القسم العام بالاسم أو بعدد الفصول
def is_general_dept(dept) -> bool:
    """هل هذا القسم هو «القسم العام»؟

    يُكتشف بأكثر من طريقة حماية للبيانات: الاسم المطابق، أو عدد فصول <= 1.
    غياب العمود لا يُعدّ عاماً — الاسم وحده يُقرر حينها.
    """
    if not dept:
        return False
    name = _col(dept, 'name', None)
    if name is not None and str(name).strip() == GENERAL_DEPT_NAME:
        return True
    semesters = _col(dept, 'semesters', None)
    if semesters is None:
        return False
    try:
        return int(semesters) <= 1
    except (TypeError, ValueError):
        return False


# /     /     >---- الفصول المسموحة للقسم
def allowed_semesters_for(dept) -> List[int]:
    """الفصول المسموحة لقسم: «القسم العام» = [1] والباقي [2..8].

    الأقسام غير العامة تحترم عدد فصولها (قسم بـ 5 فصول = [2,3,4,5]).
    """
    if not dept or is_general_dept(dept):
        return [1]
    semesters = _col(dept, 'semesters', 8)
    try:
        total = int(semesters)
    except (TypeError, ValueError):
        total = 8
    if total <= 1:
        return [1]
    return list(range(2, min(total, 8) + 1))


# /     /     >---- تحقق مركزي يستدعيه كل مسار كتابة
def validate_semester_allowed(db, department_id, semester) -> None:
    """يرفض الفصل غير المسموح لقسم الحصة برمي InvalidSemesterError.

    تُستدعى قبل أي أثر جانبي (قبل إنشاء النسخة) وفي طبقة الخدمة كدفاع.
    """
    if not department_id:
        return
    row = db.execute(
        'SELECT name, semesters FROM departments WHERE id = ?',
        (department_id,),
    ).fetchone()
    if row is None:
        return
    allowed = allowed_semesters_for(row)
    try:
        sem = int(semester)
    except (TypeError, ValueError):
        raise InvalidSemesterError(INVALID_SEMESTER_MESSAGE)
    if sem not in allowed:
        raise InvalidSemesterError(INVALID_SEMESTER_MESSAGE)


# ─────────────────────────────────────────────
# نطاق الصلاحيات لكل مستخدم — مرآة قواعد المسارات الحالية
# ─────────────────────────────────────────────

def _normalized_roles(user) -> list:
    roles = _col(user, 'roles', None) or _col(user, 'role', None) or []
    if isinstance(roles, str):
        roles = [roles]
    return [r for r in roles if r]


# /     /     >---- نطاق مستخدم واحد (قرارات الرؤية/التعديل/الطباعة)
def compute_scope(user) -> Dict[str, Any]:
    """نطاق صلاحيات الجدول لمستخدم واحد، مطابق لقواعد المسارات الحالية.

    Phase 0: منشأة وموثّقة بالاختبارات — تُوصل بالمسارات في المرحلة الثانية.
    """
    if not user or not _col(user, 'id', None):
        return {
            'can_view': False, 'can_edit': False, 'can_print_all': False,
            'is_hod': False, 'user_dept': None, 'editable_dept_id': None,
            'own_teacher_id': None,
        }
    roles = _normalized_roles(user)
    is_hod = 'head_of_department' in roles
    user_dept = _col(user, 'hod_department_id', None) or _col(user, 'department_id', None)
    can_view = has_permission(roles, 'timetable.view')
    can_edit = has_permission(roles, 'timetable.edit')
    return {
        'can_view': can_view,
        'can_edit': can_edit,
        'can_print_all': can_view,          # المسارات الحالية تشترط view فقط
        'is_hod': is_hod,
        'user_dept': user_dept,
        'editable_dept_id': user_dept if is_hod else None,
        'own_teacher_id': _col(user, 'teacher_id', None),
    }


# /     /     >---- هل يستطيع المستخدم تحرير قسم معيّن؟
def can_edit_entry(user, dept_id) -> bool:
    """رئيس القسم يعدّل قسمه فقط، والباقي يعدّل كل الأقسام المرئية له."""
    scope = compute_scope(user)
    if not scope['can_edit']:
        return False
    if scope['is_hod']:
        return scope['editable_dept_id'] is not None and dept_id == scope['editable_dept_id']
    return True


# ─────────────────────────────────────────────
# رمز تتبّع التغييرات (لدعم التحديث الفوري في المرحلة الثانية)
# ─────────────────────────────────────────────

# /     /     >---- رمز نسخة + عدد حصص يقارن به العميل التغييرات
def semester_token(db, dept_id, semester) -> str:
    """رمز يستخدم للكشف عن تغيّر جدول (قسم، فصل) دون جلب البيانات كل مرة."""
    ver_row = db.execute(
        'SELECT COALESCE(MAX(id), 0) FROM timetable_versions '
        'WHERE department_id = ? AND semester = ?',
        (dept_id, semester),
    ).fetchone()
    max_version_id = int(ver_row[0]) if ver_row else 0
    cnt_row = db.execute(
        'SELECT COUNT(*) FROM timetable '
        'WHERE department_id = ? AND semester = ? '
        'AND (version_id IS NULL OR version_id IN '
        "(SELECT id FROM timetable_versions WHERE status = 'active'))",
        (dept_id, semester),
    ).fetchone()
    count = int(cnt_row[0]) if cnt_row else 0
    return f'{max_version_id}:{count}'