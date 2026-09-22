"""User service — authentication, CRUD, password management.

Refactored to accept repository injection while maintaining backward
compatibility with the existing module-level function API.

/     /     >---- خدمة المستخدمين: تسجيل الدخول، إدارة الحسابات، وكلمات المرور.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from werkzeug.security import generate_password_hash, check_password_hash

from core.constants import (
    PASSWORD_RESET_EXPIRY_HOURS,
    ROLE_NAMES,
)
from core.exceptions import ConflictError, ProtectedAccountError, ValidationError
from security.authorization import highest_priority_role
from services.hod_resolution import get_current_hod

logger = logging.getLogger(__name__)

# /     /     >---- تجزئة وهمية تُستخدم دائماً لمنع تمييز الحسابات (CWE-204)
# /     /     >---- hasher موحد لضمان استهلاك نفس الوقت سواء وُجد المستخدم أم لا
_DUMMY_PASSWORD_HASH = generate_password_hash('dummy-not-a-real-account-3x!Kq')

# /     /     >---- الأدوار الإدارية ما تنتميش لقسم أكاديمي
_DEPARTMENTLESS_ROLES = frozenset({'exam'})

# /     /     >---- الأدوار الإدارية اللي كياخدو وحدة إدارية (مش قسم أكاديمي)
_ADMINISTRATIVE_ROLES = frozenset({'faculty_affairs', 'research_development', 'exam'})

# /     /     >---- الأدوار اللي كياخدو قسم أكاديمي
_ACADEMIC_ROLES = frozenset({'teacher', 'head_of_department'})

# /     /     >---- حساب مدير مكتب أعضاء هيئة التدريس الأساسي (محمي)
_PRIMARY_OFFICE_MANAGER_USERNAME = 'office_manager'


class UserService:
    """Class-based user service with dependency injection.

    /     /     >---- خدمة المستخدمين بشكل كلاس مع حقن التبعيات.
    """

    def __init__(self, db, user_repository, teacher_repository=None):
        self.db = db
        self._repo = user_repository
        self._teacher_repo = teacher_repository

    # /     /     >---- حماية حساب مدير المكتب الأساسي

    # /     /     >---- نتحقق هل المستخدم هو مدير المكتب الأساسي (بالدور أو بجدول الأدوار)
    def is_protected_user(self, user_id: int) -> bool:
        """Return True if the user is the primary office-manager (by landing
        role or by an explicit ``faculty_affairs`` entry in ``user_roles``).

        A protected account can never be deleted, deactivated,
        demoted, or stripped of its ``faculty_affairs`` role, even via a direct
        service call (not just hidden UI buttons).
        """
        user = self._repo.find_by_id(user_id)
        if not user:
            return False
        if user.get('username') != _PRIMARY_OFFICE_MANAGER_USERNAME:
            return False
        if user.get('role') == 'faculty_affairs':
            return True
        roles = self._repo.find_roles_by_user(user_id) or []
        return 'faculty_affairs' in roles

    # /     /     >---- مانع: ما نخلّيش أي عملية تخريبية على حساب محمي
    def _guard_against_destructive(self, user_id: int) -> None:
        if self.is_protected_user(user_id):
            raise ProtectedAccountError()

    # /     /     >---- المصادقة (تسجيل الدخول)

    # /     /     >---- تسجيل الدخول: تحقق من اسم المستخدم وكلمة المرور، ونسجّل الجلسة
    def authenticate(self, username: str, password: str, remember: bool,
                     session_dict: dict) -> Tuple[bool, Optional[Dict]]:
        user = self._repo.find_by_username(username)
        # /     /     >---- دائماً نتحقق من التجزئة حتى لو المستخدم غير موجود
        # /     /     >---- هذا يمنع تمييز الحسابات عبر فرق التوقيت (CWE-204)
        pw_hash = user['password'] if user else _DUMMY_PASSWORD_HASH
        if not check_password_hash(pw_hash, password):
            return False, None
        if not user:
            return False, None
        # /     /     >---- رمز أولي منتهي الصلاحية ولم يُستعمل: يُرفض الدخول
        # /     /     >---- (المستخدم يسترجع الرمز عبر المسار القياسي ببريده)
        # /     /     >---- نرجع علامة مميزة بدلاً من None حتى تعرض الواجهة رسالة
        # /     /     >---- واضحة بدلاً من رسالة "البيانات غير صحيحة" المضلِّلة.
        if not user.get('is_active', 1):
            return False, None
        if (user.get('initial_login_code_used') == 0
                and user.get('initial_login_code_hash')
                and user.get('initial_login_code_expires')):
            from datetime import datetime as _dt
            try:
                exp = _dt.strptime(
                    user['initial_login_code_expires'], '%Y-%m-%d %H:%M:%S'
                )
            except (ValueError, TypeError):
                exp = None
            if exp is not None and _dt.now() > exp:
                return False, {'auth_error': 'initial_code_expired'}
        # CSRF token survives the session rebuild: forms rendered before
        # login (or replayed by the browser's Back/Forward cache) keep a
        # valid token. Without this, re-submitting a cached form after login
        # fails CSRF and flashes the error — that's what shows "خطأ في التحقق
        # الأمني (CSRF)" when pressing the Back button.
        csrf_token = session_dict.get('_csrf_token')
        session_dict.clear()
        session_dict['permanent'] = bool(remember)
        session_dict['user_id'] = user['id']
        session_dict['username'] = user['username']
        # /     /     >---- رمز الدخول الأولي: أول تسجيل ناجح يبطل استخدامه نهائياً
        # /     /     >---- (نحذف تجزئته حتى ما يبقاش صالح للاستعمال مرة ثانية)
        if user.get('initial_login_code_used') == 0 and user.get('initial_login_code_hash'):
            self.db.execute(
                'UPDATE users SET initial_login_code_used = 1, '
                'initial_login_code_hash = NULL WHERE id = ?',
                (user['id'],),
            )
            self.db.commit()
            # /     /     >---- أول دخول برمز مؤقت: نُعلّم الجلسة لتعرض
            # /     /     >---- رسالة ترحيب + اقتراح تغيير الرمز (احتفظ به أو غيّره)
            session_dict['first_login_temp_code'] = True
        # /     /     >---- أدوار متعددة: كامل مجموعة الأدوار + دور الهبوط (الأعلى أولوية)
        granted = self._repo.find_roles_by_user(user['id']) or [user['role']]
        if not granted:
            granted = [user['role']]
        session_dict['roles'] = granted
        session_dict['role'] = highest_priority_role(granted) or user['role']
        session_dict['label'] = user['label'] or ''
        # /     /     >---- المصدر الوحيد لربط المستخدم بالأستاذ هو teachers.user_id
        teacher_id = None
        hod_department_id = None
        teacher_department_id = None
        t_row = self.db.execute(
            'SELECT id, department_id, hod_department_id FROM teachers '
            'WHERE user_id = ? AND deleted_at IS NULL',
            (user['id'],),
        ).fetchone()
        if t_row:
            teacher_id = t_row['id']
            teacher_department_id = t_row['department_id']
            hod_department_id = t_row['hod_department_id']
            if not hod_department_id and teacher_department_id:
                hod_department_id = teacher_department_id
        if not hod_department_id:
            hod_department_id = user['department_id']
        session_dict['department_id'] = user['department_id'] or teacher_department_id
        session_dict['hod_department_id'] = hod_department_id
        session_dict['teacher_id'] = teacher_id
        # /     /     >---- رئيس القسم المرتبط بسجل أستاذ ياخد واجهة "المحاضر"
        # /     /     >---- (يرى جدوله ويرفع محتوى مقرراته من الهيدر)
        if (teacher_id is not None
                and 'head_of_department' in granted
                and 'teacher' not in granted):
            granted = granted + ['teacher']
            session_dict['roles'] = granted
        session_dict['administrative_department_id'] = user.get('administrative_department_id')
        session_dict['supervisor_admin_dept'] = user.get('supervisor_admin_dept', '')
        session_dict['theme'] = user['theme'] if user['theme'] else 'light'
        session_dict['_csrf_token'] = csrf_token or secrets.token_hex(32)

        from database.history import add_history
        add_history(
            self.db, 'login', 'user', user['id'],
            user['id'], user['username'],
            f'تسجيل دخول: {user["username"]}',
        )
        self.db.commit()
        return True, user

    # /     /     >---- إدارة كلمات المرور

    # /     /     >---- إنشاء رمز إعادة تعيين كلمة المرور لاسم المستخدم
    def create_password_reset(self, username: str) -> Optional[tuple]:
        # /     /     >---- تجزئة وهمية قبل الفرع دائماً لمعادلة زمن الاستجابة (CWE-204)
        check_password_hash(_DUMMY_PASSWORD_HASH, username)
        user = self._repo.find_by_username_or_email(username)
        if user:
            token = secrets.token_urlsafe(48)
            expires = (datetime.now() + timedelta(hours=PASSWORD_RESET_EXPIRY_HOURS)).strftime(
                '%Y-%m-%d %H:%M:%S'
            )
            self._repo.create_password_reset(user['id'], token, expires)
            return token, user.get('email')
        return None

    # /     /     >---- التحقق من صحة رمز إعادة التعيين وصلاحيته
    def validate_reset_token(self, token: str) -> Optional[Dict]:
        return self._repo.find_valid_reset_token(token)

    # /     /     >---- تنفيذ إعادة التعيين وتحديث كلمة المرور وعلام الرمز كمستعمل
    def reset_password(self, row: Dict, password: str) -> None:
        self._repo.update_password(row['user_id'], generate_password_hash(password))
        self._repo.mark_reset_used(row['id'])

    # /     /     >---- تغيير كلمة مرور مستخدم معين
    def change_user_password(self, user_id: int, new_password: str) -> None:
        self._repo.update_password(user_id, generate_password_hash(new_password))

    # /     /     >---- عمليات CRUD للمستخدمين

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        return self._repo.find_by_id(user_id)

    # /     /     >---- جلب الملف الكامل للمستخدم مع قسمه وأستاذه واسم الدور
    def get_user_profile(self, user_id: int) -> Optional[Dict]:
        user = self._repo.find_with_department(user_id)
        if not user:
            return None
        teacher = self._repo.get_teacher_by_user(user_id)
        return {
            'user': user,
            'teacher': teacher,
            'role_name': ROLE_NAMES.get(user['role'], user['role']),
        }

    def list_users(self, search: str = '', page: int = 1):
        return self._repo.list_users(search, page)

    def get_all_departments(self):
        return self._repo.list_visible_departments()

    # /     /     >---- الأقسام الأكاديمية الظاهرة للأدوار الأكاديمية
    def get_departments_for_role(self, role):
        from database.repositories.department_repository import DepartmentRepository
        return DepartmentRepository(self._repo.db).list_academic()

    def create_user(self, username: str, password: str, role: str,
                    department_id: int, email: str, label: str) -> None:
        self._repo.create_user({
            'username': username,
            'password': generate_password_hash(password),
            'role': role,
            'department_id': department_id,
            'email': email,
            'label': label,
        })

    def update_user(self, user_id: int, role: str, department_id: int,
                    email: str, label: str, password: str = None) -> None:
        data = {'role': role, 'department_id': department_id,
                'email': email, 'label': label}
        if password:
            data['password'] = generate_password_hash(password)
        self._repo.update_user(user_id, data)

    def delete_user(self, user_id: int) -> None:
        self._guard_against_destructive(user_id)
        self._repo.delete_user(user_id)

    # /     /     >---- تفعيل/تعطيل الحساب (تعطيل ناعم عبر is_active)
    def set_user_active(self, user_id: int, active: bool) -> None:
        """Enable/disable a user account (soft disable via ``is_active``).

        A protected office-manager account can never be deactivated.
        """
        if not active:
            self._guard_against_destructive(user_id)
        self._repo.set_user_active(user_id, bool(active))

    # /     /     >---- استبدال مجموعة أدوار المستخدم (يأبى نزع faculty_affairs من حساب محمي)
    def set_user_roles(self, user_id: int, roles) -> None:
        """Replace the user's granted role set stored in ``user_roles``.

        Refuses to strip ``faculty_affairs`` from a protected account.
        """
        if self.is_protected_user(user_id) and 'faculty_affairs' not in (roles or []):
            raise ProtectedAccountError()
        self._repo.set_user_roles(user_id, roles)

    # /     /     >---- إنشاء/تحديث مدرك للدور (دمج تدفق المستخدم + الملف)

    # /     /     >---- يرجع القسم الأكاديمي المسموح للدور، أو None
    def _force_academic_department(self, role: str, department_id):
        """Return the academic department_id allowed for the given role, or None."""
        if department_id is None:
            return None
        if role not in _ACADEMIC_ROLES:
            return None
        row = self.db.execute(
            'SELECT type FROM departments WHERE id = ?', (department_id,)
        ).fetchone()
        if not row or row['type'] != 'academic':
            return None
        return department_id

    # /     /     >---- يرجع القسم الإداري المسموح للدور، أو None
    def _force_administrative_department(self, role: str, administrative_department_id):
        """Return the administrative department_id allowed for the given role, or None."""
        if administrative_department_id is None:
            return None
        if role not in _ADMINISTRATIVE_ROLES:
            return None
        row = self.db.execute(
            'SELECT type FROM departments WHERE id = ?', (administrative_department_id,)
        ).fetchone()
        if not row or row['type'] != 'administrative':
            return None
        return administrative_department_id

    # /     /     >---- هل يوجد حساب مدير مكتب أساسي (مع إمكانية استثناء مستخدم)
    def _primary_manager_exists(self, exclude_user_id: int = None) -> bool:
        sql = "SELECT 1 FROM users WHERE username = ?"
        params = [_PRIMARY_OFFICE_MANAGER_USERNAME]
        if exclude_user_id is not None:
            sql += ' AND id != ?'
            params.append(exclude_user_id)
        return self.db.execute(sql, params).fetchone() is not None

    # /     /     >---- هل قسم رئيس القسم متاح (بدون استثناء مستخدم معين)
    def _hod_department_available(self, department_id, exclude_user_id: int = None) -> bool:
        sql = ("SELECT 1 FROM users WHERE role = 'head_of_department' "
               'AND department_id = ?')
        params = [department_id]
        if exclude_user_id is not None:
            sql += ' AND id != ?'
            params.append(exclude_user_id)
        return self.db.execute(sql, params).fetchone() is None

    # /     /     >---- رسالة إيضاحية عند محاولة تعيين رئيس لقسم مشغول
    def _hod_occupied_message(self, department_id) -> str:
        hod = get_current_hod(self.db, department_id)
        current = f' ({hod["name"]})' if hod else ''
        return f'هذا القسم لديه رئيس قسم بالفعل{current} — يتم استبدال الرئيس من ملف الأستاذ'

    # /     /     >---- إنشاء ملف أستاذ مرتبط بالمستخدم (مع منع تكرار الرقم الأكاديمي)
    def _create_teacher_profile(self, user_id: int, data: Dict[str, Any]) -> None:
        from utils.text import normalize_academic_number

        # /     /     >---- حارس الهوية: نرفض إذا الرقم الأكاديمي موجود من قبل
        an = normalize_academic_number(data.get('academic_number'))
        if an and self._teacher_repo:
            existing = self._teacher_repo.find_by_academic_number(an)
            if existing:
                raise ValueError(
                    f"Cannot create duplicate teacher profile: "
                    f"academic_number '{an}' belongs to teacher "
                    f"id={existing[0]['id']} ({existing[0]['name']!r})"
                )

        rank_id = data.get('rank_id')
        if rank_id in (None, ''):
            rank_id = None
        self.db.execute(
            '''INSERT INTO teachers
               (name, email, phone, academic_number, specialization,
                department_id, rank_id, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (data.get('name') or '',
             data.get('email') or '',
             data.get('phone') or '',
             data.get('academic_number') or '',
             data.get('specialization') or '',
             data.get('department_id'),
             rank_id,
             user_id),
        )
        self.db.commit()

    # /     /     >---- تحديث ملف الأستاذ أو إنشاؤه إذا مازالش موجود
    def _update_teacher_profile(self, user_id: int, data: Dict[str, Any]) -> None:
        existing = self._repo.get_teacher_by_user(user_id)
        if existing:
            rank_id = data.get('rank_id')
            if rank_id in (None, ''):
                rank_id = None
            self.db.execute(
                '''UPDATE teachers SET
                     name = ?, email = ?, phone = ?, academic_number = ?,
                     specialization = ?, department_id = ?, rank_id = ?
                   WHERE id = ?''',
                (data.get('name') or '',
                 data.get('email') or '',
                 data.get('phone') or '',
                 data.get('academic_number') or '',
                 data.get('specialization') or '',
                 data.get('department_id'),
                 rank_id,
                 existing['id']),
            )
            self.db.commit()
        else:
            self._create_teacher_profile(user_id, data)

    # /     /     >---- إنشاء مستخدم مع تطبيق قواعد نموذج الأدوار
    def create_user_with_profile(self, username: str, password: str, role: str,
                                  department_id, email: str, label: str,
                                  **extra) -> int:
        """Create a user, applying the role model rules.

        - Teacher role also creates the linked teacher profile.
        - Head of Department must pick an academic department without an HOD.
        - Only one primary office-manager account (``office_manager``) may exist.
        - Academic roles carry an academic department.
        - Administrative roles carry an administrative department.
        """
        department_id = self._force_academic_department(role, department_id)
        admin_dept_id = self._force_administrative_department(
            role, extra.get('administrative_department_id')
        )
        if (role == 'faculty_affairs'
                and username == _PRIMARY_OFFICE_MANAGER_USERNAME
                and self._primary_manager_exists()):
            raise ConflictError('يوجد حساب مدير المكتب الأساسي مسبقاً')
        if role == 'head_of_department':
            if department_id is None:
                raise ValidationError(message='يرجى اختيار القسم لرئيس القسم')
            if not self._hod_department_available(department_id):
                raise ConflictError(self._hod_occupied_message(department_id))

        user_id = self._repo.create_user({
            'username': username,
            'password': generate_password_hash(password),
            'role': role,
            'department_id': department_id,
            'administrative_department_id': admin_dept_id,
            'email': email or '',
            'label': label or '',
            'phone': extra.get('phone') or '',
        })
        if role == 'teacher':
            self._create_teacher_profile(user_id, {
                'name': label or '',
                'email': email or '',
                'phone': extra.get('phone') or '',
                'academic_number': extra.get('academic_number') or '',
                'specialization': extra.get('specialization') or '',
                'department_id': department_id,
                'rank_id': extra.get('rank_id'),
            })
        return user_id

    # /     /     >---- تحديث مستخدم مع تطبيق قواعد نموذج الأدوار
    def update_user_with_profile(self, user_id: int, username: str, role: str, department_id,
                                  email: str, label: str, phone: str = '',
                                  password: str = None,
                                  **extra) -> None:
        """Update a user, applying the role model rules.

        Mirrors :meth:`create_user_with_profile`; a role switch away from
        ``teacher`` keeps the linked teacher profile so the teacher record is
        never lost or duplicated.
        """
        existing = self._repo.find_by_id(user_id)
        if not existing:
            return
        new_role = role or existing['role']
        department_id = self._force_academic_department(new_role, department_id)
        admin_dept_id = self._force_administrative_department(
            new_role, extra.get('administrative_department_id')
        )
        if (new_role == 'faculty_affairs'
                and username == _PRIMARY_OFFICE_MANAGER_USERNAME
                and self._primary_manager_exists(exclude_user_id=user_id)):
            raise ConflictError('يوجد حساب مدير المكتب الأساسي مسبقاً')
        if (existing['role'] == 'faculty_affairs'
                and existing['username'] == _PRIMARY_OFFICE_MANAGER_USERNAME
                and new_role != 'faculty_affairs'):
            raise ProtectedAccountError('لا يمكن تغيير دور حساب مدير المكتب الأساسي')
        if new_role == 'head_of_department':
            if department_id is None:
                raise ValidationError(message='يرجى اختيار القسم لرئيس القسم')
            if not self._hod_department_available(department_id, exclude_user_id=user_id):
                raise ConflictError(self._hod_occupied_message(department_id))

        data = {
            'username': username or existing['username'],
            'role': new_role,
            'department_id': department_id,
            'administrative_department_id': admin_dept_id,
            'email': email or '',
            'label': label or '',
            'phone': phone or '',
        }
        if password:
            data['password'] = generate_password_hash(password)
        self._repo.update_user(user_id, data)

        if new_role == 'teacher':
            self._update_teacher_profile(user_id, {
                'name': label or '',
                'email': email or '',
                'phone': extra.get('phone') or '',
                'academic_number': extra.get('academic_number') or '',
                'specialization': extra.get('specialization') or '',
                'department_id': department_id,
                'rank_id': extra.get('rank_id'),
            })
        # /     /     >---- نحافظ على ملف الأستاذ مرتبطاً حتى لو تبدّل الدور

    def username_exists(self, username: str) -> bool:
        return self._repo.username_exists(username)

    # /     /     >---- تغيير الثيم (فاتح/داكن/ملوّن)
    def update_theme(self, user_id: int, theme: str) -> bool:
        if theme not in ('light', 'dark', 'colorful'):
            return False
        self._repo.update_theme(user_id, theme)
        return True


# /     /     >---- دوال مستوى الوحدة المحافظة على التوافق مع المسارات القديمة
# /     /     >---- الكود الجديد يحقن الخدمة عبر g.container


def authenticate(db, username, password, remember, session_dict):
    from flask_db import get_db
    from database.repositories.user_repository import UserRepository
    repo = UserRepository(db)
    svc = UserService(db, repo)
    return svc.authenticate(username, password, remember, session_dict)


def create_password_reset(db, username):
    from database.repositories.user_repository import UserRepository
    repo = UserRepository(db)
    svc = UserService(db, repo)
    return svc.create_password_reset(username)


def validate_reset_token(db, token):
    from database.repositories.user_repository import UserRepository
    repo = UserRepository(db)
    return repo.find_valid_reset_token(token)


def reset_password(db, row, password):
    from database.repositories.user_repository import UserRepository
    repo = UserRepository(db)
    svc = UserService(db, repo)
    svc.reset_password(row, password)


def change_user_password(db, user_id, new_password):
    from database.repositories.user_repository import UserRepository
    repo = UserRepository(db)
    svc = UserService(db, repo)
    svc.change_user_password(user_id, new_password)


def get_user_by_id(db, user_id):
    from database.repositories.user_repository import UserRepository
    return UserRepository(db).find_by_id(user_id)


def get_user_profile(db, user_id):
    from database.repositories.user_repository import UserRepository
    repo = UserRepository(db)
    svc = UserService(db, repo)
    return svc.get_user_profile(user_id)


def list_users(db, search, page):
    from database.repositories.user_repository import UserRepository
    repo = UserRepository(db)
    svc = UserService(db, repo)
    return svc.list_users(search, page)


def get_all_departments(db):
    from database.repositories.user_repository import UserRepository
    return UserRepository(db).list_visible_departments()


def get_departments_for_role(db, role):
    from database.repositories.department_repository import DepartmentRepository
    return DepartmentRepository(db).list_academic()


def create_user(db, username, password, role, department_id, email, label):
    from database.repositories.user_repository import UserRepository
    repo = UserRepository(db)
    svc = UserService(db, repo)
    svc.create_user(username, password, role, department_id, email, label)


def create_user_with_profile(db, username, password, role, department_id,
                             email, label, **extra):
    from database.repositories.user_repository import UserRepository
    repo = UserRepository(db)
    svc = UserService(db, repo)
    return svc.create_user_with_profile(
        username, password, role, department_id, email, label, **extra
    )


def update_user_with_profile(db, user_id, username, role, department_id, email, label,
                             phone='', password=None, **extra):
    from database.repositories.user_repository import UserRepository
    repo = UserRepository(db)
    svc = UserService(db, repo)
    svc.update_user_with_profile(
        user_id, username, role, department_id, email, label, phone, password, **extra
    )


def update_user(db, id, role, department_id, email, label, password=None):
    from database.repositories.user_repository import UserRepository
    repo = UserRepository(db)
    svc = UserService(db, repo)
    svc.update_user(id, role, department_id, email, label, password)


def delete_user(db, id):
    from database.repositories.user_repository import UserRepository
    svc = UserService(db, UserRepository(db))
    svc.delete_user(id)


def username_exists(db, username):
    from database.repositories.user_repository import UserRepository
    return UserRepository(db).username_exists(username)


def update_theme(db, user_id, theme):
    from database.repositories.user_repository import UserRepository
    repo = UserRepository(db)
    svc = UserService(db, repo)
    return svc.update_theme(user_id, theme)