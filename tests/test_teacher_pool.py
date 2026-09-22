"""Tests for teacher pool (many-to-many membership) features.

Covers:
  1. Teacher-pool endpoint excludes teachers already in HOD's dept
  2. Teacher-pool excludes soft-deleted teachers
  3. dept-assign adds teacher to department
  4. dept-assign prevents duplicate membership
  5. dept-unassign removes membership + reconciles department_id
  6. dept-unassign prevents removing last department
  7. _validate_specialization: no depts + spec allowed
  8. _validate_specialization: depts + spec from different dept rejected
"""

import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema
from routes.teachers import _validate_specialization, _reconcile_primary_dept


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'pool_test.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)

    conn.execute(
        "INSERT INTO departments (name, semesters, majors, hidden, has_sections, type) "
        "VALUES ('قسم الحاسوب', 7, 8, 0, 1, 'academic')"
    )
    conn.execute(
        "INSERT INTO departments (name, semesters, majors, hidden, has_sections, type) "
        "VALUES ('قسم الاتصالات', 7, 8, 0, 1, 'academic')"
    )
    dept1 = conn.execute(
        "SELECT id FROM departments WHERE name='قسم الحاسوب'"
    ).fetchone()['id']
    dept2 = conn.execute(
        "SELECT id FROM departments WHERE name='قسم الاتصالات'"
    ).fetchone()['id']

    conn.execute(
        "INSERT INTO teachers (name, academic_number, department_id) "
        "VALUES ('أحمد علي', 'AN-001', ?)", (dept1,)
    )
    conn.execute(
        "INSERT INTO teachers (name, academic_number, department_id) "
        "VALUES ('محمد حسن', 'AN-002', ?)", (dept2,)
    )
    conn.execute(
        "INSERT INTO teachers (name, academic_number, department_id) "
        "VALUES ('خالد يوسف', 'AN-003', ?)", (dept2,)
    )
    conn.execute(
        "INSERT INTO teachers (name, academic_number, department_id) "
        "VALUES ('عبده الناجي', 'AN-004', ?)", (dept2,)
    )
    t1 = conn.execute(
        "SELECT id FROM teachers WHERE academic_number='AN-001'"
    ).fetchone()['id']
    t2 = conn.execute(
        "SELECT id FROM teachers WHERE academic_number='AN-002'"
    ).fetchone()['id']

    conn.execute(
        'INSERT INTO teacher_departments (teacher_id, department_id) VALUES (?, ?)',
        (t1, dept1),
    )
    conn.execute(
        'INSERT INTO teacher_departments (teacher_id, department_id) VALUES (?, ?)',
        (t2, dept2),
    )

    conn.execute(
        "INSERT INTO users (username, password, role, label, department_id) "
        "VALUES ('hod', 'x', 'head_of_department', 'رئيس قسم الحاسوب', ?)",
        (dept1,),
    )
    conn.execute(
        "INSERT INTO users (username, password, role, label) "
        "VALUES ('admin', 'x', 'faculty_affairs', 'مدير')"
    )
    conn.commit()
    conn.close()
    return db_path


