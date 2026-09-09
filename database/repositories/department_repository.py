from __future__ import annotations

from typing import Any, Dict, List, Optional

from database.repositories.base_repository import BaseRepository


class DepartmentRepository(BaseRepository):
    table = 'departments'

    def find_by_id(self, dept_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT * FROM departments WHERE id = ?', (dept_id,)
        ).fetchone()
        return dict(row) if row else None

    def find_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT * FROM departments WHERE name = ?', (name,)
        ).fetchone()
        return dict(row) if row else None

    def list_visible(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            'SELECT * FROM departments WHERE hidden = 0 AND deleted_at IS NULL ORDER BY name'
        ).fetchall()]

    def list_academic(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM departments WHERE type = 'academic' AND deleted_at IS NULL ORDER BY name"
        ).fetchall()]

    def list_administrative(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM departments WHERE type = 'administrative' AND deleted_at IS NULL ORDER BY name"
        ).fetchall()]

    def list_visible_with_majors(self) -> List[Dict[str, Any]]:
        depts = self.list_visible()
        if not depts:
            return depts
        ids = [d['id'] for d in depts]
        placeholders = ','.join('?' * len(ids))
        majors = self.db.execute(
            f'SELECT * FROM department_majors '
            f'WHERE department_id IN ({placeholders}) ORDER BY department_id, name',
            ids,
        ).fetchall()
        by_dept: Dict[int, List[Dict[str, Any]]] = {}
        for m in majors:
            by_dept.setdefault(m['department_id'], []).append(dict(m))
        for dept in depts:
            dept['major_list'] = by_dept.get(dept['id'], [])
        return depts

    def create(self, data: Dict[str, Any]) -> int:
        self.db.execute(
            'INSERT INTO departments (name, semesters, majors) VALUES (?, ?, ?)',
            (data['name'], data['semesters'], data['majors']),
        )
        self.db.commit()
        return self.db.execute('SELECT last_insert_rowid()').fetchone()[0]

    def update(self, dept_id: int, data: Dict[str, Any]) -> None:
        self.db.execute(
            'UPDATE departments SET name=?, semesters=?, majors=? WHERE id=?',
            (data['name'], data['semesters'], data['majors'], dept_id),
        )
        self.db.commit()


    # ── Majors ───────────────────────────────────────────────────────────

    def add_major(self, department_id: int, name: str) -> None:
        self.db.execute(
            'INSERT INTO department_majors (department_id, name) VALUES (?, ?)',
            (department_id, name),
        )
        self.db.commit()

    def delete_major(self, major_id: int, department_id: int) -> None:
        self.db.execute(
            'DELETE FROM department_majors WHERE id = ? AND department_id = ?',
            (major_id, department_id),
        )
        self.db.commit()

    def get_majors(self, department_id: int) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            'SELECT * FROM department_majors WHERE department_id = ? ORDER BY name',
            (department_id,),
        ).fetchall()]

    def count_majors(self, department_id: int) -> int:
        row = self.db.execute(
            'SELECT COUNT(*) as cnt FROM department_majors WHERE department_id = ?',
            (department_id,),
        ).fetchone()
        return row['cnt'] or 0

    def find_by_name_ignoring_deleted(self, name: str) -> Optional[Dict[str, Any]]:
        """Used by routes that look up department by text name (students dept)."""
        row = self.db.execute(
            'SELECT id, semesters FROM departments WHERE name = ?', (name,)
        ).fetchone()
        return dict(row) if row else None
