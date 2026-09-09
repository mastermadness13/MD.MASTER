"""Tests for multi-role grants and super-admin protection.

The standalone ``/users`` page was removed in the multi-role overhaul and
account/role management moved into the teacher create/edit flow.  These tests
cover the two durable behaviours that live at the service layer:

  1. The super-admin account is protected against every destructive action
     (delete, deactivate, demote, strip the super_admin role) even when called
     directly — not just hidden in the UI.
  2. Creating a teacher grants the landing ``teacher`` role plus any selected
     additional roles into the ``user_roles`` table.
"""

import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema
from core.exceptions import ProtectedAccountError
from database.repositories.user_repository import UserRepository
from database.repositories.teacher_repository import TeacherRepository
from services.user_service import UserService
from services import teacher_service


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'roles.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) "
        "VALUES ('superadmin', 'x', 'super_admin', 'مدير')"
    )
    conn.commit()
    conn.close()
    return str(db_path)


@pytest.fixture
def svc(db_fx):
    conn = sqlite3.connect(db_fx)
    conn.row_factory = sqlite3.Row
    repo = UserRepository(conn)
    return UserService(conn, repo), conn


def _q(path, sql, params=()):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


# ── Super-admin protection ──────────────────────────────────────────────


def test_superadmin_recognised_as_protected(db_fx, svc):
    user_service, conn = svc
    super_id = _q(db_fx, "SELECT id FROM users WHERE role='super_admin'")[0]['id']
    assert user_service.is_protected_user(super_id) is True


def test_regular_user_not_protected(db_fx, svc):
    user_service, conn = svc
    conn.execute(
        "INSERT INTO users (username, password, role, label) VALUES ('t1', 'x', 'teacher', 'مدرس')"
    )
    conn.commit()
    uid = _q(db_fx, "SELECT id FROM users WHERE username='t1'")[0]['id']
    assert user_service.is_protected_user(uid) is False


def test_cannot_delete_superadmin(db_fx, svc):
    user_service, conn = svc
    super_id = _q(db_fx, "SELECT id FROM users WHERE role='super_admin'")[0]['id']
    with pytest.raises(ProtectedAccountError):
        user_service.delete_user(super_id)
    assert _q(db_fx, "SELECT id FROM users WHERE role='super_admin'")


def test_cannot_deactivate_superadmin(db_fx, svc):
    user_service, conn = svc
    super_id = _q(db_fx, "SELECT id FROM users WHERE role='super_admin'")[0]['id']
    with pytest.raises(ProtectedAccountError):
        user_service.set_user_active(super_id, False)
    assert _q(db_fx, 'SELECT is_active FROM users WHERE id=?', (super_id,))[0]['is_active'] == 1


def test_cannot_demote_superadmin(db_fx, svc):
    user_service, conn = svc
    super_id = _q(db_fx, "SELECT id FROM users WHERE role='super_admin'")[0]['id']
    with pytest.raises(ProtectedAccountError):
        user_service.update_user_with_profile(
            super_id, 'superadmin', 'teacher', None, '', 'مدير'
        )
    assert _q(db_fx, 'SELECT role FROM users WHERE id=?', (super_id,))[0]['role'] == 'super_admin'


def test_cannot_strip_superadmin_role(db_fx, svc):
    user_service, conn = svc
    super_id = _q(db_fx, "SELECT id FROM users WHERE role='super_admin'")[0]['id']
    with pytest.raises(ProtectedAccountError):
        user_service.set_user_roles(super_id, ['teacher'])
    assert 'super_admin' in _q(
        db_fx, 'SELECT role FROM user_roles WHERE user_id=?', (super_id,)) \
        or _q(db_fx, 'SELECT role FROM users WHERE id=?', (super_id,))[0]['role'] == 'super_admin'


# ── Multi-role grant via teacher create ────────────────────────────────


def _tdata(ac, name='عضو تجريبي'):
    return {
        'name': name, 'academic_number': ac, 'email': 'a@b.c', 'phone': '000',
        'department_id': None, 'qualification_id': None, 'rank_id': None,
        'classification_id': None, 'national_id': None, 'contract_date': None,
        'tasks': None,
    }


def test_create_teacher_grants_teacher_plus_extras(db_fx):
    conn = sqlite3.connect(db_fx)
    conn.row_factory = sqlite3.Row
    svc = teacher_service.TeacherService(conn, TeacherRepository(conn), UserRepository(conn))
    teacher_service.create_teacher(
        conn, _tdata('ACC-9001'),
        department_ids=None, additional_roles=['exam', 'head_of_department'],
    )
    t = _q(db_fx, "SELECT id, user_id FROM teachers WHERE academic_number='ACC-9001'")[0]
    roles = sorted(r['role'] for r in _q(
        db_fx, 'SELECT role FROM user_roles WHERE user_id=?', (t['user_id'],)))
    assert roles == ['exam', 'head_of_department', 'teacher']
    conn.close()


def test_create_teacher_without_extras_still_has_teacher_role(db_fx):
    conn = sqlite3.connect(db_fx)
    conn.row_factory = sqlite3.Row
    svc = teacher_service.TeacherService(conn, TeacherRepository(conn), UserRepository(conn))
    teacher_service.create_teacher(conn, _tdata('ACC-9002'), department_ids=None, additional_roles=None)
    t = _q(db_fx, "SELECT id, user_id FROM teachers WHERE academic_number='ACC-9002'")[0]
    roles = sorted(r['role'] for r in _q(
        db_fx, 'SELECT role FROM user_roles WHERE user_id=?', (t['user_id'],)))
    assert roles == ['teacher']
    conn.close()