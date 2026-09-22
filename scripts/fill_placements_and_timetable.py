#!/usr/bin/env python3
"""One-time fill: place every catalog course into its department/phase and
auto-generate a conflict-free weekly timetable for each visible department.

- Placements: each ``DEFAULT_COURSE_CATALOG`` course is assigned to its
  department and program phase (القسم العام -> semester 1, other departments ->
  year + 1, matching the app's ``YEAR_TO_SEMESTER`` rule).
- Timetable: for each visible academic department and phase an active version
  is ensured and every placed course is scheduled into a free (day, period,
  teacher, room) slot using the department's teachers and the available rooms.

Idempotent: existing ``course_departments`` rows are rebuilt from the catalog,
and a department+phase that already has timetable entries is skipped.

Usage:
    python scripts/fill_placements_and_timetable.py
"""

from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config import Config
from database.connection import connect
from database.seed_data import DEFAULT_COURSE_CATALOG
from services.timetable_service import create_entry, ensure_current_version

# /     /     >---- القسم العام هو الوحيد اللي فصله الأول؛ باقي الأقسام فصلها = سنة + 1
GENERAL_DEPT = 'القسم العام'

# /     /     >---- الأقسام الأكاديمية الظاهرة اللي تولد لها الجداول (شعبة البرمجيات محذوفة)
VISIBLE_DEPTS = (
    'القسم العام',
    'قسم الاتصالات',
    'قسم الحاسوب',
    'قسم المدني',
    'قسم المعماري',
    'قسم النفط',
)

DAYS = ['السبت', 'الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس']
PERIODS = [('A', '09:00', '12:00'), ('B', '12:01', '15:00')]

# /     /     >---- ترتيب الفترات عبر الأسبوع (6 أيام × فترتان = 12 خانة)
SLOT_ORDER = [(day, period, start, end) for day in DAYS for period, start, end in PERIODS]


def placement_semester(department: str, year: int) -> int:
    return 1 if department == GENERAL_DEPT else year + 1


def fill_placements(db) -> int:
    dept_id_by_name = {
        row['name']: row['id']
        for row in db.execute('SELECT id, name FROM departments').fetchall()
    }
    course_id_by_name = {
        row['name']: row['id']
        for row in db.execute('SELECT id, name FROM courses').fetchall()
    }

    placements = []
    seen = set()
    for department, year, names in DEFAULT_COURSE_CATALOG:
        dept_id = dept_id_by_name.get(department)
        if dept_id is None:
            continue
        semester = placement_semester(department, year)
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            course_id = course_id_by_name.get(name)
            if course_id is None:
                print(f'  [warn] لا يوجد مقرر بهذا الاسم: {name}')
                continue
            placements.append((course_id, dept_id, semester, year, department))

    db.execute('DELETE FROM course_departments')
    for course_id, dept_id, semester, year, department in placements:
        db.execute(
            'INSERT INTO course_departments (course_id, department_id, semester) '
            'VALUES (?, ?, ?)',
            (course_id, dept_id, semester),
        )
        db.execute(
            'UPDATE courses SET department = ?, department_id = ?, year = ?, semester = ? '
            'WHERE id = ?',
            (department, dept_id, year, semester, course_id),
        )
    db.commit()
    print(f'[placements] {len(placements)} مقرر موزّع على أقسامه وفصوله')
    return len(placements)


def _dept_teacher_ids(db, dept_id: int, dept_name: str):
    rows = db.execute(
        'SELECT id FROM teachers WHERE department_id = ? OR department = ? ORDER BY id',
        (dept_id, dept_name),
    ).fetchall()
    return [row['id'] for row in rows]


def _available_rooms(db):
    rows = db.execute("SELECT id FROM rooms WHERE status = 'متاحة' ORDER BY id").fetchall()
    if not rows:
        rows = db.execute('SELECT id FROM rooms ORDER BY id').fetchall()
    return [row['id'] for row in rows]


