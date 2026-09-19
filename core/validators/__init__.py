"""Input validation helpers.

Every public function returns a list of error strings (empty = valid).
Functions accept raw form data and expected field names.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from core.constants import PASSWORD_MIN_LENGTH

# ─────────────────────────────────────────────

# /     /     >---- نتأكد الحقل موجود وما فاضي
def required(value: Any, field_name: str) -> Optional[str]:
    # /     /     >---- إذا القيمة لا شيء أو نص فاضي نرجع خطأ "مطلوب"
    if value is None or (isinstance(value, str) and not value.strip()):
        return f'{field_name} مطلوب'
    return None

# ─────────────────────────────────────────────

# /     /     >---- نتأكد النص يولم عدد حروف معينة
def min_length(value: str, min_len: int, field_name: str) -> Optional[str]:
    if value and len(value.strip()) < min_len:
        return f'{field_name} يجب أن يكون على الأقل {min_len} حرف'
    return None

# ─────────────────────────────────────────────

# /     /     >---- نتأكد النص ما يتجاوز عدد حروف معين
def max_length(value: str, max_len: int, field_name: str) -> Optional[str]:
    if value and len(value) > max_len:
        return f'{field_name} يجب ألا يتجاوز {max_len} حرف'
    return None

# ─────────────────────────────────────────────

# /     /     >---- نتأكد البريد الإلكتروني صحيح (pattern)
def valid_email(value: str, field_name: str = 'البريد الإلكتروني') -> Optional[str]:
    if value and not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', value):
        return f'{field_name} غير صحيح'
    return None

# ─────────────────────────────────────────────

# /     /     >---- نتأكد رقم الهاتف صحيح (7-20 رقم/رموز)
def valid_phone(value: str, field_name: str = 'رقم الهاتف') -> Optional[str]:
    if value and not re.match(r'^[\d+\-\s()]{7,20}$', value):
        return f'{field_name} غير صحيح'
    return None

# ─────────────────────────────────────────────

# /     /     >---- نتأكد اسم المستخدم ما فيه رموز ممنوعة
def valid_username(value: str) -> Optional[str]:
    if value and not re.match(r'^[a-zA-Z0-9._-]+$', value):
        return 'اسم المستخدم يجب أن يحتوي على أحرف وأرقام ونقاط وشرطات فقط'
    return None

# ─────────────────────────────────────────────

# /     /     >---- نتأكد كلمتا المرور متطابقتين
def password_match(pw: str, confirm: str) -> Optional[str]:
    if pw != confirm:
        return 'كلمتا المرور غير متطابقتين'
    return None

# ─────────────────────────────────────────────

# /     /     >---- نتأكد كلمة المرور طولها صحيح
def valid_password(pw: str) -> Optional[str]:
    if pw and len(pw) < PASSWORD_MIN_LENGTH:
        return f'كلمة المرور يجب أن تكون على الأقل {PASSWORD_MIN_LENGTH} أحرف'
    return None

# ─────────────────────────────────────────────

# /     /     >---- نتأكد المعرف (ID) رقم صحيح
def valid_id(value: Any, field_name: str = 'المعرف') -> Optional[str]:
    # /     /     >---- إذا فاضي مطلوب
    if value is None or value == '':
        return f'{field_name} مطلوب'
    try:
        int(value)
    except (ValueError, TypeError):
        return f'{field_name} يجب أن يكون رقماً'
    return None

# ─────────────────────────────────────────────

# /     /     >---- نشغّل قائمة قواعد التحقق ونجمع كل الأخطاء
def validate(data: Dict[str, Any], rules: List) -> List[str]:
    """Run a list of validation rules and return all error messages.

    Each rule is a callable that returns an error string or None.

    Example::

        errors = validate(form_data, [
            lambda: required(form_data.get('name'), 'الاسم'),
            lambda: min_length(form_data.get('name', ''), 2, 'الاسم'),
            lambda: valid_email(form_data.get('email', '')),
        ])
    """
    errors = []
    for rule in rules:
        err = rule()
        if err:
            errors.append(err)
    return errors