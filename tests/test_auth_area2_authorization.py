# -*- coding: utf-8 -*-
"""Area 2 (authentication and authorization) — session invalidation guards.

The Flask session is a *signed client-side cookie* that carries the granted
role set, and ``app.before_request``/``enforce_session_version`` re-reads the
``users`` row on every request to compare its ``session_version`` against the
one in the cookie. That counter was previously rotated only by a password
change, so a demotion, a revoked multi-role, or a disable/re-enable left the
already-issued cookie still exercising the old authority until it expired —
up to ``PERMANENT_SESSION_LIFETIME`` (7 days).

Any method that changes what an account may do must therefore bump the
counter. These tests pin that contract twice: at the repository mutation, and
end-to-end on a live session cookie.
"""

import ast
import logging
import pathlib

import pytest

import flask_db
from database.connection import connect
from database.repositories.user_repository import UserRepository
from database.schema import ensure_schema
from page_routes.auth_pages import _build_reset_url

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Methods that change authority without needing a bump, and why:
#   create_user  — a brand-new row cannot have a live session yet.
#   delete_user  — the row is removed, so enforce_session_version takes its
#                  missing-row branch and clears the cookie on its own.
_NO_BUMP_REQUIRED = {'create_user', 'delete_user'}


@pytest.fixture
def repo_db(tmp_path):
    """A throwaway database with one user holding a single role."""
    db_path = tmp_path / 'area2_authz.db'
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.execute(
        "INSERT INTO users (username, password, role, label) "
        "VALUES ('area2_user', 'x', 'faculty_affairs', 'مكتب')"
    )
    uid = conn.execute(
        "SELECT id FROM users WHERE username = 'area2_user'"
    ).fetchone()['id']
    conn.execute(
        "INSERT INTO user_roles (user_id, role) VALUES (?, 'faculty_affairs')",
        (uid,),
    )
    conn.commit()
    yield conn, UserRepository(conn)
    conn.close()


def _version(conn, user_id):
    return conn.execute(
        'SELECT session_version FROM users WHERE id = ?', (user_id,)
    ).fetchone()['session_version']


# ── the counter itself ───────────────────────────────────────────────────


def test_fresh_user_starts_at_version_one(repo_db):
    conn, _ = repo_db
    uid = conn.execute(
        "SELECT id FROM users WHERE username = 'area2_user'"
    ).fetchone()['id']
    assert _version(conn, uid) == 1


def test_role_change_bumps_session_version(repo_db):
    conn, repo = repo_db
    uid = conn.execute(
        "SELECT id FROM users WHERE username = 'area2_user'"
    ).fetchone()['id']
    repo.update_user(uid, {'role': 'teacher'})
    assert _version(conn, uid) == 2


def test_department_change_bumps_session_version(repo_db):
    conn, repo = repo_db
    uid = conn.execute(
        "SELECT id FROM users WHERE username = 'area2_user'"
    ).fetchone()['id']
    repo.update_user(uid, {'department_id': 3})
    assert _version(conn, uid) == 2


def test_replacing_the_role_set_bumps_session_version(repo_db):
    conn, repo = repo_db
    uid = conn.execute(
        "SELECT id FROM users WHERE username = 'area2_user'"
    ).fetchone()['id']
    repo.set_user_roles(uid, ['teacher'])
    assert _version(conn, uid) == 2


def test_adding_and_removing_a_single_role_bump_session_version(repo_db):
    conn, repo = repo_db
    uid = conn.execute(
        "SELECT id FROM users WHERE username = 'area2_user'"
    ).fetchone()['id']
    repo.add_user_role(uid, 'head_of_department')
    assert _version(conn, uid) == 2
    repo.remove_user_role(uid, 'faculty_affairs')
    assert _version(conn, uid) == 3


def test_disable_and_reenable_both_bump_session_version(repo_db):
    """Re-enabling must not resurrect a cookie captured while disabled."""
    conn, repo = repo_db
    uid = conn.execute(
        "SELECT id FROM users WHERE username = 'area2_user'"
    ).fetchone()['id']
    repo.set_user_active(uid, False)
    assert _version(conn, uid) == 2
    repo.set_user_active(uid, True)
    assert _version(conn, uid) == 3


def test_profile_only_update_keeps_the_session(repo_db):
    """Not every profile edit should force a re-login."""
    conn, repo = repo_db
    uid = conn.execute(
        "SELECT id FROM users WHERE username = 'area2_user'"
    ).fetchone()['id']
    repo.update_user(uid, {'email': 'new@example.edu', 'label': 'مكتبDean'})
    assert _version(conn, uid) == 1


def test_password_change_still_bumps_session_version(repo_db):
    conn, repo = repo_db
    uid = conn.execute(
        "SELECT id FROM users WHERE username = 'area2_user'"
    ).fetchone()['id']
    repo.update_password(uid, 'scrypt:whatever')
    assert _version(conn, uid) == 2


# ── end-to-end: the boundary the fix is actually about ──────────────────


