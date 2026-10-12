"""The teaching ledger mirrors saved timetable entries without inflating hours."""

from database.repositories.teacher_repository import TeacherRepository
from database.repositories.timetable_repository import TimetableRepository
from database.schema import ensure_schema
from services.timetable_service import TimetableService


def _seed_schedule(db):
    department_id = db.execute(
        "INSERT INTO departments "
        "(name, semesters, majors, hidden, has_sections, type) "
        "VALUES ('قسم المزامنة', 8, 8, 0, 1, 'academic')"
    ).lastrowid
    teacher_id = db.execute(
        'INSERT INTO teachers (name, department_id) VALUES (?, ?)',
        ('أ. اختبار المزامنة', department_id),
    ).lastrowid
    course_id = db.execute(
        'INSERT INTO courses (code, name, department_id, semester) '
        'VALUES (?, ?, ?, 1)',
        ('SYNC-1', 'مقرر المزامنة', department_id),
    ).lastrowid
    active_version_id = db.execute(
        'INSERT INTO timetable_versions '
        '(department_id, semester, semester_code, status) '
        "VALUES (?, 1, 'fall_2026', 'active')",
        (department_id,),
    ).lastrowid
    old_version_id = db.execute(
        'INSERT INTO timetable_versions '
        '(department_id, semester, semester_code, status) '
        "VALUES (?, 1, 'spring_2026', 'superseded')",
        (department_id,),
    ).lastrowid
    db.commit()
    return department_id, teacher_id, course_id, active_version_id, old_version_id


def _timetable_row(db, teacher_id, course_id, department_id, version_id,
                   day, hours, deleted_at=None):
    return db.execute(
        'INSERT INTO timetable '
        '(day, semester, period, course_id, teacher_id, department_id, '
        'version_id, hours, deleted_at) '
        'VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?)',
        (day, 'A', course_id, teacher_id, department_id, version_id,
         hours, deleted_at),
    ).lastrowid


def test_schema_rebuilds_ledger_from_non_deleted_timetable_rows(raw_db):
    department_id, teacher_id, course_id, active_version, old_version = (
        _seed_schedule(raw_db)
    )
    active_entry = _timetable_row(
        raw_db, teacher_id, course_id, department_id, active_version,
        'الأحد', 3,
    )
    historical_entry = _timetable_row(
        raw_db, teacher_id, course_id, department_id, old_version,
        'الاثنين', 2,
    )
    _timetable_row(
        raw_db, teacher_id, course_id, department_id, active_version,
        'الثلاثاء', 8, deleted_at='2026-10-01 00:00:00',
    )
    raw_db.execute(
        'INSERT INTO teacher_taught_courses '
        '(teacher_id, course_id, department_id, semester, semester_code, '
        'day, period, hours, timetable_entry_id) '
        'VALUES (?, ?, ?, 1, ?, ?, ?, 99, ?)',
        (teacher_id, course_id, department_id, 'fall_2026', 'الأحد', 'A',
         active_entry),
    )
    raw_db.execute(
        'INSERT INTO teacher_taught_courses '
        '(teacher_id, course_id, department_id, semester, semester_code, '
        'day, period, hours, timetable_entry_id) '
        'VALUES (?, ?, ?, 1, ?, ?, ?, 40, 999999)',
        (teacher_id, course_id, department_id, 'fall_2026', 'الخميس', 'Z'),
    )
    raw_db.execute(
        "DELETE FROM _migration_log "
        "WHERE migration_name = 'taught_courses_by_timetable_entry_v1'"
    )
    raw_db.commit()

    ensure_schema(raw_db)

    rows = raw_db.execute(
        'SELECT timetable_entry_id, hours FROM teacher_taught_courses '
        'ORDER BY timetable_entry_id'
    ).fetchall()
    assert [(row['timetable_entry_id'], row['hours']) for row in rows] == [
        (active_entry, 3),
        (historical_entry, 2),
    ]
    assert TeacherRepository(raw_db).count_teaching_hours(teacher_id) == 3


def test_recording_and_deleting_entry_keeps_one_ledger_row(raw_db):
    schedule = _seed_schedule(raw_db)
    department_id, teacher_id, course_id, version_id = schedule[:4]
    entry_id = _timetable_row(
        raw_db, teacher_id, course_id, department_id, version_id,
        'الأحد', 2,
    )
    service = TimetableService(raw_db, TimetableRepository(raw_db))

    service._record_taught_course(
        teacher_id, course_id, department_id, 1, version_id,
        day='الأحد', period='A', hours=2, timetable_entry_id=entry_id,
    )
    service._record_taught_course(
        teacher_id, course_id, department_id, 1, version_id,
        day='الاثنين', period='B', hours=4, timetable_entry_id=entry_id,
    )
    rows = raw_db.execute(
        'SELECT timetable_entry_id, day, hours FROM teacher_taught_courses '
        'WHERE timetable_entry_id = ?',
        (entry_id,),
    ).fetchall()
    assert len(rows) == 1
    assert (rows[0]['day'], rows[0]['hours']) == ('الاثنين', 4)

    assert TimetableRepository(raw_db).delete(entry_id)
    assert raw_db.execute(
        'SELECT 1 FROM teacher_taught_courses WHERE timetable_entry_id = ?',
        (entry_id,),
    ).fetchone() is None
