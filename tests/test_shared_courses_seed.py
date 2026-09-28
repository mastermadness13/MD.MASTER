"""The shared subjects (تمرين ميداني / مشروع) must land in every academic
department exactly once, with a generated code and no resurrection after a
soft delete.
"""

import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema
from database.seed_data import (
    SHARED_COURSES_ALL_DEPARTMENTS,
    SHARED_COURSES_EXCLUDED_DEPARTMENTS,
)

SUBJECT_NAMES = [name for name, _semester in SHARED_COURSES_ALL_DEPARTMENTS]


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'shared_courses_test.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.close()
    return db_path


def _q(db_path, sql, params=()):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _subjects(db_path):
    return _q(db_path, 'SELECT id, name, code, year, semester, department_id, icon '
                      'FROM courses WHERE name IN ({}) AND deleted_at IS NULL'
                      .format(','.join('?' * len(SUBJECT_NAMES))), SUBJECT_NAMES)


def _placements(db_path, course_id):
    return _q(db_path, 'SELECT cd.department_id, cd.semester, d.name AS dept '
                       'FROM course_departments cd JOIN departments d ON d.id = cd.department_id '
                       'WHERE cd.course_id = ? ORDER BY cd.department_id', (course_id,))


def _academic_departments(db_path):
    excluded = SHARED_COURSES_EXCLUDED_DEPARTMENTS
    rows = _q(db_path, 'SELECT id, name FROM departments '
                       "WHERE hidden = 0 AND type = 'academic' AND deleted_at IS NULL "
                       'ORDER BY id')
    return [r for r in rows if r['name'] not in excluded]


def test_bootstrap_creates_both_subjects_with_generated_codes(db_fx):
    from scripts.seed import bootstrap_defaults
    bootstrap_defaults(str(db_fx))

    subjects = {r['name']: r for r in _subjects(db_fx)}
    assert set(subjects) == set(SUBJECT_NAMES), subjects
    for name, semester in SHARED_COURSES_ALL_DEPARTMENTS:
        row = subjects[name]
        assert row['code'], 'a subject must still get a course code'
        assert row['code'] not in (None, ''), name
        assert row['semester'] == semester, row
        assert row['year'] == -(-semester // 2), row
        assert row['icon'] and row['icon'] != '�Y"-', row


def test_each_subject_reaches_every_academic_department(db_fx):
    from scripts.seed import bootstrap_defaults
    bootstrap_defaults(str(db_fx))

    departments = _academic_departments(db_fx)
    assert len(departments) >= 2, 'fixture needs at least two academic departments'
    for subject in _subjects(db_fx):
        placements = _placements(db_fx, subject['id'])
        assert len(placements) == len(departments), (subject, placements, departments)
        assert {p['department_id'] for p in placements} == {d['id'] for d in departments}


def test_general_department_is_excluded(db_fx):
    from scripts.seed import bootstrap_defaults
    bootstrap_defaults(str(db_fx))

    placeholders = ','.join('?' * len(SHARED_COURSES_EXCLUDED_DEPARTMENTS))
    excluded_ids = {
        r['id'] for r in _q(db_fx, f'SELECT id FROM departments WHERE name IN ({placeholders})',
                            SHARED_COURSES_EXCLUDED_DEPARTMENTS)
    }
    assert excluded_ids, 'fixture must contain an excluded department'
    for subject in _subjects(db_fx):
        for placement in _placements(db_fx, subject['id']):
            assert placement['department_id'] not in excluded_ids, placement


def test_bootstrap_twice_adds_no_duplicates(db_fx):
    from scripts.seed import bootstrap_defaults
    bootstrap_defaults(str(db_fx))
    first = ({r['name']: r['code'] for r in _subjects(db_fx)},
             {r['name']: r['id'] for r in _subjects(db_fx)})
    placements_first = sum(len(_placements(db_fx, r['id'])) for r in _subjects(db_fx))

    bootstrap_defaults(str(db_fx))

    second = ({r['name']: r['code'] for r in _subjects(db_fx)},
              {r['name']: r['id'] for r in _subjects(db_fx)})
    placements_second = sum(len(_placements(db_fx, r['id'])) for r in _subjects(db_fx))
    assert second == first, (first, second)
    assert placements_second == placements_first


def test_ensure_schema_path_restores_placements_in_existing_database(db_fx):
    """``flask run`` never calls bootstrap_defaults, only ensure_schema."""
    from scripts.seed import bootstrap_defaults
    bootstrap_defaults(str(db_fx))
    expected = len(_academic_departments(db_fx)) * len(SUBJECT_NAMES)

    conn = connect(str(db_fx))
    conn.execute('DELETE FROM course_departments')
    conn.commit()
    conn.close()

    flask_db.ensure_database_schema()

    placed = sum(len(_placements(db_fx, r['id'])) for r in _subjects(db_fx))
    assert placed == expected, (placed, expected)


def test_ensure_schema_path_does_not_resurrect_soft_deleted_subjects(db_fx):
    from scripts.seed import bootstrap_defaults
    bootstrap_defaults(str(db_fx))
    placements_before = len(_q(db_fx, 'SELECT 1 FROM course_departments'))

    conn = connect(str(db_fx))
    conn.execute('UPDATE courses SET deleted_at = ?', ('2026-01-01',))
    conn.commit()
    conn.close()

    flask_db.ensure_database_schema()
    bootstrap_defaults(str(db_fx))

    assert _subjects(db_fx) == []
    assert len(_q(db_fx, 'SELECT 1 FROM course_departments')) == placements_before


def test_soft_deleted_subject_is_not_resurrected(db_fx):
    from scripts.seed import bootstrap_defaults
    bootstrap_defaults(str(db_fx))
    conn = connect(str(db_fx))
    conn.execute("UPDATE courses SET deleted_at = '2026-01-01' WHERE name = ?",
                 (SUBJECT_NAMES[0],))
    conn.commit()
    conn.close()

    bootstrap_defaults(str(db_fx))
    flask_db.ensure_database_schema()

    alive = {r['name'] for r in _subjects(db_fx)}
    assert SUBJECT_NAMES[0] not in alive
    assert set(SUBJECT_NAMES[1:]) <= alive


def test_course_codes_stay_unique(db_fx):
    from scripts.seed import bootstrap_defaults
    bootstrap_defaults(str(db_fx))

    codes = [r['code'] for r in _q(db_fx, 'SELECT code FROM courses '
                                            'WHERE code IS NOT NULL AND code != ""')]
    assert len(codes) == len(set(codes))


def test_code_is_not_hardcoded_and_follows_the_occupied_slots(db_fx):
    """The code is allocated at seed time, so squatting the next slot shifts it."""
    from scripts.seed import bootstrap_defaults
    bootstrap_defaults(str(db_fx))
    first = {r['name']: r['code'] for r in _subjects(db_fx)}

    conn = connect(str(db_fx))
    conn.execute('DELETE FROM courses WHERE name = ?', (SUBJECT_NAMES[1],))
    conn.execute('INSERT INTO courses (name, code, year, semester, department, '
                 'department_id) VALUES (?, ?, 4, 8, ?, NULL)',
                 ('مقرر يحجز الرمز', first[SUBJECT_NAMES[1]], 'مشترك بين الأقسام'))
    conn.commit()
    conn.close()

    bootstrap_defaults(str(db_fx))

    codes = {r['name']: r['code'] for r in _subjects(db_fx)}
    assert codes[SUBJECT_NAMES[1]] != first[SUBJECT_NAMES[1]], codes
    test_course_codes_stay_unique(db_fx)