def _pick_free(items, offset: int, busy: set):
    """Return the next free item cycling from a rotating offset, else None."""
    if not items:
        return None
    n = len(items)
    for k in range(n):
        item = items[(offset + k) % n]
        if item not in busy:
            return item
    return None


def generate_timetable(db) -> dict:
    dept_rows = {
        row['name']: row
        for row in db.execute('SELECT id, name FROM departments').fetchall()
    }
    rooms = _available_rooms(db)
    # /     /     >---- التتبع عام على كل الجدول حتى ما يتعارضش أستاذ أو قاعة
    # في نفس اليوم والفترة عبر فصول القسم الواحد أو الأقسام المشتركة بالقاعات.
    busy_teacher: dict = {}
    busy_room: dict = {}

    counts = {}
    course_index = 0

    for dept_name in VISIBLE_DEPTS:
        dept = dept_rows.get(dept_name)
        if not dept:
            continue
        dept_id = dept['id']
        sems = [
            row['semester'] for row in db.execute(
                'SELECT DISTINCT semester FROM course_departments '
                'WHERE department_id = ? ORDER BY semester',
                (dept_id,),
            ).fetchall()
        ]
        teachers = _dept_teacher_ids(db, dept_id, dept_name)

        for sem in sems:
            courses = [dict(row) for row in db.execute(
                'SELECT cd.course_id, c.code, c.name '
                'FROM course_departments cd '
                'JOIN courses c ON c.id = cd.course_id '
                'WHERE cd.department_id = ? AND cd.semester = ? ORDER BY c.code',
                (dept_id, sem),
            ).fetchall()]
            if not courses:
                continue

            key = (dept_name, sem)
            existing = db.execute(
                'SELECT 1 FROM timetable WHERE department_id = ? AND semester = ? LIMIT 1',
                (dept_id, sem),
            ).fetchone()
            if existing:
                print(f'  [skip] {dept_name} - فصل {sem} يوجد جدول بالفعل')
                counts[key] = 0
                continue

            version_id = ensure_current_version(db, dept_id, sem)
            n_placed = 0

            for course in courses:
                placed = False
                # /     /     >---- نبدا الفحص من خانة مختلفة لكل مقرر حتى نتوزع
                # الحصص على أيام الأسبوع ولا نكدّسها كلها في يوم واحد.
                start_at = course_index % len(SLOT_ORDER)
                for k in range(len(SLOT_ORDER)):
                    day, period, start, end = SLOT_ORDER[(start_at + k) % len(SLOT_ORDER)]
                    slot = (day, period)
                    teacher_id = _pick_free(teachers, course_index, busy_teacher.setdefault(slot, set()))
                    room_id = _pick_free(rooms, course_index, busy_room.setdefault(slot, set()))
                    if teacher_id is None or room_id is None:
                        continue
                    busy_teacher[slot].add(teacher_id)
                    busy_room[slot].add(room_id)
                    create_entry(
                        db, day, sem, period, course['course_id'],
                        teacher_id, room_id, dept_id,
                        start_time=start, end_time=end,
                        version_id=version_id,
                        lecture_type='theory', hours=3,
                    )
                    n_placed += 1
                    placed = True
                    break
                course_index += 1
                if not placed:
                    print(f'  [warn] لم يُجد مكان: {course["code"] or ""} {course["name"]} '
                          f'({dept_name} فصل {sem})')

            counts[key] = n_placed
            print(f'  [timetable] {dept_name} - فصل {sem}: {n_placed} حصة')

    return counts


def main():
    db = connect(Config.DATABASE)
    try:
        print('== 1) ملء توزيعات المقررات ==')
        fill_placements(db)
        print('== 2) توليد الجداول الأسبوعية ==')
        counts = generate_timetable(db)
        total = sum(counts.values())
        print(f'== انتهى: {sum(1 for v in counts.values() if v)} جدول مليان، '
              f'{total} حصة، و{sum(1 for v in counts.values() if v == 0)} جدول مكشوف (موجود سابقاً) ==')
    finally:
        db.close()


if __name__ == '__main__':
    main()