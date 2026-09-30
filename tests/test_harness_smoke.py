"""Smoke tests for the shared harness itself.

The harness is load-bearing for the rest of this suite: if it silently builds
sessions that the app would not honour, every downstream test would pass for
the wrong reason.  These tests pin the properties the other files rely on.
"""

import pytest

from tests.harness import (
    ALL_ROLES,
    ROLE_ACCOUNTS,
    body_of,
    concrete_path,
    has_permission_for,
    json_headers,
    login_as,
    read_row,
    scalar,
)


# ── the harness builds a real, distinct account per role ───────────

@pytest.mark.parametrize('role', ALL_ROLES)
def test_every_role_has_an_account(seeded, role):
    """Each role resolves to a user row that exists and is active."""
    user_id = seeded['users'][role]
    row = read_row(
        seeded['db_path'],
        'SELECT id, role, is_active FROM users WHERE id = ?',
        (user_id,),
    )
    assert row is not None, f'role {role} has no user row'
    assert row['is_active'] == 1


def test_user_ids_are_unique_per_role(seeded):
    """Two roles never share a user id, so a session cannot be ambiguous."""
    ids = list(seeded['users'].values())
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize('role', ALL_ROLES)
def test_usernames_are_unique(seeded, role):
    """Usernames are unique across roles (schema enforces it, assert it too)."""
    username = ROLE_ACCOUNTS[role][0]
    count = scalar(
        seeded['db_path'],
        'SELECT COUNT(*) FROM users WHERE username = ?',
        (username,),
    )
    assert count == 1


def test_seeded_office_manager_is_not_reused_as_another_role(seeded):
    """The bootstrap account (id 1) is a different person from every harness role.

    This is the exact confusion that broke the older suite: it injected
    ``user_id=1`` and called it ``exam``, silently testing the office manager.
    """
    office = read_row(
        seeded['db_path'], 'SELECT id FROM users WHERE username = ?',
        ('office_manager',),
    )
    assert office is not None
    assert office['id'] not in seeded['users'].values()


# ── user_roles back each account ───────────────────────────────────

@pytest.mark.parametrize('role', ALL_ROLES)
def test_user_roles_row_exists(seeded, role):
    """``user_roles`` carries the granted set, which the app trusts over the session."""
    found = scalar(
        seeded['db_path'],
        'SELECT COUNT(*) FROM user_roles WHERE user_id = ? AND role = ?',
        (seeded['users'][role], role),
    )
    assert found == 1


# ── the seeded reference data is present ───────────────────────────

def test_departments_seeded(seeded):
    assert seeded['departments']['قسم الحاسوب']
    assert seeded['departments']['القسم العام']


def test_general_department_has_single_semester(seeded):
    """The general department is the one whose semester count is 1."""
    semesters = scalar(
        seeded['db_path'],
        'SELECT semesters FROM departments WHERE id = ?',
        (seeded['departments']['القسم العام'],),
    )
    assert semesters == 1


def test_course_and_room_seeded(seeded):
    assert seeded['course_id'] and seeded['room_id']
    assert scalar(
        seeded['db_path'], 'SELECT COUNT(*) FROM courses WHERE id = ?',
        (seeded['course_id'],),
    ) == 1
    assert scalar(
        seeded['db_path'], 'SELECT COUNT(*) FROM rooms WHERE id = ?',
        (seeded['room_id'],),
    ) == 1


# ── login_as produces a session the app accepts ────────────────────

@pytest.mark.parametrize('role', ALL_ROLES)
def test_login_as_session_is_accepted(app_fx, seeded, role):
    """A harness session is authenticated: no bounce back to /login."""
    client = login_as(app_fx, seeded['db_path'], role)
    response = client.get('/health')
    assert response.status_code == 200


@pytest.mark.parametrize('role', ALL_ROLES)
def test_login_as_stores_matching_user_id(app_fx, seeded, role):
    """The session's user_id is the row that actually holds the role."""
    client = login_as(app_fx, seeded['db_path'], role)
    with client.session_transaction() as sess:
        stored = sess['user_id']
    assert stored == seeded['users'][role]
    row = read_row(
        seeded['db_path'], 'SELECT role FROM users WHERE id = ?', (stored,)
    )
    assert row['role'] == role


def test_login_as_sets_csrf_token(app_fx, seeded):
    """Every harness client carries the shared CSRF token."""
    client = login_as(app_fx, seeded['db_path'], 'dean')
    with client.session_transaction() as sess:
        assert sess['_csrf_token']


def test_login_as_accepts_department_scope(app_fx, seeded):
    """A department-scoped session round-trips its department_id."""
    dept = seeded['departments']['قسم الحاسوب']
    client = login_as(
        app_fx, seeded['db_path'], 'head_of_department', department_id=dept,
    )
    with client.session_transaction() as sess:
        assert sess['department_id'] == dept


def test_login_as_supports_multi_role(app_fx, seeded):
    """A person who is both teacher and HOD keeps both roles in session."""
    client = login_as(
        app_fx, seeded['db_path'], 'head_of_department',
        extra_roles=('teacher',), active_role='teacher',
    )
    with client.session_transaction() as sess:
        assert set(sess['roles']) == {'head_of_department', 'teacher'}
        assert sess['role'] == 'teacher'


def test_login_as_can_force_password_change(app_fx, seeded):
    """The forced-change flag is honoured by the harness."""
    client = login_as(
        app_fx, seeded['db_path'], 'teacher', force_password_change=True,
    )
    with client.session_transaction() as sess:
        assert sess['force_password_change'] is True


# ── permission helper agrees with the constant map ─────────────────

@pytest.mark.parametrize('role', ALL_ROLES)
def test_has_permission_helper_matches_map(role):
    """The harness permission helper reads the real constant map."""
    from core.constants import ROLE_PERMISSIONS

    for permission in ROLE_PERMISSIONS.get(role, set()):
        assert has_permission_for(role, permission)
    assert not has_permission_for(role, 'definitely.not.a.permission')


# ── path concretisation ────────────────────────────────────────────

@pytest.mark.parametrize('rule,expected', [
    ('/api/courses/<int:course_id>', '/api/courses/1'),
    ('/api/courses/<int:course_id>/permanent', '/api/courses/1/permanent'),
    ('/teachers/<int:id>/teaching-record/<semester_code>',
     '/teachers/1/teaching-record/1'),
    ('/reset-password/<token>', '/reset-password/1'),
    ('/timetable/api/get-entry/<int:entry_id>', '/timetable/api/get-entry/1'),
])
def test_concrete_path_substitutes_converters(rule, expected):
    assert concrete_path(rule) == expected


def test_concrete_path_leaves_plain_paths_alone():
    assert concrete_path('/departments') == '/departments'
    assert concrete_path('/health') == '/health'


# ── response helpers ───────────────────────────────────────────────

def test_body_of_returns_text(app_fx, seeded):
    """``body_of`` works on a streamed test response."""
    client = login_as(app_fx, seeded['db_path'], 'dean')
    assert isinstance(body_of(client.get('/health')), str)


def test_json_headers_signal_json():
    """The JSON header bundle marks the caller as an API client."""
    headers = json_headers()
    assert headers['X-Requested-With'] == 'XMLHttpRequest'
    assert 'application/json' in headers['Accept']
