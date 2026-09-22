# -*- coding: utf-8 -*-
"""Unit tests for services/timetable_scope.py — Phase 0.

Covers the single source of truth for the general-department semester rule:
detection, allowed-semester ranges, the central validation guard, the
per-user scope mirrors, and the change-tracking token.
"""

import sqlite3

import pytest

from database.connection import connect
from database.schema import ensure_schema
from services.timetable_scope import (
    GENERAL_DEPT_NAME,
    INVALID_SEMESTER_MESSAGE,
    InvalidSemesterError,
    allowed_semesters_for,
    can_edit_entry,
    compute_scope,
    is_general_dept,
    semester_token,
    validate_semester_allowed,
)


@pytest.fixture
def db_fx(tmp_path):
    db_path = tmp_path / 'tt_scope.db'
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)

    conn.execute(
        "INSERT INTO departments (name, semesters, majors, hidden, has_sections, type) "
        "VALUES ('القسم العام', 1, 1, 0, 1, 'academic')"
    )
    general_id = conn.execute("SELECT id FROM departments WHERE name='القسم العام'").fetchone()['id']
    conn.execute(
        "INSERT INTO departments (name, semesters, majors, hidden, has_sections, type) "
        "VALUES ('قسم الحاسوب', 8, 8, 0, 1, 'academic')"
    )
    computers_id = conn.execute("SELECT id FROM departments WHERE name='قسم الحاسوب'").fetchone()['id']
    conn.commit()
    yield conn, general_id, computers_id
    conn.close()


# ───────────────────────────── is_general_dept ─────────────────────────────

def test_is_general_by_name():
    assert is_general_dept({'name': 'القسم العام', 'semesters': 8})


def test_is_general_by_semesters_le_one():
    assert is_general_dept({'name': 'قسم غريب', 'semesters': 1})
    assert is_general_dept({'name': 'قسم غريب', 'semesters': 0})


def test_is_not_general_regular():
    assert not is_general_dept({'name': 'قسم الحاسوب', 'semesters': 8})


def test_is_general_false_for_missing_or_none():
    assert not is_general_dept(None)
    assert not is_general_dept({})
    assert not is_general_dept({'name': 'قسم الحاسوب'})


# ───────────────────────── approved semester ranges ─────────────────────────

def test_allowed_general_semester_only_one():
    assert allowed_semesters_for({'name': 'القسم العام', 'semesters': 1}) == [1]


def test_allowed_regular_eight_semesters():
    assert allowed_semesters_for({'name': 'قسم الحاسوب', 'semesters': 8}) == [2, 3, 4, 5, 6, 7, 8]


def test_allowed_regular_respects_own_count():
    assert allowed_semesters_for({'name': 'قسم مدني', 'semesters': 5}) == [2, 3, 4, 5]


def test_allowed_missing_row_defaults_to_regular():
    assert allowed_semesters_for(None) == [1]


# ───────────────────────────── validation guard ─────────────────────────────

def test_validate_accepts_allowed_semester(db_fx):
    conn, _general, computers = db_fx
    validate_semester_allowed(conn, computers, 5)


def test_validate_rejects_semester_one_for_regular_dept(db_fx):
    conn, _general, computers = db_fx
    with pytest.raises(InvalidSemesterError) as exc:
        validate_semester_allowed(conn, computers, 1)
    assert str(exc.value) == INVALID_SEMESTER_MESSAGE


def test_validate_rejects_semester_two_for_general_dept(db_fx):
    conn, general, _computers = db_fx
    with pytest.raises(InvalidSemesterError):
        validate_semester_allowed(conn, general, 2)


def test_validate_skips_unknown_department(db_fx):
    conn, _general, _computers = db_fx
    validate_semester_allowed(conn, 999999, 1)


def test_validate_rejects_non_numeric_semester(db_fx):
    conn, _general, computers = db_fx
    with pytest.raises(InvalidSemesterError):
        validate_semester_allowed(conn, computers, 'abc')


# ───────────────────────────── compute_scope ─────────────────────────────

def _user(role, department_id=None, teacher_id=None, roles=None):
    return {'id': 1, 'role': role, 'roles': roles,
            'department_id': department_id, 'teacher_id': teacher_id}


def test_scope_exam_no_longer_has_timetable_access():
    scope = compute_scope(_user('exam'))
    assert not scope['can_view'] and not scope['can_edit']
    assert not scope['can_print_all']
    assert scope['is_hod'] is False


def test_scope_teacher_views_without_edit():
    scope = compute_scope(_user('teacher', teacher_id=7))
    assert scope['can_view'] and not scope['can_edit']
    assert scope['own_teacher_id'] == 7


def test_scope_hod_scoped_to_own_department():
    scope = compute_scope(_user('head_of_department', department_id=3))
    assert scope['is_hod'] and scope['editable_dept_id'] == 3


def test_scope_unknown_user_is_denied():
    scope = compute_scope({'id': 1, 'role': 'not_a_role'})
    assert not scope['can_view'] and not scope['can_edit']


def test_can_edit_hod_only_own_dept():
    user = _user('head_of_department', department_id=3)
    assert can_edit_entry(user, 3)
    assert not can_edit_entry(user, 4)


def test_can_edit_denied_without_edit_permission():
    assert not can_edit_entry(_user('exam'), 3)


# ───────────────────────────── semester_token ─────────────────────────────

def test_semester_token_changes_when_entry_added(db_fx):
    conn, _general, computers = db_fx
    before = semester_token(conn, computers, 2)
    conn.execute(
        "INSERT INTO timetable (day, semester, period, department_id) "
        "VALUES ('الأحد', 2, 'A', ?)",
        (computers,),
    )
    conn.commit()
    after = semester_token(conn, computers, 2)
    assert before != after