@pytest.fixture
def live_client(tmp_path, app_fx, monkeypatch):
    """A client whose session cookie carries a real, matching user row."""
    db_path = tmp_path / 'area2_live.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.execute(
        "INSERT INTO users (username, password, role, label) "
        "VALUES ('area2_live', 'x', 'faculty_affairs', 'مكتب')"
    )
    uid = conn.execute(
        "SELECT id FROM users WHERE username = 'area2_live'"
    ).fetchone()['id']
    conn.execute(
        "INSERT INTO user_roles (user_id, role) VALUES (?, 'faculty_affairs')",
        (uid,),
    )
    conn.commit()
    conn.close()

    client = app_fx.test_client()
    with client.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
        sess['user_id'] = uid
        sess['role'] = 'faculty_affairs'
        sess['roles'] = ['faculty_affairs']
    yield client, uid, db_path
    conn = connect(str(db_path))
    conn.close()


def test_office_role_reaches_the_teachers_page(live_client):
    client, _, _ = live_client
    assert client.get('/teachers').status_code == 200


def test_demoted_session_is_bounced_to_login(live_client):
    """The regression: a live cookie must stop working after a demotion."""
    client, uid, db_path = live_client
    assert client.get('/teachers').status_code == 200

    conn = connect(str(db_path))
    repo = UserRepository(conn)
    repo.update_user(uid, {'role': 'teacher'})
    repo.set_user_roles(uid, ['teacher'])
    conn.close()

    response = client.get('/teachers')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']
    with client.session_transaction() as sess:
        assert 'user_id' not in sess


def test_revoked_role_is_bounced_to_login(live_client):
    client, uid, db_path = live_client
    assert client.get('/teachers').status_code == 200

    conn = connect(str(db_path))
    UserRepository(conn).remove_user_role(uid, 'faculty_affairs')
    conn.close()

    assert client.get('/teachers').status_code == 302


def test_disabled_account_is_bounced_to_login(live_client):
    client, uid, db_path = live_client
    assert client.get('/teachers').status_code == 200

    conn = connect(str(db_path))
    UserRepository(conn).set_user_active(uid, False)
    conn.close()

    assert client.get('/teachers').status_code == 302


# ── password-reset link origin ──────────────────────────────────────────


def test_reset_link_ignores_a_forged_host_when_base_is_configured(
    app_fx, monkeypatch
):
    """The reset link is a bearer credential: its origin must be configured."""
    monkeypatch.setitem(
        app_fx.config, 'RESET_BASE_URL', 'https://portal.example.edu'
    )
    with app_fx.test_request_context(
        '/forgot-password', headers={'Host': 'attacker.example'}
    ):
        url = _build_reset_url('TOKEN123')
    assert url == 'https://portal.example.edu/reset-password/TOKEN123'
    assert 'attacker.example' not in url


def test_reset_link_tolerates_a_trailing_slash_in_the_base(app_fx, monkeypatch):
    monkeypatch.setitem(
        app_fx.config, 'RESET_BASE_URL', 'https://portal.example.edu/'
    )
    with app_fx.test_request_context('/forgot-password'):
        assert _build_reset_url('T') == 'https://portal.example.edu/reset-password/T'


def test_reset_link_falls_back_to_the_request_host_but_warns(
    app_fx, monkeypatch, caplog
):
    """Unset base keeps local development working; the risk is logged."""
    monkeypatch.setitem(app_fx.config, 'RESET_BASE_URL', '')
    with caplog.at_level(logging.WARNING, logger='page_routes.auth_pages'):
        with app_fx.test_request_context(
            '/forgot-password', headers={'Host': 'attacker.example'}
        ):
            url = _build_reset_url('TOKEN123')
    assert 'attacker.example' in url
    assert any('RESET_BASE_URL' in r.message for r in caplog.records)


# ── durable guard against reintroducing the defect ──────────────────────


def test_every_authority_mutation_rotates_the_session_counter():
    """Any new method that writes role/authority must also bump the counter.

    A repository method can grant or revoke authority without going near a
    route, so the routes cannot police this. This walks the class and fails on
    a writer that forgets, which is how the original defect stayed invisible.
    """
    path = ROOT / 'database' / 'repositories' / 'user_repository.py'
    src = path.read_text(encoding='utf-8')
    tree = ast.parse(src)
    cls = next(
        n for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == 'UserRepository'
    )

    missing = []
    for fn in cls.body:
        if not isinstance(fn, ast.FunctionDef) or fn.name in _NO_BUMP_REQUIRED:
            continue
        text = ast.get_source_segment(src, fn) or ''
        writes = any(
            kw in text for kw in ('INSERT', 'UPDATE', 'DELETE', 'REPLACE')
        )
        touches_authority = any(
            tok in text for tok in ("'role'", '"role"', 'user_roles', 'is_active')
        )
        if not (writes and touches_authority):
            continue
        rotates = (
            '_bump_session_version' in text
            or 'session_version = session_version + 1' in text
        )
        if not rotates:
            missing.append(fn.name)

    assert missing == [], (
        'authority-mutating repository methods that do not rotate '
        f'session_version (live sessions would keep the old role): {missing}'
    )
