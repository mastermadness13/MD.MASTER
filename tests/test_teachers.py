"""Tests for teacher creation guards — academic_number identity checks."""

import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.repositories.teacher_repository import TeacherRepository
from database.schema import ensure_schema
from services.teacher_service import TeacherService


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'teachers_test.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) "
        "VALUES ('admin', 'x', 'super_admin', 'مدير')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, has_sections, type) "
        "VALUES ('قسم الحاسوب', 7, 8, 0, 1, 'academic')"
    )
    conn.commit()
    conn.close()
    return db_path


def _make_service(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    repo = TeacherRepository(conn)
    return TeacherService(conn, repo), conn


def _make_teacher_data(**overrides):
    data = {
        'name': 'أحمد علي',
        'email': '',
        'phone': '',
        'department_id': 1,
        'academic_number': '',
        'qualification_id': None,
        'rank_id': None,
        'classification_id': None,
        'national_id': '',
        'contract_date': '',
        'tasks': '',
    }
    data.update(overrides)
    return data


def test_create_teacher_with_academic_number_succeeds(db_fx):
    svc, conn = _make_service(db_fx)
    result = svc.create_teacher(_make_teacher_data(academic_number='AN-001'))
    assert result['id'] > 0
    conn.close()


def test_create_teacher_rejects_duplicate_academic_number(db_fx):
    svc, conn = _make_service(db_fx)
    svc.create_teacher(_make_teacher_data(academic_number='AN-100'))

    with pytest.raises(ValueError, match='AN-100'):
        svc.create_teacher(_make_teacher_data(
            name='محمد حسن', academic_number='AN-100'
        ))
    conn.close()


def test_create_teacher_allows_same_name_different_person(db_fx):
    """Two teachers with the same name can exist in the teachers table.

    Note: create_teacher() also creates a user with a generated username,
    so same-name teachers must use different names through that path.
    This test verifies the teachers table itself allows it.
    """
    conn = sqlite3.connect(str(db_fx))
    conn.row_factory = sqlite3.Row
    conn.execute(
        'INSERT INTO teachers (name, academic_number) VALUES (?, ?)',
        ('عمر بن الخطاب', None),
    )
    conn.execute(
        'INSERT INTO teachers (name, academic_number) VALUES (?, ?)',
        ('عمر بن الخطاب', None),
    )
    conn.commit()
    count = conn.execute(
        "SELECT COUNT(*) FROM teachers WHERE name = 'عمر بن الخطاب'"
    ).fetchone()[0]
    assert count == 2
    conn.close()


def test_create_teacher_allows_different_academic_numbers(db_fx):
    svc, conn = _make_service(db_fx)
    r1 = svc.create_teacher(_make_teacher_data(
        name='خالد بن الوليد', academic_number='AN-201'
    ))
    r2 = svc.create_teacher(_make_teacher_data(
        name='صالح بن خالد', academic_number='AN-202'
    ))
    assert r1['id'] != r2['id']
    conn.close()


def test_create_teacher_academic_number_sentinels_not_unique(db_fx):
    svc, conn = _make_service(db_fx)
    r1 = svc.create_teacher(_make_teacher_data(name='الأول', academic_number=''))
    r2 = svc.create_teacher(_make_teacher_data(name='الثاني', academic_number=''))
    r3 = svc.create_teacher(_make_teacher_data(name='الثالث', academic_number=None))
    assert r1['id'] != r2['id']
    assert r2['id'] != r3['id']
    conn.close()


def test_academic_title_prefix_additions():
    from utils.format import academic_title_prefix
    assert academic_title_prefix('محاضر') == 'م.'
    assert academic_title_prefix('مساعد محاضر') == 'م.'
    assert academic_title_prefix('معيد') == 'أ.'
    assert academic_title_prefix('أستاذ مساعد') == 'د.'
    assert academic_title_prefix('أستاذ') == 'أ.د.'
    assert academic_title_prefix('') == ''