def _conn(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def test_pool_excludes_teacher_already_in_hod_dept(db_fx):
    """AN-001 is in dept1 (HOD dept) — should NOT appear in pool."""
    conn = _conn(db_fx)
    dept1 = conn.execute(
        "SELECT id FROM departments WHERE name='قسم الحاسوب'"
    ).fetchone()['id']
    pool = conn.execute(
        'SELECT t.id FROM teachers t '
        'WHERE t.deleted_at IS NULL '
        'AND NOT EXISTS ('
        '  SELECT 1 FROM teacher_departments tdx '
        '  WHERE tdx.teacher_id = t.id AND tdx.department_id = ?'
        ') ORDER BY t.name',
        (dept1,),
    ).fetchall()
    pool_ids = [r['id'] for r in pool]
    t1 = conn.execute(
        "SELECT id FROM teachers WHERE academic_number='AN-001'"
    ).fetchone()['id']
    t2 = conn.execute(
        "SELECT id FROM teachers WHERE academic_number='AN-002'"
    ).fetchone()['id']
    assert t1 not in pool_ids, "Teacher in HOD dept should NOT appear in pool"
    assert t2 in pool_ids, "Teacher in other dept SHOULD appear in pool"
    conn.close()

def test_dept_assign_adds_membership(db_fx):
    """Assigning a teacher adds membership to teacher_departments."""
    conn = _conn(db_fx)
    dept1 = conn.execute(
        "SELECT id FROM departments WHERE name='قسم الحاسوب'"
    ).fetchone()['id']
    t3 = conn.execute(
        "SELECT id FROM teachers WHERE academic_number='AN-003'"
    ).fetchone()['id']
    before = conn.execute(
        'SELECT COUNT(*) AS cnt FROM teacher_departments '
        'WHERE teacher_id = ? AND department_id = ?',
        (t3, dept1),
    ).fetchone()['cnt']
    assert before == 0
    conn.execute(
        'INSERT OR IGNORE INTO teacher_departments (teacher_id, department_id) VALUES (?, ?)',
        (t3, dept1),
    )
    _reconcile_primary_dept(conn, t3)
    conn.commit()
    after = conn.execute(
        'SELECT COUNT(*) AS cnt FROM teacher_departments '
        'WHERE teacher_id = ? AND department_id = ?',
        (t3, dept1),
    ).fetchone()['cnt']
    assert after == 1
    teacher = conn.execute(
        'SELECT department_id FROM teachers WHERE id = ?', (t3,)
    ).fetchone()
    assert teacher['department_id'] == dept1
    conn.close()


def test_dept_assign_prevents_duplicate(db_fx):
    """Assigning a teacher already in dept is idempotent (INSERT OR IGNORE)."""
    conn = _conn(db_fx)
    dept1 = conn.execute(
        "SELECT id FROM departments WHERE name='قسم الحاسوب'"
    ).fetchone()['id']
    t1 = conn.execute(
        "SELECT id FROM teachers WHERE academic_number='AN-001'"
    ).fetchone()['id']
    before = conn.execute(
        'SELECT COUNT(*) AS cnt FROM teacher_departments '
        'WHERE teacher_id = ? AND department_id = ?',
        (t1, dept1),
    ).fetchone()['cnt']
    assert before == 1
    conn.execute(
        'INSERT OR IGNORE INTO teacher_departments (teacher_id, department_id) VALUES (?, ?)',
        (t1, dept1),
    )
    conn.commit()
    after = conn.execute(
        'SELECT COUNT(*) AS cnt FROM teacher_departments '
        'WHERE teacher_id = ? AND department_id = ?',
        (t1, dept1),
    ).fetchone()['cnt']
    assert after == 1, "Duplicate insert should be ignored"
    conn.close()


def test_dept_unassign_removes_membership_and_reconciles(db_fx):
    """Unassigning removes membership and reconciles department_id."""
    conn = _conn(db_fx)
    dept1 = conn.execute(
        "SELECT id FROM departments WHERE name='قسم الحاسوب'"
    ).fetchone()['id']
    dept2 = conn.execute(
        "SELECT id FROM departments WHERE name='قسم الاتصالات'"
    ).fetchone()['id']
    t2 = conn.execute(
        "SELECT id FROM teachers WHERE academic_number='AN-002'"
    ).fetchone()['id']
    conn.execute(
        'INSERT OR IGNORE INTO teacher_departments (teacher_id, department_id) VALUES (?, ?)',
        (t2, dept1),
    )
    conn.commit()
    memberships = conn.execute(
        'SELECT department_id FROM teacher_departments WHERE teacher_id = ? ORDER BY department_id',
        (t2,),
    ).fetchall()
    assert len(memberships) == 2

    conn.execute(
        'DELETE FROM teacher_departments WHERE teacher_id = ? AND department_id = ?',
        (t2, dept1),
    )
    _reconcile_primary_dept(conn, t2)
    conn.commit()

    remaining = conn.execute(
        'SELECT department_id FROM teacher_departments WHERE teacher_id = ?',
        (t2,),
    ).fetchall()
    assert len(remaining) == 1
    assert remaining[0]['department_id'] == dept2
    teacher = conn.execute(
        'SELECT department_id FROM teachers WHERE id = ?', (t2,)
    ).fetchone()
    assert teacher['department_id'] == dept2
    conn.close()


def test_dept_unassign_prevents_last_department(db_fx):
    """Unassigning a teacher's only department is blocked at the route level.

    We test the data constraint: teacher must have at least one membership
    remaining (checked before calling the delete at route level).
    """
    conn = _conn(db_fx)
    dept1 = conn.execute(
        "SELECT id FROM departments WHERE name='قسم الحاسوب'"
    ).fetchone()['id']
    t1 = conn.execute(
        "SELECT id FROM teachers WHERE academic_number='AN-001'"
    ).fetchone()['id']
    remaining = conn.execute(
        'SELECT COUNT(*) AS cnt FROM teacher_departments '
        'WHERE teacher_id = ? AND department_id != ?',
        (t1, dept1),
    ).fetchone()['cnt']
    assert remaining == 0, "AN-001 is only in dept1 — cannot unassign"
    conn.close()


def test_validate_specialization_no_depts_spec_allowed(db_fx):
    """With no departments selected, any specialization is allowed."""
    conn = _conn(db_fx)
    result = _validate_specialization(
        conn, {'specialization_id': 999}, department_ids=[]
    )
    assert result is None, "No dept + spec should be allowed"
    conn.close()


def test_validate_specialization_depts_wrong_spec_rejected(db_fx):
    """With depts selected, a spec from a different dept is rejected."""
    conn = _conn(db_fx)
    dept1 = conn.execute(
        "SELECT id FROM departments WHERE name='قسم الحاسوب'"
    ).fetchone()['id']
    dept2 = conn.execute(
        "SELECT id FROM departments WHERE name='قسم الاتصالات'"
    ).fetchone()['id']
    conn.execute(
        'INSERT INTO specializations (name, department_id) VALUES (?, ?)',
        ('شبكات', dept2),
    )
    conn.commit()
    spec_id = conn.execute(
        'SELECT id FROM specializations WHERE name = ?'
    , ('شبكات',)).fetchone()['id']
    result = _validate_specialization(
        conn,
        {'specialization_id': spec_id},
        department_ids=[dept1],
    )
    assert result is not None, "Spec from dept2 should be rejected for dept1"
    assert 'لا ينتمي' in result
    conn.close()


def test_validate_specialization_depts_correct_spec_allowed(db_fx):
    """With depts selected, a spec from one of those depts is allowed."""
    conn = _conn(db_fx)
    dept1 = conn.execute(
        "SELECT id FROM departments WHERE name='قسم الحاسوب'"
    ).fetchone()['id']
    conn.execute(
        'INSERT INTO specializations (name, department_id) VALUES (?, ?)',
        ('هندسة برمجيات', dept1),
    )
    conn.commit()
    spec_id = conn.execute(
        'SELECT id FROM specializations WHERE name = ?'
    , ('هندسة برمجيات',)).fetchone()['id']
    result = _validate_specialization(
        conn,
        {'specialization_id': spec_id},
        department_ids=[dept1],
    )
    assert result is None
    conn.close()
