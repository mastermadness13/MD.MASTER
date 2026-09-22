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
        "VALUES ('admin', 'x', 'faculty_affairs', 'مدير')"
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


def test_initial_login_code_sent_and_lifecycle(db_fx):
    """On teacher creation, an initial code is hashed + expiring; first login
    invalidates it permanently (email-only flow)."""
    svc, conn = _make_service(db_fx)
    result = svc.create_teacher(_make_teacher_data(
        name='حساب جديد', academic_number='AN-900', email='new@example.com'
    ))
    user = conn.execute(
        'SELECT * FROM users WHERE id = (SELECT user_id FROM teachers '
        'WHERE academic_number = \'AN-900\')'
    ).fetchone()
    assert user['initial_login_code_hash']
    assert user['initial_login_code_used'] == 0
    assert user['initial_login_code_expires']
    assert user['force_password_change'] == 1
    # تسجيل الدخول بالرمز: يُنجح ثم يبطل الرمز فوراً
    from services.user_service import UserService
    from database.repositories.user_repository import UserRepository
    repo = UserRepository(conn)
    svc2 = UserService(conn, repo)
    session_dict = {}
    ok, _ = svc2.authenticate(user['username'], result['password'], False, session_dict)
    assert ok is True
    after = conn.execute(
        'SELECT initial_login_code_used, initial_login_code_hash FROM users WHERE id = ?',
        (user['id'],)
    ).fetchone()
    assert after['initial_login_code_used'] == 1
    assert after['initial_login_code_hash'] is None
    conn.close()


def test_initial_login_code_expired_rejected(db_fx):
    """An unused, expired initial code must reject login (recovery via email)."""
    svc, conn = _make_service(db_fx)
    result = svc.create_teacher(_make_teacher_data(
        name='حساب منتهي', academic_number='AN-901'
    ))
    conn.execute(
        'UPDATE users SET initial_login_code_expires = \'2000-01-01 00:00:00\' '
        'WHERE id = (SELECT user_id FROM teachers WHERE academic_number = \'AN-901\')'
    )
    conn.commit()
    user = conn.execute(
        'SELECT * FROM users WHERE username = ?', (result['username'],)
    ).fetchone()
    from services.user_service import UserService
    from database.repositories.user_repository import UserRepository
    svc2 = UserService(conn, UserRepository(conn))
    ok, marker = svc2.authenticate(user['username'], result['password'], False, {})
    assert ok is False
    # الرمز منتهي ولم يُستعمل: نرجع علامة مميزة تُعرض كرسالة واضحة في الواجهة
    assert marker is not None and marker.get('auth_error') == 'initial_code_expired'
    conn.close()


def test_academic_title_prefix_additions():
    from utils.format import academic_title_prefix
    assert academic_title_prefix('محاضر') == 'م.'
    assert academic_title_prefix('مساعد محاضر') == 'م.'
    assert academic_title_prefix('معيد') == 'أ.'
    assert academic_title_prefix('أستاذ مساعد') == 'د.'
    assert academic_title_prefix('أستاذ') == 'أ.د.'
    assert academic_title_prefix('') == ''


def _insert_teacher_without_account(conn, name='أستاذ مستورد', academic_number='AN-IMP-1'):
    conn.execute(
        'INSERT INTO teachers (name, academic_number) VALUES (?, ?)',
        (name, academic_number),
    )
    conn.commit()
    return conn.execute(
        'SELECT id FROM teachers WHERE academic_number = ?', (academic_number,)
    ).fetchone()['id']


def test_credentials_username_password_create_linked_account(db_fx):
    """Setting username/password on a teacher with no linked account creates one
    and enables immediate login (no activation code needed)."""
    svc, conn = _make_service(db_fx)
    tid = _insert_teacher_without_account(conn, academic_number='AN-IMP-1')
    ok = svc.update_teacher_credentials(tid, new_username='imported1', new_password='s3cret!')
    assert ok is True
    linked = conn.execute(
        'SELECT user_id FROM teachers WHERE id = ?', (tid,)
    ).fetchone()['user_id']
    assert linked is not None
    from services.user_service import UserService
    from database.repositories.user_repository import UserRepository
    ok2, sess = UserService(conn, UserRepository(conn)).authenticate('imported1', 's3cret!', False, {})
    assert ok2 is True
    assert sess['id'] == linked
    conn.close()


def test_credentials_username_only_creates_account_with_initial_code(db_fx):
    """A username-only update for an unlinked teacher issues an initial login
    code (hashed + expiring) instead of leaving the account with no password."""
    svc, conn = _make_service(db_fx)
    tid = _insert_teacher_without_account(conn, name='بدون كلمة مرور', academic_number='AN-IMP-2')
    ok = svc.update_teacher_credentials(tid, new_username='imported2')
    assert ok is True
    user = conn.execute(
        'SELECT * FROM users JOIN teachers t ON t.user_id = users.id WHERE t.id = ?', (tid,)
    ).fetchone()
    assert user['initial_login_code_hash']
    assert user['initial_login_code_used'] == 0
    assert user['initial_login_code_expires']
    assert user['force_password_change'] == 1
    conn.close()


def test_reset_password_creates_account_when_missing(db_fx):
    """Reset-password generates the account on demand for an unlinked teacher."""
    svc, conn = _make_service(db_fx)
    tid = _insert_teacher_without_account(conn, name='أستاذ معاد', academic_number='AN-IMP-3')
    new_code = svc.reset_teacher_password(tid)
    assert new_code
    user = conn.execute(
        'SELECT * FROM users JOIN teachers t ON t.user_id = users.id WHERE t.id = ?', (tid,)
    ).fetchone()
    assert user['force_password_change'] == 1
    assert user['initial_login_code_used'] == 0
    assert user['password'] != 'x'
    conn.close()
