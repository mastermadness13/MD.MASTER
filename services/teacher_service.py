"""Teacher service — CRUD, credentials.

Uses ``TeacherRepository`` for data access.  Module-level functions are kept
for backward compatibility with existing routes.
"""

from __future__ import annotations

import logging
import re
import secrets
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

from flask import session
from werkzeug.security import generate_password_hash

from core.constants import SEMESTER_LABELS
from core.constants.seasons import (
    LEGACY_PERIOD_CODE,
    LEGACY_PERIOD_LABEL,
    normalize_period_code,
    period_label,
    period_sort_key,
)
from database.constants import SOFT_DELETE_TABLES
from utils.format import teaching_semester_label

logger = logging.getLogger(__name__)


def _generate_username(name: str) -> str:
    parts = name.strip().split()
    if len(parts) >= 2:
        base = parts[0][0] + '.' + parts[1]
    else:
        base = parts[0] if parts else 'teacher'
    return re.sub(r'[^\w.]', '', base.lower())


def _generate_password() -> str:
    return secrets.token_urlsafe(8)


class TeacherService:
    """Class-based teacher service with repository injection."""

    def __init__(self, db=None, teacher_repo=None, user_repo=None,
                 timetable_repo=None, course_repo=None):
        self.db = db
        self._repo = teacher_repo
        self._user_repo = user_repo
        self._timetable_repo = timetable_repo
        self._course_repo = course_repo

    def list_teachers(self, role, user_data, search, dept_filter, page=1):
        where, params, dept_filter = self._build_where(role, user_data, search, dept_filter)
        where_clause = ' AND '.join(where) if where else '1=1'
        rows, total, pg, pp = self._repo.list_teachers(where_clause, params, page)
        departments = self._repo.list_visible_departments()
        return rows, total, pg, pp, departments, dept_filter

    def get_form_lookups(self) -> Dict[str, list]:
        return self._repo.get_form_lookups()

    def create_teacher(self, data: Dict[str, Any], department_ids=None,
                       additional_roles=None) -> Dict[str, str]:
        from utils.text import normalize_academic_number, normalize_arabic_name

        an = normalize_academic_number(data.get('academic_number'))
        if an:
            existing = self._repo.find_by_academic_number(an)
            if existing:
                raise ValueError(
                    "Teacher with academic_number '"
                    f"{an}"
                    "' already exists (id="
                    f"{existing[0]['id']}"
                    ", name="
                    f"{existing[0]['name']!r}"
                    ')'
                )

        norm_name = normalize_arabic_name(data.get('name', ''))
        if norm_name:
            candidates = self._repo.find_by_name_normalized(norm_name)
            if candidates:
                logger.warning(
                    "Creating teacher '%s' — %d existing teacher(s) share the same normalized name: %s",
                    data.get('name'),
                    len(candidates),
                    [c['id'] for c in candidates],
                )

        teacher_id = self._repo.create(data)
        if department_ids:
            self.db.executemany(
                'INSERT OR IGNORE INTO teacher_departments (teacher_id, department_id) VALUES (?, ?)',
                [(teacher_id, did) for did in department_ids],
            )
            self.db.commit()

        username = _generate_username(data['name'])
        password = _generate_password()
        if self._user_repo and self._user_repo.username_exists(username):
            username = f"{username}.{teacher_id}"
        self.db.execute(
            'INSERT INTO users (username, password, role, label, department_id, email) VALUES (?, ?, ?, ?, ?, ?)',
            (
                username,
                generate_password_hash(password),
                'teacher',
                data['name'],
                data['department_id'],
                data['email'],
            ),
        )
        user_id = self.db.execute('SELECT last_insert_rowid()').fetchone()[0]
        self._repo.link_user(teacher_id, user_id)
        granted = ['teacher'] + [r for r in (additional_roles or []) if r and r != 'teacher']
        try:
            self._user_repo.set_user_roles(user_id, granted)
        except AttributeError:
            pass
        return {
            'id': teacher_id,
            'username': username,
            'password': password,
        }

    def get_teacher(self, teacher_id: int) -> Optional[Dict]:
        return self._repo.find_by_id(teacher_id)

    def update_teacher(self, teacher_id: int, data: Dict[str, Any]) -> None:
        self._repo.update(teacher_id, data)

    def get_teacher_granted_roles(self, teacher_id: int) -> list:
        """Return the granted role set for a teacher's linked user account."""
        teacher = self._repo.find_by_id(teacher_id)
        if not teacher or not teacher.get('user_id'):
            return []
        roles = self._user_repo.find_roles_by_user(teacher['user_id'])
        if roles:
            return roles
        return [teacher.get('role') or 'teacher']

    def set_teacher_extra_roles(self, teacher_id: int, additional_roles) -> None:
        """Refresh the linked user's granted roles (landing 'teacher' + extras)."""
        teacher = self._repo.find_by_id(teacher_id)
        if not teacher or not teacher.get('user_id'):
            return None
        granted = ['teacher'] + [r for r in (additional_roles or []) if r and r != 'teacher']
        self._user_repo.set_user_roles(teacher['user_id'], granted)

    def reset_teacher_password(self, teacher_id: int) -> Optional[str]:
        teacher = self._repo.find_by_id(teacher_id)
        if not teacher or not teacher.get('user_id'):
            return None
        new_password = _generate_password()
        self.db.execute(
            'UPDATE users SET password = ? WHERE id = ?',
            (generate_password_hash(new_password), teacher['user_id']),
        )
        self.db.commit()
        return new_password

    def update_teacher_credentials(self, teacher_id: int, new_username=None,
                                   new_password=None) -> bool:
        teacher = self._repo.find_by_id(teacher_id)
        if not teacher or not teacher.get('user_id'):
            return False
        if new_username:
            self.db.execute(
                'UPDATE users SET username = ? WHERE id = ?',
                (new_username, teacher['user_id']),
            )
        if new_password:
            self.db.execute(
                'UPDATE users SET password = ? WHERE id = ?',
                (generate_password_hash(new_password), teacher['user_id']),
            )
        self.db.commit()
        return True

    def get_teacher_detail(self, teacher_id: int) -> Optional[Tuple]:
        t = self._repo.find_detail(teacher_id)
        if not t:
            return None
        courses = self._repo.get_courses_for_teacher(teacher_id)
        timetable_count = self._repo.count_timetable_entries(teacher_id)
        stats = {
            'course_count': len(courses),
            'timetable_count': timetable_count,
            'hours_count': self._repo.count_teaching_hours(teacher_id),
        }
        return t, courses, stats

    def _semester_label(self, department_id: Optional[int], sem: int) -> str:
        """Semester display name from the academic record when available."""
        if department_id is not None:
            try:
                row = self.db.execute(
                    'SELECT name FROM semesters WHERE department_id = ? AND semester_number = ? AND is_active = 1 AND deleted_at IS NULL AND name IS NOT NULL AND name != "" LIMIT 1',
                    (department_id, sem),
                ).fetchone()
                if row and row['name']:
                    return row['name']
            except Exception:
                logger.debug('Failed to look up semester name for dept=%s sem=%s', department_id, sem)
        return teaching_semester_label(sem)

    def _period_date_hint(self, code: str) -> str:
        """Approximate time window shown next to a teaching period."""
        if code == LEGACY_PERIOD_CODE:
            try:
                row = self.db.execute(
                    "SELECT MIN(created_at) AS d FROM timetable_versions WHERE COALESCE(semester_code, '') LIKE 'migrated%'",
                ).fetchone()
                if row and row['d']:
                    y, m, day = str(row['d'])[:10].split('-')
                    return 'مستوردة بتاريخ ' + '{}/{}/{}'.format(day, m, y)
            except Exception:
                logger.debug('Failed to look up legacy period date hint')
            return ''
        sc = str(code or '')
        if sc.startswith('fall_') and sc[5:].isdigit():
            y = int(sc[5:])
            return 'سبتمبر {} – يناير {}'.format(y, y + 1)
        if sc.startswith('spring_') and sc[7:].isdigit():
            y = int(sc[7:])
            return 'فبراير {} – يونيو {}'.format(y, y)
        return ''

    def get_teaching_record(self, teacher_id: int, year_filter: str = '',
                            semester_filter: int = None) -> Dict:
        """Build the historical teaching record grouped by year → semester."""
        rows = self._repo.get_teaching_record(teacher_id, year_filter, semester_filter)
        years = self._repo.get_teaching_years(teacher_id)
        semester_nums = self._repo.get_teaching_semesters(teacher_id)

        groups = OrderedDict()
        for r in rows:
            sem_code = normalize_period_code(r['semester_code']) or 'غير محدد'
            sem = r['semester']
            groups.setdefault(sem_code, OrderedDict()).setdefault(sem, []).append(r)

        years_data = []
        for sem_code, sem_map in groups.items():
            year_total = 0
            sem_list = []
            for sem, entries in sem_map.items():
                sem_total = sum(e['hours'] or 0 for e in entries)
                year_total += sem_total
                sem_list.append({
                    'number': sem,
                    'label': self._semester_label(entries[0].get('department_id'), sem),
                    'entries': entries,
                    'total_hours': sem_total,
                    'course_count': len(entries),
                })
            display_name = ''
            if sem_code != LEGACY_PERIOD_CODE:
                try:
                    row = self.db.execute(
                        'SELECT name_ar FROM semesters WHERE code = ? LIMIT 1',
                        (sem_code,),
                    ).fetchone()
                    if row and row['name_ar']:
                        display_name = row['name_ar']
                except Exception:
                    logger.debug('Failed to look up semester display name for code=%s', sem_code)
                if not display_name:
                    display_name = period_label(sem_code)
            else:
                display_name = LEGACY_PERIOD_LABEL
            years_data.append({
                'year': display_name,
                'semester_code': sem_code,
                'is_legacy': sem_code == LEGACY_PERIOD_CODE,
                'date_hint': self._period_date_hint(sem_code),
                'semesters': sem_list,
                'total_hours': year_total,
            })

        years_data.sort(key=lambda g: period_sort_key(g['semester_code']), reverse=True)

        for group in years_data:
            if not group.get('year'):
                group['year'] = period_label(group['semester_code']) or LEGACY_PERIOD_LABEL
            entries = [e for sem in group['semesters'] for e in sem['entries']]
            semesters = {e['semester'] for e in entries if e.get('semester')}
            group['course_count'] = len(entries)
            group['min_semester'] = min(semesters) if semesters else None
            group['missing_hours_total'] = sum(e.get('missing_hours') or 0 for e in entries)

        periods = [
            {
                'code': g['semester_code'],
                'label': g['year'],
                'course_count': g['course_count'],
                'total_hours': g['total_hours'],
                'is_legacy': g.get('is_legacy', False),
                'date_hint': g.get('date_hint', ''),
            }
            for g in years_data
        ]
        semesters = [{'number': s, 'label': teaching_semester_label(s)} for s in semester_nums]
        return {
            'years_data': years_data,
            'years': years,
            'periods': periods,
            'semesters': semesters,
            'year_filter': year_filter,
            'semester_filter': semester_filter,
            'total_hours': sum(r['hours'] or 0 for r in rows),
            'missing_hours_count': sum(1 for r in rows if not r['hours']),
        }

    def get_teaching_record_filtered(self, teacher_id: int, semester: int,
                                     semester_code: str, semester_display: str = '',
                                     department_id: int = None) -> Dict:
        """Build a filtered teaching record for one teacher + year level + period."""
        entries = self._repo.get_teaching_record_filtered(
            teacher_id, semester, semester_code, department_id=department_id,
        )
        total_hours = sum(e['hours'] or 0 for e in entries)
        sem_label = SEMESTER_LABELS.get(semester, 'الفصل {}'.format(semester))

        dept_map = {}
        for e in entries:
            dn = (e.get('department_name') or '').strip()
            if not dn:
                dn = 'غير محدد'
            if dn not in dept_map:
                dept_map[dn] = {'name': dn, 'entries': [], 'subtotal_hours': 0}
            dept_map[dn]['entries'].append(e)
            dept_map[dn]['subtotal_hours'] += e.get('hours') or 0

        return {
            'departments': list(dept_map.values()),
            'total_hours': total_hours,
            'missing_hours_count': sum(1 for e in entries if not e.get('hours')),
            'filter': {
                'semester': semester,
                'semester_label': sem_label,
                'semester_code': semester_code,
                'semester_display': semester_display or semester_code,
                'department_names': [d['name'] for d in dept_map.values()],
            },
        }

    def teacher_delete(self, teacher_id: int, history_callback=None) -> None:
        from core.exceptions import ProtectedAccountError
        from database.repositories.user_repository import UserRepository
        row = self.db.execute(
            'SELECT user_id FROM teachers WHERE id = ?',
            (teacher_id,),
        ).fetchone()
        if row and row['user_id']:
            from services.user_service import UserService
            svc = UserService(self.db, UserRepository(self.db))
            if svc.is_protected_user(row['user_id']):
                raise ProtectedAccountError()
        self.db.execute(
            'UPDATE teachers SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?',
            (teacher_id,),
        )
        if history_callback:
            history_callback(self.db)
        self.db.commit()

    def teacher_restore(self, teacher_id: int) -> None:
        self.db.execute(
            'UPDATE teachers SET deleted_at = NULL WHERE id = ?',
            (teacher_id,),
        )
        self.db.commit()

    def teacher_hard_delete(self, teacher_id: int) -> None:
        from core.exceptions import ProtectedAccountError
        row = self.db.execute(
            'SELECT user_id FROM teachers WHERE id = ?',
            (teacher_id,),
        ).fetchone()
        if row and row['user_id']:
            from services.user_service import UserService
            from database.repositories.user_repository import UserRepository
            svc = UserService(self.db, UserRepository(self.db))
            if svc.is_protected_user(row['user_id']):
                raise ProtectedAccountError()
        self.db.execute(
            'DELETE FROM teachers WHERE id = ?',
            (teacher_id,),
        )
        self.db.commit()


    def _build_where(self, role, user_data, search, dept_filter):
        where = ['t.deleted_at IS NULL']
        params = []
        if role == 'head_of_department':
            user_dept_id = session.get('hod_department_id')
            if user_dept_id:
                dept_filter = str(user_dept_id)
                where.append('EXISTS (SELECT 1 FROM teacher_departments tdx WHERE tdx.teacher_id = t.id AND tdx.department_id = ?)')
                params.append(user_dept_id)
        elif dept_filter:
            where.append('EXISTS (SELECT 1 FROM teacher_departments tdx WHERE tdx.teacher_id = t.id AND tdx.department_id = ?)')
            params.append(dept_filter)
        if search:
            where.append('(t.name LIKE ? OR t.email LIKE ? OR t.academic_number LIKE ?)')
            params.extend([f'%{search}%'] * 3)
        return where, params, dept_filter


