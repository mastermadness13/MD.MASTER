# -*- coding: utf-8 -*-
"""Area 1 (database) — N+1 regression guards.

Three query-in-loop patterns were batched:

* ``ExamService.build_dept_exam_data`` fetched exam rows once per department;
  it now fetches them once and partitions by ``department_id`` in Python.
* ``sync_courses_from_timetable`` ran a ``GROUP BY semester`` query per course;
  it now runs one query grouped by ``(course_id, semester)``.
* ``copy_submission_as_draft`` re-ran ``PRAGMA table_info`` for every
  curriculum row; the schema probe is hoisted and the rows go in via
  ``executemany``.

Batching is only safe if each row still lands with its original owner, so
these tests pin the partitioning rather than just asserting "no exception".
"""

import pytest

from database.connection import connect
from database.schema import ensure_schema
from services.course_content_service import copy_submission_as_draft
from services.course_service import sync_courses_from_timetable
from services.exam_service import EXAM_DAYS_ORDER, build_dept_exam_data


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / 'area1_nplusone.db'
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    yield conn
    conn.close()


def _dept(conn, name, semesters=8):
    conn.execute(
        'INSERT INTO departments (name, semesters, majors, hidden, type) '
        'VALUES (?, ?, 0, 0, ?)',
        (name, semesters, 'general' if semesters <= 1 else 'academic'),
    )
    return conn.execute(
        'SELECT id FROM departments WHERE name = ?', (name,)
    ).fetchone()['id']


def _course(conn, dept_id, code, name, year=1):
    conn.execute(
        'INSERT INTO courses (code, name, year, department_id) VALUES (?, ?, ?, ?)',
        (code, name, year, dept_id),
    )
    return conn.execute(
        'SELECT id FROM courses WHERE code = ?', (code,)
    ).fetchone()['id']


def test_exam_grid_partitions_rows_per_department(db):
    day = EXAM_DAYS_ORDER[0]
    cs_dept = _dept(db, 'قسم الحاسوب')
    math_dept = _dept(db, 'قسم الرياض')
    db.execute('INSERT INTO rooms (name) VALUES (?)', ('قاعة 101',))
    room_id = db.execute('SELECT id FROM rooms LIMIT 1').fetchone()['id']

    cs_course = _course(db, cs_dept, 'CS101', 'مقرر حاسوب')
    math_course = _course(db, math_dept, 'MA101', 'مقرر رياض')

    for dept_id, course_id in ((cs_dept, cs_course), (math_dept, math_course)):
        db.execute(
            'INSERT INTO exam_schedule (course_id, room_id, department_id, '
            'week, day_ar, start_time, semester, status) '
            "VALUES (?, ?, ?, 1, ?, '08:00', 1, 'published')",
            (course_id, room_id, dept_id, day),
        )
    db.commit()

    grid = build_dept_exam_data(db)

    found = {}
    for entry in grid:
        names = set()
        for slot in entry['time_slots']:
            for row in slot['cells'].values():
                names.add(row['course_name'])
        found[entry['id']] = names

    assert found[cs_dept] == {'مقرر حاسوب'}
    assert found[math_dept] == {'مقرر رياض'}


def test_exam_grid_batched_query_respects_published_filter(db):
    day = EXAM_DAYS_ORDER[0]
    dept_id = _dept(db, 'قسم الحاسوب')
    course_id = _course(db, dept_id, 'CS102', 'مقرر مسودة')
    db.execute(
        'INSERT INTO exam_schedule (course_id, department_id, week, day_ar, '
        "start_time, semester, status) VALUES (?, ?, 1, ?, '08:00', 1, 'draft')",
        (course_id, dept_id, day),
    )
    db.commit()

    everything = build_dept_exam_data(db)
    published = build_dept_exam_data(db, published_only=True)

    def names(entries):
        out = set()
        for entry in entries:
            for slot in entry['time_slots']:
                for row in slot['cells'].values():
                    out.add(row['course_name'])
        return out

    assert names(everything) == {'مقرر مسودة'}
    assert names(published) == set()


def test_sync_courses_uses_batched_semester_counts(db):
    dept_id = _dept(db, 'قسم الحاسوب')
    clear = _course(db, dept_id, 'CS201', 'مقرر واضح', year=5)
    tied = _course(db, dept_id, 'CS202', 'مقرر متساوي', year=5)

    rows = [
        (clear, 2), (clear, 2), (clear, 2), (clear, 3),
        (tied, 2), (tied, 3),
    ]
    for course_id, semester in rows:
        db.execute(
            'INSERT INTO timetable (course_id, department_id, day, semester) '
            "VALUES (?, ?, 'الأحد', ?)",
            (course_id, dept_id, semester),
        )
    db.commit()

    result = sync_courses_from_timetable(db, dept_id)

    assert result['synced'] == 1
    assert result['skipped'] == 1
    assert len(result['messages']) == 1
    assert db.execute(
        'SELECT year FROM courses WHERE id = ?', (clear,)
    ).fetchone()['year'] == 1
    assert db.execute(
        'SELECT year FROM courses WHERE id = ?', (tied,)
    ).fetchone()['year'] == 5


