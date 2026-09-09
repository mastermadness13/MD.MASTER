from __future__ import annotations

from typing import Any, Dict, List, Optional

from database.repositories.base_repository import BaseRepository


def semester_bounds(academic_year: str, semester: int):
    """(start_date, end_date) covering the chosen term.

    Understands codes like fall_2026 / spring_2027 as well as the
    legacy YYYY-YYYY academic-year format.
    """
    code = (academic_year or '').strip()
    if code.startswith('fall_'):
        y = code[len('fall_'):]
        return f'{y}-09-01', f'{y}-12-31'
    if code.startswith('spring_'):
        y = code[len('spring_'):]
        return f'{y}-01-01', f'{y}-06-30'
    parts = code.split('-')
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        start_year, end_year = parts[0], parts[1]
    else:
        start_year = end_year = code
    if semester == 1:
        return f'{start_year}-09-01', f'{start_year}-12-31'
    return f'{end_year}-01-01', f'{end_year}-06-30'


class FacultyPerformanceRepository(BaseRepository):
    table = 'teachers'

    # ── Teacher Profile ──────────────────────────────────────────

    def get_teacher_profile(self, teacher_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            '''SELECT t.id, t.name, t.email, t.phone, t.academic_number, t.national_id,
                      t.specialization, t.contract_date, t.tasks,
                      t.first_lecture_date, t.work_start_date,
                      s.name AS specialization_name,
                      d.name AS dept_name, t.department_id,
                      q.name_ar AS qual_name, t.qualification_id,
                      r.name_ar AS rank_name, t.rank_id,
                      c.name_ar AS class_name, t.classification_id,
                      u.username
               FROM teachers t
               LEFT JOIN departments d ON t.department_id = d.id
               LEFT JOIN specializations s ON t.specialization_id = s.id
               LEFT JOIN qualifications q ON t.qualification_id = q.id
               LEFT JOIN academic_ranks r ON t.rank_id = r.id
               LEFT JOIN classifications c ON t.classification_id = c.id
               LEFT JOIN users u ON t.user_id = u.id
               WHERE t.id = ? AND t.deleted_at IS NULL''',
            (teacher_id,),
        ).fetchone()
        return dict(row) if row else None

    # ── Timetable Entries (from teacher_taught_courses) ────────────

    def get_timetable_entries(
        self, teacher_id: int, department_ids, semester_code: str
    ) -> List[Dict[str, Any]]:
        """Entries of a teacher (across all given departments) for the selected
        semester_code, read from the teaching-assignment ledger."""
        ids = [int(d) for d in (department_ids or []) if d]
        if not ids:
            return []
        placeholders = ','.join('?' * len(ids))
        return [dict(r) for r in self.db.execute(
            f'''
            SELECT ttc.id, ttc.course_id, ttc.day,
                   ttc.start_time, ttc.end_time,
                   ttc.student_section, ttc.lecture_type,
                   COALESCE(ttc.hours, 0) AS manual_hours,
                   ttc.period,
                   (SELECT name FROM courses WHERE id = ttc.course_id) AS course_name,
                   (SELECT code FROM courses WHERE id = ttc.course_id) AS course_code,
                   (SELECT year FROM courses WHERE id = ttc.course_id) AS course_year,
                   (SELECT theoretical_hours FROM courses WHERE id = ttc.course_id) AS theoretical_hours,
                   (SELECT practical_hours FROM courses WHERE id = ttc.course_id) AS practical_hours,
                   (SELECT name FROM departments WHERE id = ttc.department_id) AS dept_name
            FROM teacher_taught_courses ttc
            WHERE ttc.teacher_id = ?
              AND ttc.department_id IN ({placeholders})
              AND ttc.semester_code = ?
            ORDER BY course_year, ttc.day, ttc.period
            ''',
            [teacher_id] + ids + [semester_code],
        ).fetchall()]

    # ── Course-level report (محضر مقرر) ───────────────────────────

    def get_course_by_id(self, course_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            '''SELECT c.id, c.name, c.code, c.year,
                      c.theoretical_hours, c.practical_hours,
                      d.name AS dept_name
               FROM courses c
               LEFT JOIN departments d ON c.department_id = d.id
               WHERE c.id = ? AND c.deleted_at IS NULL''',
            (course_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_course_teaching_entries(
        self, course_id: int, semester_code: str,
        department_id: int = None,
    ) -> List[Dict[str, Any]]:
        """All teaching assignments of one course across every teacher for the
        given semester_code, read from the teaching-assignment ledger."""
        extra = ''
        params: list = [course_id, semester_code]
        if department_id:
            extra = ' AND ttc.department_id = ?'
            params.append(department_id)
        return [dict(r) for r in self.db.execute(
            f'''
            SELECT ttc.id, ttc.day,
                   ttc.start_time, ttc.end_time,
                   ttc.student_section, ttc.lecture_type,
                   COALESCE(ttc.hours, 0) AS manual_hours,
                   ttc.period,
                   (SELECT name FROM teachers WHERE id = ttc.teacher_id
                    AND deleted_at IS NULL) AS teacher_name,
                   (SELECT r.name FROM teachers t
                    JOIN academic_ranks r ON t.rank_id = r.id
                    WHERE t.id = ttc.teacher_id) AS teacher_rank,
                   (SELECT name FROM courses WHERE id = ttc.course_id) AS course_name,
                   (SELECT code FROM courses WHERE id = ttc.course_id) AS course_code,
                   (SELECT year FROM courses WHERE id = ttc.course_id) AS course_year,
                   (SELECT theoretical_hours FROM courses WHERE id = ttc.course_id) AS theoretical_hours,
                   (SELECT practical_hours FROM courses WHERE id = ttc.course_id) AS practical_hours,
                   (SELECT name FROM departments WHERE id = ttc.department_id) AS dept_name
            FROM teacher_taught_courses ttc
            WHERE ttc.course_id = ?
              AND ttc.semester_code = ?
              {extra}
            ORDER BY teacher_name, ttc.day, ttc.period
            ''',
            params,
        ).fetchall()]

    # ── Workload Rules ───────────────────────────────────────────

    def get_workload_rules(self, rank_id: int, academic_year: str) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            '''SELECT category, min_hours, max_hours
               FROM faculty_workload_rules
               WHERE rank_id = ? AND academic_year = ? AND deleted_at IS NULL''',
            (rank_id, academic_year),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Research Activities ──────────────────────────────────────

    def get_research_activities(
        self, teacher_id: int, academic_year: str, semester: int
    ) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            '''SELECT id, activity_type, hours, notes
               FROM faculty_research_activities
               WHERE teacher_id = ? AND academic_year = ? AND semester = ?
               AND deleted_at IS NULL
               ORDER BY id''',
            (teacher_id, academic_year, semester),
        ).fetchall()
        return [dict(r) for r in rows]

    def upsert_research_activities(
        self, teacher_id: int, academic_year: str, semester: int,
        activities: List[Dict[str, Any]],
    ) -> None:
        self.db.execute(
            '''DELETE FROM faculty_research_activities
               WHERE teacher_id = ? AND academic_year = ? AND semester = ?''',
            (teacher_id, academic_year, semester),
        )
        for act in activities:
            activity_type = act.get('activity_type', '').strip()
            hours = int(act.get('hours', 0) or 0)
            notes = act.get('notes', '')
            if not activity_type:
                continue
            self.db.execute(
                '''INSERT INTO faculty_research_activities
                   (teacher_id, academic_year, semester, activity_type, hours, notes)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (teacher_id, academic_year, semester, activity_type, hours, notes),
            )
        self.db.commit()

    # ── Admin Assignments ────────────────────────────────────────

    def get_admin_assignments(
        self, teacher_id: int, academic_year: str, semester: int
    ) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            '''SELECT id, task_name, auto_hours, manual_hours,
                      assignment_date, start_date, end_date, notes
               FROM faculty_admin_assignments
               WHERE teacher_id = ? AND deleted_at IS NULL
               AND (academic_year = '' OR academic_year = ?)
               AND (semester = 0 OR semester = ?)''',
            (teacher_id, academic_year, semester),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d['hours_used'] = (d.get('auto_hours') or 0) + (d.get('manual_hours') or 0)
            result.append(d)
        return result

    def is_assignment_active_for_semester(
        self, start_date: str, end_date: Optional[str],
        academic_year: str, semester: int,
    ) -> bool:
        sem_start, sem_end = semester_bounds(academic_year, semester)
        if start_date > sem_end:
            return False
        if end_date and end_date < sem_start:
            return False
        return True

    def upsert_admin_assignments(
        self, teacher_id: int, assignments: List[Dict[str, Any]]
    ) -> None:
        self.db.execute(
            'DELETE FROM faculty_admin_assignments WHERE teacher_id = ?',
            (teacher_id,),
        )
        for a in assignments:
            task_name = a.get('task_name', '').strip()
            auto_hours = a.get('auto_hours')
            manual_hours = int(a.get('manual_hours', 0) or 0)
            assignment_date = a.get('assignment_date', '')
            start_date = a.get('start_date', '')
            end_date = a.get('end_date') or None
            notes = a.get('notes', '')
            academic_year = a.get('academic_year', '')
            sem = int(a.get('semester', 0) or 0)
            if not task_name or not start_date:
                continue
            self.db.execute(
                '''INSERT INTO faculty_admin_assignments
                   (teacher_id, task_name, auto_hours, manual_hours,
                    assignment_date, start_date, end_date, notes,
                    academic_year, semester)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (teacher_id, task_name, auto_hours, manual_hours,
                 assignment_date, start_date, end_date, notes,
                 academic_year, sem),
            )
        self.db.commit()

    def get_single_admin_assignment(
        self, teacher_id: int, task_name: str, academic_year: str, semester: int,
    ) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            '''SELECT id, task_name, assignment_date, start_date, end_date
               FROM faculty_admin_assignments
               WHERE teacher_id = ? AND task_name = ?
               AND academic_year = ? AND semester = ?
               AND deleted_at IS NULL
               LIMIT 1''',
            (teacher_id, task_name, academic_year, semester),
        ).fetchone()
        return dict(row) if row else None

    def upsert_single_admin_assignment(
        self, teacher_id: int, task_name: str, assignment_date: str,
        academic_year: str, semester: int,
    ) -> None:
        if not task_name:
            return
        existing = self.get_single_admin_assignment(
            teacher_id, task_name, academic_year, semester)
        if existing:
            self.db.execute(
                'UPDATE faculty_admin_assignments SET assignment_date = ? WHERE id = ?',
                (assignment_date, existing['id']),
            )
        else:
            self.db.execute(
                '''INSERT INTO faculty_admin_assignments
                   (teacher_id, task_name, auto_hours, manual_hours,
                    assignment_date, start_date, end_date, notes,
                    academic_year, semester)
                   VALUES (?, ?, 0, 0, ?, '', NULL, '', ?, ?)''',
                (teacher_id, task_name, assignment_date, academic_year, semester),
            )
        self.db.commit()

    def delete_single_admin_assignment(
        self, teacher_id: int, task_name: str, academic_year: str, semester: int,
    ) -> None:
        self.db.execute(
            '''DELETE FROM faculty_admin_assignments
               WHERE teacher_id = ? AND task_name = ?
               AND academic_year = ? AND semester = ?''',
            (teacher_id, task_name, academic_year, semester),
        )
        self.db.commit()

    # ── Leaves ───────────────────────────────────────────────────

    def get_leaves(
        self, teacher_id: int, academic_year: str, semester: int
    ) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            '''SELECT id, leave_type, decision_number, decision_authority,
                      decision_date, start_date, end_date, hours, notes
               FROM faculty_leaves
               WHERE teacher_id = ? AND deleted_at IS NULL''',
            (teacher_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def is_leave_active_for_semester(
        self, start_date: str, end_date: Optional[str],
        academic_year: str, semester: int,
    ) -> bool:
        sem_start, sem_end = semester_bounds(academic_year, semester)
        if start_date > sem_end:
            return False
        if end_date and end_date < sem_start:
            return False
        return True

    def upsert_leaves(
        self, teacher_id: int, leaves: List[Dict[str, Any]]
    ) -> None:
        self.db.execute(
            'DELETE FROM faculty_leaves WHERE teacher_id = ?',
            (teacher_id,),
        )
        for lv in leaves:
            leave_type = lv.get('leave_type', '').strip()
            decision_number = lv.get('decision_number', '')
            decision_authority = lv.get('decision_authority', '')
            decision_date = lv.get('decision_date', '')
            start_date = lv.get('start_date', '')
            end_date = lv.get('end_date') or None
            hours = int(lv.get('hours', 0) or 0)
            notes = lv.get('notes', '')
            if not leave_type or not start_date:
                continue
            self.db.execute(
                '''INSERT INTO faculty_leaves
                   (teacher_id, leave_type, decision_number, decision_authority,
                    decision_date, start_date, end_date, hours, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (teacher_id, leave_type, decision_number, decision_authority,
                 decision_date, start_date, end_date, hours, notes),
            )
        self.db.commit()

    # ── Dropdowns ────────────────────────────────────────────────

    def list_academic_departments(self) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            'SELECT id, name FROM departments WHERE type = \'academic\' AND deleted_at IS NULL ORDER BY name'
        ).fetchall()
        return [dict(r) for r in rows]

    def list_teachers_by_department(self, department_id: int) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            '''SELECT id, name, academic_number
               FROM teachers WHERE department_id = ? AND deleted_at IS NULL
               ORDER BY name''',
            (department_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_members_summary(self) -> List[Dict[str, Any]]:
        """All active teaching members with display fields (office member lists)."""
        rows = self.db.execute(
            '''SELECT t.id, t.name, t.email, t.academic_number,
                      d.name AS dept_name,
                      q.name_ar AS qual_name, r.name_ar AS rank_name
               FROM teachers t
               LEFT JOIN departments d ON t.department_id = d.id
               LEFT JOIN qualifications q ON t.qualification_id = q.id
               LEFT JOIN academic_ranks r ON t.rank_id = r.id
               WHERE t.deleted_at IS NULL
               ORDER BY d.name, t.name'''
        ).fetchall()
        return [dict(r) for r in rows]

    def list_academic_years(self) -> List[str]:
        rows = self.db.execute(
            '''SELECT DISTINCT semester_code FROM timetable_versions
               WHERE status = 'active'
               ORDER BY semester_code DESC'''
        ).fetchall()
        years = []
        for r in rows:
            code = r[0]
            if code and code not in years:
                years.append(code)
        if not years:
            years = ['2025-2026']
        return years

    def get_teacher_department(self, teacher_id: int) -> Optional[int]:
        row = self.db.execute(
            'SELECT department_id FROM teachers WHERE id = ? AND deleted_at IS NULL',
            (teacher_id,),
        ).fetchone()
        return row[0] if row else None

    # ── Lookup Tables ────────────────────────────────────────────

    def list_research_activity_types(self) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            'SELECT id, name FROM research_activity_types WHERE is_active = 1 ORDER BY sort_order, id'
        ).fetchall()
        return [dict(r) for r in rows]

    def list_admin_assignment_types(self) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            'SELECT id, name, default_hours FROM admin_assignment_types WHERE is_active = 1 ORDER BY sort_order, id'
        ).fetchall()
        return [dict(r) for r in rows]
