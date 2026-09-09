from __future__ import annotations

from typing import Any, Dict, List, Optional

from database.repositories.base_repository import BaseRepository


class CourseRepository(BaseRepository):
    table = 'courses'

    def find_by_id(self, course_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT * FROM courses WHERE id = ?', (course_id,)
        ).fetchone()
        return dict(row) if row else None

    def find_by_name(self, course_id: int) -> Optional[str]:
        row = self.db.execute(
            'SELECT name FROM courses WHERE id = ?', (course_id,)
        ).fetchone()
        return row['name'] if row else None

    def list_courses(self, where_clause: str, params: list,
                     dept_filter_clause: str = '',
                     page: int = 1, per_page: int = 20) -> tuple:
        base = (
            f'SELECT DISTINCT c.* FROM courses c {dept_filter_clause} '
            f'WHERE {where_clause} ORDER BY c.name'
        )
        return self.paginate(base, params, page, per_page)

    def list_visible_departments(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            'SELECT * FROM departments WHERE hidden = 0 AND deleted_at IS NULL ORDER BY name'
        ).fetchall()]

    def create(self, data: Dict[str, Any]) -> int:
        self.db.execute(
            'INSERT INTO courses (code, name, theoretical_hours, practical_hours, '
            'total_hours, icon, notes, year, semester) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (data['code'], data['name'], data['theoretical_hours'],
             data['practical_hours'], data['total_hours'],
             data['icon'], data['notes'], data.get('year'), data.get('semester')),
        )
        self.db.commit()
        return self.db.execute('SELECT last_insert_rowid()').fetchone()[0]

    def update(self, course_id: int, data: Dict[str, Any]) -> None:
        self.db.execute(
            'UPDATE courses SET code=?, name=?, theoretical_hours=?, '
            'practical_hours=?, total_hours=?, icon=?, notes=?, year=?, semester=? WHERE id=?',
            (data['code'], data['name'], data['theoretical_hours'],
             data['practical_hours'], data['total_hours'],
             data['icon'], data['notes'], data.get('year'), data.get('semester'),
             course_id),
        )
        self.db.commit()

    def get_detail(self, course_id: int) -> Optional[Dict[str, Any]]:
        c = self.db.execute(
            'SELECT * FROM courses WHERE id = ?', (course_id,)
        ).fetchone()
        if not c:
            return None
        departments = self.db.execute(
            'SELECT d.id, d.name FROM course_departments cd '
            'JOIN departments d ON cd.department_id = d.id '
            'WHERE cd.course_id = ?', (course_id,)
        ).fetchall()
        prerequisites = self.db.execute(
            'SELECT p.id, p.code, p.name FROM course_prerequisites cp '
            'JOIN courses p ON cp.prerequisite_id = p.id '
            'WHERE cp.course_id = ?', (course_id,)
        ).fetchall()
        return {
            'course': dict(c),
            'departments': [dict(d) for d in departments],
            'prerequisites': [dict(p) for p in prerequisites],
        }

    def get_edit_form_data(self, course_id: int) -> Dict[str, Any]:
        departments = self.list_visible_departments()
        courses = [dict(r) for r in self.db.execute(
            'SELECT id, code, name FROM courses WHERE deleted_at IS NULL AND id != ? ORDER BY name',
            (course_id,),
        ).fetchall()]
        prereq_ids = [r['prerequisite_id'] for r in self.db.execute(
            'SELECT prerequisite_id FROM course_prerequisites WHERE course_id = ?',
            (course_id,),
        ).fetchall()]
        current_dept_ids = [r['department_id'] for r in self.db.execute(
            'SELECT department_id FROM course_departments WHERE course_id = ?',
            (course_id,),
        ).fetchall()]
        return {
            'departments': departments,
            'courses': courses,
            'prereq_ids': prereq_ids,
            'current_dept_ids': current_dept_ids,
        }

    def get_dept_mapping(self, course_ids: list) -> Dict[int, List[str]]:
        mapping: Dict[int, List[str]] = {}
        if not course_ids:
            return mapping
        placeholders = ','.join('?' for _ in course_ids)
        rows = self.db.execute(
            f'SELECT cd.course_id, d.name FROM course_departments cd '
            f'JOIN departments d ON cd.department_id = d.id '
            f'WHERE cd.course_id IN ({placeholders})',
            course_ids,
        ).fetchall()
        for r in rows:
            mapping.setdefault(r['course_id'], []).append(r['name'])
        return mapping

    def get_dept_id_mapping(self, course_ids: list) -> Dict[int, List[int]]:
        mapping: Dict[int, List[int]] = {}
        if not course_ids:
            return mapping
        placeholders = ','.join('?' for _ in course_ids)
        rows = self.db.execute(
            f'SELECT course_id, department_id FROM course_departments '
            f'WHERE course_id IN ({placeholders})',
            course_ids,
        ).fetchall()
        for r in rows:
            mapping.setdefault(r['course_id'], []).append(r['department_id'])
        return mapping

    def get_dept_placement_mapping(self, course_ids: list) -> Dict[int, Dict[int, int]]:
        """Map course_id -> {department_id: semester} for per-department placement."""
        mapping: Dict[int, Dict[int, int]] = {}
        if not course_ids:
            return mapping
        placeholders = ','.join('?' for _ in course_ids)
        rows = self.db.execute(
            f'SELECT course_id, department_id, semester FROM course_departments '
            f'WHERE course_id IN ({placeholders})',
            course_ids,
        ).fetchall()
        for r in rows:
            mapping.setdefault(r['course_id'], {})[r['department_id']] = (
                r['semester'] or 1
            )
        return mapping

    def set_departments(self, course_id: int, placements: list,
                        default_semester: int = 1) -> None:
        """Set the course's department placements (per-department semester).

        ``placements`` may be either a plain list of department IDs (kept for
        backward compatibility) or a list of dicts ``{department_id, semester}``.
        When a department is passed without a semester, ``default_semester`` is
        used (for API/create callers that only send department IDs).
        """
        course_sem = self.db.execute(
            'SELECT semester FROM courses WHERE id = ?', (course_id,)
        ).fetchone()
        course_sem = course_sem['semester'] if course_sem else None

        # Normalise to a list of (dept_id, semester) pairs.
        items = []
        for p in placements:
            if isinstance(p, dict):
                items.append((
                    int(p.get('department_id')),
                    p.get('semester'),
                ))
            else:
                items.append((int(p), None))

        self.db.execute(
            'DELETE FROM course_departments WHERE course_id = ?', (course_id,)
        )
        for dept_id, sem in items:
            if sem is None:
                sem = course_sem if course_sem is not None else default_semester
            sem = int(sem)
            if sem < 1:
                sem = default_semester
            self.db.execute(
                'INSERT INTO course_departments (course_id, department_id, semester) '
                'VALUES (?, ?, ?)',
                (course_id, dept_id, sem),
            )
        # Keep the owner department (courses.department_id) in sync: when the
        # current owner is no longer among the placements it was unchecked
        # from the course, so it must not linger in that department's plan.
        owner_row = self.db.execute(
            'SELECT department_id FROM courses WHERE id = ?', (course_id,)
        ).fetchone()
        old_owner = owner_row['department_id'] if owner_row else None
        if old_owner is not None:
            dept_ids = [d for d, _ in items]
            if old_owner not in dept_ids:
                new_owner = dept_ids[0] if dept_ids else None
                self.db.execute(
                    'UPDATE courses SET department_id = ? WHERE id = ?',
                    (new_owner, course_id),
                )
        self.db.commit()

    def set_prerequisites(self, course_id: int, prerequisite_id: int = None) -> None:
        self.db.execute(
            'DELETE FROM course_prerequisites WHERE course_id = ?', (course_id,)
        )
        if prerequisite_id:
            self.db.execute(
                'INSERT INTO course_prerequisites (course_id, prerequisite_id) VALUES (?, ?)',
                (course_id, prerequisite_id),
            )
        self.db.commit()

    def get_create_form_data(self) -> Dict[str, Any]:
        departments = self.list_visible_departments()
        courses = [dict(r) for r in self.db.execute(
            'SELECT id, code, name FROM courses WHERE deleted_at IS NULL ORDER BY name'
        ).fetchall()]
        course_ids = [c['id'] for c in courses]
        course_dept_map = self.get_dept_id_mapping(course_ids) if course_ids else {}
        return {'departments': departments, 'courses': courses, 'course_dept_map': course_dept_map}