def teacher_where_clause(role, user_data, search, dept_filter):
    where = ['t.deleted_at IS NULL']
    params = []
    if role == 'head_of_department':
        user_dept_id = session.get('hod_department_id')
        if user_dept_id:
            dept_filter = str(user_dept_id)
            where.append('EXISTS (SELECT 1 FROM teacher_departments tdx WHERE tdx.teacher_id = t.id AND tdx.department_id = ?)')
            params.append(user_dept_id)
    elif dept_filter:
        where.append('EXISTS (SELECT 1 FROM teacher_departments tdx WHERE tdx.teacher_id = t.id AND tdx.department_id = ?)')
        params.append(dept_filter)
    if search:
        where.append('(t.name LIKE ? OR t.email LIKE ? OR t.academic_number LIKE ?)')
        params.extend([f'%{search}%'] * 3)
    return where, params, dept_filter


def list_teachers(db, role, user_data, search, dept_filter, page):
    from utils.format import paginate
    from database.repositories.teacher_repository import TeacherRepository

    repo = TeacherRepository(db)
    where, params, dept_filter = teacher_where_clause(role, user_data, search, dept_filter)
    where_clause = ' AND '.join(where) if where else '1=1'
    query = (
        'SELECT t.*, d.name as dept_name, u.username as username FROM teachers t LEFT JOIN departments d ON t.department_id = d.id LEFT JOIN users u ON t.user_id = u.id WHERE '
        f'{where_clause}'
        ' ORDER BY t.name'
    )
    rows, total, pg, pp = paginate(query, params, page)
    departments = repo.list_visible_departments()
    return rows, total, pg, pp, departments, dept_filter


