"""User service — authentication, CRUD, password management.

Refactored to accept repository injection while maintaining backward
compatibility with the existing module-level function API.
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

logger = logging.getLogger(__name__)

# Administrative roles never belong to an academic department.
# They may be assigned to an administrative unit (type='administrative').
_DEPARTMENTLESS_ROLES = frozenset({'super_admin', 'exam'})

# Administrative roles that carry an administrative unit (not academic dept).
_ADMINISTRATIVE_ROLES = frozenset({'faculty_affairs', 'research_development', 'exam'})

# Roles that carry an academic department.
_ACADEMIC_ROLES = frozenset({'teacher', 'head_of_department'})


class UserService:
    """Class-based user service with dependency injection."""

    def __init__(self, db, user_repository, teacher_repository=None):
        self.db = db
        self._repo = user_repository
        self._teacher_repo = teacher_repository

    # ── Super-admin protection ───────────────────────────────────────────

    def is_protected_user(self, user_id: int) -> bool:
        """Return True if the user is the main super-admin (by landing role or
        by an explicit ``super_admin`` entry in ``user_roles``).

        A protected account can never be deleted, deactivated,
        demoted, or stripped of its ``super_admin`` role, even via a direct
        service call (not just hidden UI buttons).
        """
        user = self._repo.find_by_id(user_id)
        if not user:
            return False
        if user.get('role') == 'super_admin':
            return True
        roles = self._repo.find_roles_by_user(user_id) or []
        return 'super_admin' in roles

    def _guard_against_destructive(self, user_id: int) -> None:
        if self.is_protected_user(user_id):
            raise ProtectedAccountError()

    # ── Authentication ───────────────────────────────────────────────────

    def authenticate(self, username: str, password: str, remember: bool,
                     session_dict: dict) -> Tuple[bool, Optional[Dict]]:
        user = self._repo.find_by_username(username)
        if user and check_password_hash(user['password'], password):
            if not user.get('is_active', 1):
                return False, None
            session_dict.clear()
            session_dict['permanent'] = bool(remember)
            session_dict['user_id'] = user['id']
            session_dict['username'] = user['username']
            # Multi-role: full granted role set + landing (highest priority) role.
            granted = self._repo.find_roles_by_user(user['id']) or [user['role']]
            if not granted:
                granted = [user['role']]
            session_dict['roles'] = granted
            session_dict['role'] = highest_priority_role(granted) or user['role']
            session_dict['label'] = user['label'] or ''
            # The single source of truth for the user→teacher link is
            # teachers.user_id (there is no users.teacher_id column).
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
            session_dict['administrative_department_id'] = user.get('administrative_department_id')
            session_dict['supervisor_admin_dept'] = user.get('supervisor_admin_dept', '')
            session_dict['theme'] = user['theme'] if user['theme'] else 'light'
            session_dict['_csrf_token'] = secrets.token_hex(32)

            from database.history import add_history
            add_history(
                self.db, 'login', 'user', user['id'],
                user['id'], user['username'],
                f'تسجيل دخول: {user["username"]}',
            )
            self.db.commit()
            return True, user
        return False, None

    # ── Password management ──────────────────────────────────────────────

    def create_password_reset(self, username: str) -> Optional[tuple]:
        user = self._repo.find_by_username_or_email(username)
        if user:
            token = secrets.token_urlsafe(48)
            expires = (datetime.now() + timedelta(hours=PASSWORD_RESET_EXPIRY_HOURS)).strftime(
                '%Y-%m-%d %H:%M:%S'
            )
            self._repo.create_password_reset(user['id'], token, expires)
            return token, user.get('email')
        return None

    def validate_reset_token(self, token: str) -> Optional[Dict]:
        return self._repo.find_valid_reset_token(token)

    def reset_password(self, row: Dict, password: str) -> None:
        self._repo.update_password(row['user_id'], generate_password_hash(password))
        self._repo.mark_reset_used(row['id'])

    def change_user_password(self, user_id: int, new_password: str) -> None:
        self._repo.update_password(user_id, generate_password_hash(new_password))

    # ── User CRUD ────────────────────────────────────────────────────────

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        return self._repo.find_by_id(user_id)

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

    def set_user_active(self, user_id: int, active: bool) -> None:
        """Enable/disable a user account (soft disable via ``is_active``).

        A protected super-admin can never be deactivated.
        """
        if not active:
            self._guard_against_destructive(user_id)
        self._repo.set_user_active(user_id, bool(active))

    def set_user_roles(self, user_id: int, roles) -> None:
        """Replace the user's granted role set stored in ``user_roles``.

        Refuses to strip ``super_admin`` from a protected account.
        """
        if self.is_protected_user(user_id) and 'super_admin' not in (roles or []):
            raise ProtectedAccountError()
        self._repo.set_user_roles(user_id, roles)

    # ── Role-aware create/update (merged user + profile flow) ───────────

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

    def _super_admin_exists(self, exclude_user_id: int = None) -> bool:
        sql = "SELECT 1 FROM users WHERE role = 'super_admin'"
        params = []
        if exclude_user_id is not None:
            sql += ' AND id != ?'
            params.append(exclude_user_id)
        return self.db.execute(sql, params).fetchone() is not None

    def _hod_department_available(self, department_id, exclude_user_id: int = None) -> bool:
        sql = ("SELECT 1 FROM users WHERE role = 'head_of_department' "
               'AND department_id = ?')
        params = [department_id]
        if exclude_user_id is not None:
            sql += ' AND id != ?'
            params.append(exclude_user_id)
        return self.db.execute(sql, params).fetchone() is None

    def _create_teacher_profile(self, user_id: int, data: Dict[str, Any]) -> None:
        from utils.text import normalize_academic_number

        # Stable-identity guard: reject if academic_number already exists
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

    def create_user_with_profile(self, username: str, password: str, role: str,
                                  department_id, email: str, label: str,
                                  **extra) -> int:
        """Create a user, applying the role model rules.

        - Teacher role also creates the linked teacher profile.
        - Head of Department must pick an academic department without an HOD.
        - Only one super_admin account may exist.
        - Academic roles carry an academic department.
        - Administrative roles carry an administrative department.
        - ``super_admin`` never carries a department.
        """
        department_id = self._force_academic_department(role, department_id)
        admin_dept_id = self._force_administrative_department(
            role, extra.get('administrative_department_id')
        )
        if role == 'super_admin' and self._super_admin_exists():
            raise ConflictError('يوجد حساب مدير النظام الأساسي مسبقاً')
        if role == 'head_of_department':
            if department_id is None:
                raise ValidationError(message='يرجى اختيار القسم لرئيس القسم')
            if not self._hod_department_available(department_id):
                raise ConflictError('هذا القسم لديه رئيس قسم بالفعل')

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
        if new_role == 'super_admin' and self._super_admin_exists(exclude_user_id=user_id):
            raise ConflictError('يوجد حساب مدير النظام الأساسي مسبقاً')
        if existing['role'] == 'super_admin' and new_role != 'super_admin':
            raise ProtectedAccountError('لا يمكن تغيير دور حساب مدير النظام الأساسي')
        if new_role == 'head_of_department':
            if department_id is None:
                raise ValidationError(message='يرجى اختيار القسم لرئيس القسم')
            if not self._hod_department_available(department_id, exclude_user_id=user_id):
                raise ConflictError('هذا القسم لديه رئيس قسم بالفعل')

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
        # else: keep the teacher profile linked to the same user.  A role
        # change (teacher → head of department, teacher → administrative role)
        # must NOT destroy the teacher record or create a duplicate when the
        # role is later reverted to teacher.

    def username_exists(self, username: str) -> bool:
        return self._repo.username_exists(username)

    def update_theme(self, user_id: int, theme: str) -> bool:
        if theme not in ('light', 'dark', 'colorful'):
            return False
        self._repo.update_theme(user_id, theme)
        return True


# ── Backward-compatible module-level API ──────────────────────────────────
# These thin wrappers allow existing route code to keep working unchanged.
# New code should inject the service via g.container instead.


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
