"""Department service — CRUD, majors management.

Uses ``DepartmentRepository`` for data access.  Module-level functions are kept
for backward compatibility with existing routes.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DepartmentService:
    """Class-based department service with repository injection."""

    def __init__(self, db, department_repo):
        self.db = db
        self._repo = department_repo

    def list_departments(self) -> List[Dict[str, Any]]:
        return self._repo.list_visible_with_majors()

    def get_all_departments(self) -> List[Dict[str, Any]]:
        return self._repo.list_visible()

    def list_academic_departments(self) -> List[Dict[str, Any]]:
        return self._repo.list_academic()

    def list_administrative_departments(self) -> List[Dict[str, Any]]:
        return self._repo.list_administrative()

    def department_exists_by_name(self, name: str) -> bool:
        return self._repo.find_by_name(name) is not None

    def create_department(self, name: str, semesters: int, majors: str) -> int:
        return self._repo.create({'name': name, 'semesters': semesters, 'majors': majors})

    def get_department(self, dept_id: int) -> Optional[Dict]:
        return self._repo.find_by_id(dept_id)

    def update_department(self, dept_id: int, name: str, semesters: int, majors: str) -> None:
        self._repo.update(dept_id, {'name': name, 'semesters': semesters, 'majors': majors})

    def department_delete(self, dept_id: int, history_callback=None) -> None:
        self._repo.soft_delete(dept_id)
        if history_callback:
            history_callback(self.db)

    def department_restore(self, dept_id: int) -> None:
        self._repo.restore(dept_id)

    def department_hard_delete(self, dept_id: int) -> None:
        self._repo.delete(dept_id)


    def add_major(self, department_id: int, name: str) -> None:
        self._repo.add_major(department_id, name)

    def delete_major(self, major_id: int, department_id: int) -> None:
        self._repo.delete_major(major_id, department_id)


# ── Backward-compatible module-level API ──────────────────────────────────

def list_departments(db):
    from database.repositories.department_repository import DepartmentRepository
    depts = DepartmentRepository(db).list_visible_with_majors()
    return depts


def get_all_departments(db):
    from database.repositories.department_repository import DepartmentRepository
    return DepartmentRepository(db).list_visible()


def list_academic_departments(db):
    from database.repositories.department_repository import DepartmentRepository
    return DepartmentRepository(db).list_academic()


def list_administrative_departments(db):
    from database.repositories.department_repository import DepartmentRepository
    return DepartmentRepository(db).list_administrative()


def department_exists_by_name(db, name):
    return db.execute('SELECT 1 FROM departments WHERE name = ?', (name,)).fetchone()


def create_department(db, name, semesters, majors):
    from database.repositories.department_repository import DepartmentRepository
    return DepartmentRepository(db).create({'name': name, 'semesters': semesters, 'majors': majors})


def get_department(db, id):
    return db.execute('SELECT * FROM departments WHERE id = ?', (id,)).fetchone()


def update_department(db, id, name, semesters, majors):
    from database.repositories.department_repository import DepartmentRepository
    DepartmentRepository(db).update(id, {'name': name, 'semesters': semesters, 'majors': majors})


def department_delete(db, id, history_callback):
    from services.base_service import soft_delete
    soft_delete(db, 'departments', id, history_callback)


def department_restore(db, id):
    from services.base_service import restore
    restore(db, 'departments', id)


def department_hard_delete(db, id):
    from services.base_service import hard_delete
    hard_delete(db, 'departments', id)



def list_academic_departments(db):
    from database.repositories.department_repository import DepartmentRepository
    return DepartmentRepository(db).list_academic()


def list_administrative_departments(db):
    from database.repositories.department_repository import DepartmentRepository
    return DepartmentRepository(db).list_administrative()


def add_major(db, department_id, name):
    from database.repositories.department_repository import DepartmentRepository
    DepartmentRepository(db).add_major(department_id, name)


def delete_major(db, major_id, department_id):
    from database.repositories.department_repository import DepartmentRepository
    DepartmentRepository(db).delete_major(major_id, department_id)