def test_sync_courses_skips_course_without_timetable(db):
    dept_id = _dept(db, 'قسم الحاسوب')
    orphan = _course(db, dept_id, 'CS301', 'مقرر بلا جدول', year=4)
    db.commit()

    result = sync_courses_from_timetable(db, dept_id)

    assert result['synced'] == 0
    assert result['skipped'] == 1
    assert db.execute(
        'SELECT year FROM courses WHERE id = ?', (orphan,)
    ).fetchone()['year'] == 4


def test_copy_submission_clones_all_curriculum_rows(db):
    db.execute(
        "INSERT INTO users (username, password, role, label) "
        "VALUES ('uploader', 'x', 'teacher', 'معلم')"
    )
    user_id = db.execute('SELECT id FROM users LIMIT 1').fetchone()['id']
    dept_id = _dept(db, 'قسم الحاسوب')
    course_id = _course(db, dept_id, 'CS401', 'مقرر محتوى')

    db.execute(
        'INSERT INTO course_content_submissions '
        '(user_id, department_id, course_id, course_name, course_code, status) '
        "VALUES (?, ?, ?, 'مقرر محتوى', 'CS401', 'draft')",
        (user_id, dept_id, course_id),
    )
    src_id = db.execute(
        'SELECT id FROM course_content_submissions LIMIT 1'
    ).fetchone()['id']

    topics = ['الموضوع الأول', 'الموضوع الثاني', 'الموضوع الثالث']
    for topic in topics:
        db.execute(
            'INSERT INTO course_content_curriculum (submission_id, topic) '
            'VALUES (?, ?)',
            (src_id, topic),
        )
    db.commit()

    new_id, label = copy_submission_as_draft(db, src_id)

    assert new_id != src_id
    assert label
    new = db.execute(
        'SELECT * FROM course_content_submissions WHERE id = ?', (new_id,)
    ).fetchone()
    assert new['parent_submission_id'] == src_id
    assert new['status'] == 'draft'
    assert new['published_at'] is None
    assert new['course_name'] == 'مقرر محتوى'

    copied = db.execute(
        'SELECT topic FROM course_content_curriculum WHERE submission_id = ? '
        'ORDER BY id',
        (new_id,),
    ).fetchall()
    assert [r['topic'] for r in copied] == topics


def test_copy_submission_without_curriculum(db):
    db.execute(
        "INSERT INTO users (username, password, role, label) "
        "VALUES ('uploader', 'x', 'teacher', 'معلم')"
    )
    user_id = db.execute('SELECT id FROM users LIMIT 1').fetchone()['id']
    dept_id = _dept(db, 'قسم الحاسوب')
    db.execute(
        'INSERT INTO course_content_submissions '
        '(user_id, department_id, course_name, course_code, status) '
        "VALUES (?, ?, 'مقرر فارغ', 'CS501', 'draft')",
        (user_id, dept_id),
    )
    src_id = db.execute(
        'SELECT id FROM course_content_submissions LIMIT 1'
    ).fetchone()['id']
    db.commit()

    new_id, label = copy_submission_as_draft(db, src_id)

    assert new_id != src_id
    assert db.execute(
        'SELECT COUNT(*) AS n FROM course_content_curriculum WHERE submission_id = ?',
        (new_id,),
    ).fetchone()['n'] == 0


def _index_names(conn, table):
    return [r['name'] for r in conn.execute("PRAGMA index_list('%s')" % table)]


def test_fresh_schema_declares_timetable_teacher_day_index(db):
    assert 'idx_timetable_teacher_day' in _index_names(db, 'timetable')
    cols = [r['name'] for r in db.execute(
        "PRAGMA index_info('idx_timetable_teacher_day')")]
    assert cols == ['teacher_id', 'day']


def test_runtime_migration_recreates_timetable_teacher_day_index(db):
    db.execute('DROP INDEX IF EXISTS idx_timetable_teacher_day')
    db.commit()
    assert 'idx_timetable_teacher_day' not in _index_names(db, 'timetable')

    ensure_schema(db)

    assert 'idx_timetable_teacher_day' in _index_names(db, 'timetable')


def test_teacher_day_index_serves_the_weekly_schedule_lookup(db):
    dept_id = _dept(db, 'قسم الحاسوب')
    course_id = _course(db, dept_id, 'CS601', 'مقرر فهرس')
    for day in ('الاثنين', 'الثلاثاء'):
        for period in (1, 2):
            db.execute(
                'INSERT INTO timetable (course_id, department_id, day, period) '
                'VALUES (?, ?, ?, ?)',
                (course_id, dept_id, day, period),
            )
    db.commit()

    plan = ' '.join(
        r['detail'] for r in db.execute(
            'EXPLAIN QUERY PLAN SELECT id FROM timetable '
            'WHERE teacher_id = ? AND day = ? AND deleted_at IS NULL',
            (1, 'الاثنين'),
        )
    )
    assert 'idx_timetable_teacher_day' in plan