def get_form_lookups(db):
    from database.repositories.teacher_repository import TeacherRepository

    lookups = TeacherRepository(db).get_form_lookups()
    return (
        lookups['departments'],
        lookups['qualifications'],
        lookups['ranks'],
        lookups['classifications'],
        lookups['courses'],
        lookups['specializations'],
    )


def create_teacher(db, data, department_ids=None, additional_roles=None):
    from database.repositories.teacher_repository import TeacherRepository
    from database.repositories.user_repository import UserRepository

    repo = TeacherRepository(db)
    user_repo = UserRepository(db)
    svc = TeacherService(db, repo, user_repo)
    return svc.create_teacher(data, department_ids=department_ids, additional_roles=additional_roles)


def get_teacher(db, id):
    from database.repositories.teacher_repository import TeacherRepository
    return TeacherRepository(db).find_by_id(id)


def get_teacher_granted_roles(db, teacher_id):
    from database.repositories.teacher_repository import TeacherRepository
    from database.repositories.user_repository import UserRepository

    svc = TeacherService(db, TeacherRepository(db), UserRepository(db))
    return svc.get_teacher_granted_roles(teacher_id)


def set_teacher_extra_roles(db, teacher_id, additional_roles):
    from database.repositories.teacher_repository import TeacherRepository
    from database.repositories.user_repository import UserRepository

    svc = TeacherService(db, TeacherRepository(db), UserRepository(db))
    svc.set_teacher_extra_roles(teacher_id, additional_roles)


def update_teacher(db, id, data):
    from database.repositories.teacher_repository import TeacherRepository
    TeacherRepository(db).update(id, data)


def reset_teacher_password(db, teacher_id):
    from database.repositories.teacher_repository import TeacherRepository

    repo = TeacherRepository(db)
    svc = TeacherService(db, repo)
    return svc.reset_teacher_password(teacher_id)


def update_teacher_credentials(db, teacher_id, new_username=None, new_password=None):
    from database.repositories.teacher_repository import TeacherRepository

    repo = TeacherRepository(db)
    svc = TeacherService(db, repo)
    return svc.update_teacher_credentials(teacher_id, new_username, new_password)


def get_teacher_detail(db, id):
    from database.repositories.teacher_repository import TeacherRepository

    repo = TeacherRepository(db)
    svc = TeacherService(db, repo)
    return svc.get_teacher_detail(id)


def get_teaching_record(db, id, year_filter='', semester_filter=None):
    from database.repositories.teacher_repository import TeacherRepository

    repo = TeacherRepository(db)
    svc = TeacherService(db, repo)
    return svc.get_teaching_record(id, year_filter, semester_filter)


def get_teaching_record_filtered(db, teacher_id, semester, semester_code,
                                 semester_display='', department_id=None):
    from database.repositories.teacher_repository import TeacherRepository

    repo = TeacherRepository(db)
    svc = TeacherService(db, repo)
    return svc.get_teaching_record_filtered(
        teacher_id, semester, semester_code,
        semester_display=semester_display, department_id=department_id,
    )


def teacher_delete(db, id, history_callback):
    from services.base_service import soft_delete
    soft_delete(db, 'teachers', id, history_callback)


def teacher_restore(db, id):
    from services.base_service import restore
    restore(db, 'teachers', id)


def teacher_hard_delete(db, id):
    from services.base_service import hard_delete
    hard_delete(db, 'teachers', id)


