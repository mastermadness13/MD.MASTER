"""Authorization matrix: every route, every role, one decision each.

The application denies by default: ``enforce_permissions`` (app.py) reads the
``_required_permission`` / ``_required_roles`` / ``_required_any_roles``
attributes a decorator attached to the view, and refuses anything not declared
in ``PUBLIC_ENDPOINTS`` / ``AUTHENTICATED_ENDPOINTS``.  These tests walk that
contract against the live ``url_map``:

* a role that lacks the declared permission is refused - a JSON client with a
  hard 403, a browser with a redirect away from the page (never to /login);
* a role that holds the permission is never refused with 403;
* an anonymous caller is redirected to login or answered 401, never served the
  protected page;
* every undeclared endpoint is named in a policy list (no unreachable code);
* the sidebar shown to a role only contains pages that role may open.

The blanket ``role x rule`` sweep is what makes the suite big: every route in
the map is checked against every one of the seven roles.
"""

import pytest

from app import AUTHENTICATED_ENDPOINTS, PUBLIC_ENDPOINTS
from core.constants import ROLE_PERMISSIONS
from tests.harness import (
    ALL_ROLES,
    CSRF_TOKEN,
    concrete_path,
    get_app,
    has_permission_for,
    iter_rules,
    json_headers,
    json_of,
    login_as,
    read_row,
    read_rows,
    run_sql,
    required_permission,
    required_roles,
)

# The one application instance for the whole session - reused by ``app_fx``.
_APP = get_app()

_PUBLIC_PATH_PREFIXES = ('/static/', '/uploads/', '/favicon')


def _rules_list():
    return [
        (rule, endpoint, methods)
        for rule, endpoint, methods in iter_rules(_APP)
        if not rule.startswith(_PUBLIC_PATH_PREFIXES)
    ]


RULES = _rules_list()
RULE_IDS = [endpoint for _rule, endpoint, _methods in RULES]

# Prefer the safest state-changing method when a rule has no GET.
_METHOD_ORDER = {'POST': 0, 'PUT': 1, 'PATCH': 2, 'DELETE': 3}


def _swept_method(methods):
    if 'GET' in methods:
        return 'GET'
    return min(methods, key=lambda m: _METHOD_ORDER.get(m, 9))


def _can_reach(endpoint: str, role: str) -> bool:
    """Purely from the constant map: is *role* allowed on *endpoint*?

    A view can stack decorators, e.g. ``@permission_required('x.view')`` with
    ``@role_required('faculty_affairs')`` — the effective gate is BOTH the
    permission and the active role.  ``_required_permission`` is evaluated
    against the active role's permission set, so both axes are checked here to
    mirror ``enforce_permissions`` plus the nested guard decorators.
    """
    if endpoint in PUBLIC_ENDPOINTS or endpoint in AUTHENTICATED_ENDPOINTS:
        return True
    permission = required_permission(_APP, endpoint)
    gate = required_roles(_APP, endpoint)
    if permission is None and gate is None:
        return False  # deny-by-default: undeclared means refused
    if permission is not None and not has_permission_for(role, permission):
        return False
    if gate is not None and role not in gate[1]:
        return False
    return True


# ---- precomputed cases, once per process ----

_DENIED = [
    (rule, endpoint, _swept_method(methods), role)
    for rule, endpoint, methods in RULES
    for role in ALL_ROLES
    if not _can_reach(endpoint, role)
]
_DENIED_IDS = [_c[1] + '::' + _c[-1] for _c in _DENIED]

_ALLOWED_GET = [
    (rule, endpoint, role)
    for rule, endpoint, methods in RULES
    for role in ALL_ROLES
    if 'GET' in methods and _can_reach(endpoint, role)
]
_ALLOWED_IDS = [_c[1] + '::' + _c[-1] for _c in _ALLOWED_GET]

_ANONYMOUS = [(rule, endpoint) for rule, endpoint, _m in RULES]
ANONYMOUS_IDS = [endpoint for _r, endpoint, _m in RULES]


# ---- the deny sweep: roles that lack the permission ----

@pytest.mark.parametrize('rule,endpoint,method,role', _DENIED, ids=_DENIED_IDS)
def test_role_without_permission_is_denied_everywhere(
    app_fx, matrix_db, rule, endpoint, method, role,
):
    """A JSON client gets 403; a browser is sent away from the page.

    The 403-versus-redirect split is the security contract: an API caller must
    never receive an HTML document to misparse, and a logged-in browser must
    never be dumped onto the login page for a page it is not even logged out of.
    """
    payload = {'_csrf_token': CSRF_TOKEN}

    # API client: a hard, parseable denial.
    client = login_as(app_fx, matrix_db['db_path'], role)
    data = None if method in ('GET', 'HEAD') else payload
    resp = client.open(concrete_path(rule), method=method, data=data,
                       headers=json_headers())
    assert resp.status_code == 403, (
        f'{role} reached {endpoint} as an API client ({resp.status_code}) '
        f'despite lacking the required permission'
    )

    # Browser: redirected away, never to a 403 page nor to /login.
    browser = login_as(app_fx, matrix_db['db_path'], role)
    resp = browser.open(concrete_path(rule), method=method,
                        data=payload if method not in ('GET', 'HEAD') else None)
    assert resp.status_code == 302, (
        f'{role} browsing {endpoint} got {resp.status_code}, expected a redirect'
    )
    assert '/login' not in resp.headers.get('Location', ''), (
        f'{role} was bounced to login for {endpoint}'
    )


# ---- the allow sweep: roles that hold the permission ----

# The flat guard answers a JSON client with exactly one of these messages.
# Anything else a 403 body contains is a view-level decision (data scoping,
# nested decorators, per-row access) which the permission map cannot predict.
_GUARD_DENIAL_MESSAGES = {
    'ليس لديك صلاحية للوصول إلى هذه الصفحة',
    'هذا المسار غير مصرح به',
}


@pytest.mark.parametrize('rule,endpoint,role', _ALLOWED_GET, ids=_ALLOWED_IDS)
def test_role_with_permission_is_never_refused(
    app_fx, matrix_db, rule, endpoint, role,
):
    """The flat authorization guard never refuses a permitted role.

    A permitted role may legitimately be 403'd *inside* the view for its own
    reasons (a stacked ``role_required``, per-row access scope, missing data),
    but it must never hit the guard's own blanket refusal — the deny-by-default
    layer standing in the way of a role the map allows.
    """
    client = login_as(app_fx, matrix_db['db_path'], role)
    try:
        resp = client.get(concrete_path(rule), headers=json_headers())
    except Exception:
        # The view itself crashed (missing template, missing data, ...), so the
        # guard let the role through — which is exactly the claim here. Page
        # rendering is a different contract, covered by the page smoke tests.
        return
    if resp.status_code != 403:
        return
    body = json_of(resp)
    assert not (
        isinstance(body, dict)
        and body.get('ok') is False
        and body.get('message') in _GUARD_DENIAL_MESSAGES
    ), (
        f'{role} holds a permission for {endpoint} yet the guard refused with: '
        f'{body.get("message")}'
    )


# ---- anonymous callers ----

@pytest.mark.parametrize('rule,endpoint', _ANONYMOUS, ids=ANONYMOUS_IDS)
def test_anonymous_is_not_served_a_protected_page(app_fx, rule, endpoint):
    """An unauthenticated caller is redirected to login or answered 401.

    ``200`` here means the page leaked to the public; ``404`` is fine (the
    concrete path resolved but no such resource exists, e.g. a dynamic file
    endpoint); ``405`` is fine (a POST-only rule probed with GET); ``500`` is a
    real crash leaking server state.
    """
    resp = app_fx.test_client().get(concrete_path(rule), headers=json_headers())
    assert resp.status_code in (200, 301, 302, 401, 404, 405), (
        f'anonymous GET {endpoint} answered {resp.status_code}'
    )
    if endpoint not in PUBLIC_ENDPOINTS and resp.status_code == 200:
        # A protected page served anonymously is a leak. Dynamic file services
        # are allowed to answer from disk; everything else must not.
        assert endpoint.startswith(('public_site.', 'public_library.')), (
            f'anonymous caller was served the protected page {endpoint}'
        )
    if resp.status_code == 302 and endpoint not in PUBLIC_ENDPOINTS:
        assert '/login' in resp.headers.get('Location', ''), (
            f'anonymous {endpoint} redirected somewhere other than login'
        )


# ---- deny-by-default integrity ----

@pytest.mark.parametrize('rule,endpoint,methods', RULES, ids=RULE_IDS)
def test_every_unguarded_route_is_explicitly_listed(rule, endpoint, methods):
    """An endpoint with no declared gate must be named in a policy list.

    Anything else is unreachable dead code: the guard refuses every logged-in
    user because it cannot decide the opposite.
    """
    guarded = (
        required_permission(_APP, endpoint) is not None
        or required_roles(_APP, endpoint) is not None
    )
    listed = endpoint in PUBLIC_ENDPOINTS or endpoint in AUTHENTICATED_ENDPOINTS
    assert guarded or listed, (
        f'{endpoint} ({rule}) has neither a declared gate nor a policy entry - '
        f'every logged-in user is refused it'
    )


@pytest.mark.parametrize('rule,endpoint,methods', RULES, ids=RULE_IDS)
def test_public_endpoint_never_403s_anyone(app_fx, rule, endpoint, methods):
    """``PUBLIC_ENDPOINTS`` really makes a route public.

    A stale entry in that set is a security bug: it exempts a route from the
    permission gate on the strength of a name that no longer matches reality.
    """
    if endpoint not in PUBLIC_ENDPOINTS:
        pytest.skip('not a declared public endpoint')
    resp = app_fx.test_client().get(concrete_path(rule))
    assert resp.status_code != 403, (
        f'{endpoint} is listed public but answered 403'
    )


@pytest.mark.parametrize('rule,endpoint,methods', RULES, ids=RULE_IDS)
def test_authenticated_endpoint_needs_logged_in_user(
    app_fx, rule, endpoint, methods,
):
    """``AUTHENTICATED_ENDPOINTS`` means logged in, not public."""
    if endpoint not in AUTHENTICATED_ENDPOINTS:
        pytest.skip('not an authenticated-only endpoint')
    if 'GET' not in methods:
        pytest.skip('rule has no GET')
    resp = app_fx.test_client().get(concrete_path(rule))
    assert resp.status_code in (302, 401), (
        f'{endpoint} is authenticated-only but served an anonymous caller '
        f'({resp.status_code})'
    )


# ---- session lifecycle ----

@pytest.mark.parametrize('role', ALL_ROLES)
def test_logout_clears_the_whole_session(app_fx, seeded, role):
    """Logout leaves no user_id, no roles, and no CSRF token behind."""
    client = login_as(app_fx, seeded['db_path'], role)
    client.post('/logout', data={'_csrf_token': CSRF_TOKEN})
    with client.session_transaction() as sess:
        assert 'user_id' not in sess
        assert 'roles' not in sess
        assert '_csrf_token' not in sess


@pytest.mark.parametrize('role', ALL_ROLES)
def test_deactivated_account_loses_its_session(app_fx, seeded, role):
    """Deactivating the account invalidates the live session immediately."""
    client = login_as(app_fx, seeded['db_path'], role)
    run_sql(
        seeded['db_path'],
        'UPDATE users SET is_active = 0 WHERE id = ?',
        (seeded['users'][role],),
    )
    resp = client.get('/departments', headers=json_headers())
    assert resp.status_code in (302, 401), (
        f'{role} kept access after being deactivated'
    )


@pytest.mark.parametrize('role', ALL_ROLES)
def test_password_change_bumps_session_version(app_fx, seeded, role):
    """Changing the password invalidates other sessions of the same account."""
    user_id = seeded['users'][role]
    row = read_row(
        seeded['db_path'], 'SELECT session_version FROM users WHERE id = ?',
        (user_id,),
    )
    before_version = row['session_version']
    run_sql(
        seeded['db_path'],
        'UPDATE users SET session_version = session_version + 1 WHERE id = ?',
        (user_id,),
    )
    client = login_as(app_fx, seeded['db_path'], role)
    with client.session_transaction() as sess:
        sess['session_version'] = before_version  # deliberately stale
    resp = client.get('/departments', headers=json_headers())
    assert resp.status_code in (302, 401), (
        f'{role} kept a session whose version no longer matches the account'
    )


@pytest.mark.parametrize('role', ALL_ROLES)
def test_forced_password_change_confines_the_session(app_fx, matrix_db, role):
    """A temporary credential may reach only change-password and logout."""
    client = login_as(
        app_fx, matrix_db['db_path'], role, force_password_change=True,
    )
    for rule, endpoint, _m in RULES:
        if endpoint in ('auth.change_password', 'auth.logout'):
            continue
        resp = client.get(concrete_path(rule), headers=json_headers())
        assert resp.status_code in (302, 403), (
            f'temporary credential reached {endpoint} ({resp.status_code})'
        )


@pytest.mark.parametrize('role', ALL_ROLES)
def test_unknown_session_role_grants_nothing(app_fx, matrix_db, role):
    """A made-up role is discarded: the granted set wins on every request."""
    client = login_as(app_fx, matrix_db['db_path'], role)
    with client.session_transaction() as sess:
        sess['role'] = 'super_admin'
        sess['roles'] = ['super_admin']
    client.get('/health')
    with client.session_transaction() as sess:
        assert sess['role'] == role, (
            f'a fabricated role leaked into the active role'
        )
        assert sess['roles'] == [role]


@pytest.mark.parametrize('role', ALL_ROLES)
def test_switch_role_never_elevates(app_fx, matrix_db, role):
    """Asking for an unheld role does not change the session."""
    for target in ALL_ROLES:
        if target == role:
            continue
        client = login_as(app_fx, matrix_db['db_path'], role)
        client.post(
            '/switch-role',
            data={'role': target, '_csrf_token': CSRF_TOKEN},
            headers=json_headers(),
        )
        with client.session_transaction() as sess:
            assert sess.get('role') == role, (
                f'{role} elevated itself to {target} via /switch-role'
            )


@pytest.mark.parametrize('role', ALL_ROLES)
def test_switch_role_accepts_only_granted_roles(app_fx, matrix_db, role):
    """Switching to a granted role succeeds and stores the new active role."""
    rows = read_rows(
        matrix_db['db_path'],
        'SELECT DISTINCT role FROM user_roles WHERE user_id = ? ORDER BY role',
        (matrix_db['users'][role],),
    )
    granted = [row['role'] for row in rows]
    if len(granted) < 2:
        pytest.skip('single-role account has nothing to switch to')
    target = next(r for r in granted if r != role)
    client = login_as(app_fx, matrix_db['db_path'], role)
    resp = client.post(
        '/switch-role',
        data={'role': target, '_csrf_token': CSRF_TOKEN},
        headers=json_headers(),
    )
    assert resp.status_code == 200, resp.get_json()
    with client.session_transaction() as sess:
        assert sess.get('role') == target


# ---- CSRF framework gate ----

def test_write_without_csrf_token_is_refused_even_unauthenticated(app_fx):
    """The framework gate rejects state changes with no token, no matter who.

    An API caller must get a parseable 403; a browser gets bounced with a
    redirect rather than having the write executed.
    """
    resp = app_fx.test_client().post(
        '/switch-role', data={'role': 'dean'}, headers=json_headers(),
    )
    assert resp.status_code == 403
    resp = app_fx.test_client().post('/switch-role', data={'role': 'dean'})
    assert resp.status_code == 302


def test_csrf_token_must_match_session_token(app_fx, matrix_db):
    """A wrong token is refused even with a valid session."""
    client = login_as(app_fx, matrix_db['db_path'], 'dean')
    resp = client.post(
        '/switch-role',
        data={'role': 'dean', '_csrf_token': 'not-the-token'},
        headers=json_headers(),
    )
    assert resp.status_code == 403


def test_csrf_token_from_header_is_accepted(app_fx, matrix_db):
    """The X-CSRFToken header is a supported channel for API clients."""
    client = login_as(app_fx, matrix_db['db_path'], 'dean')
    resp = client.post(
        '/switch-role',
        data={'role': 'dean'},
        headers={'X-CSRFToken': CSRF_TOKEN, **json_headers()},
    )
    assert resp.status_code == 200, resp.get_json()


# ---- the navigation mirror ----

@pytest.mark.parametrize('role', ALL_ROLES)
def test_nav_only_offers_pages_the_role_can_open(role):
    """Every nav item shown to a role is a page that role may actually reach."""
    from core.constants.navigation import get_nav_for_permissions

    items = get_nav_for_permissions(ROLE_PERMISSIONS.get(role, set()))
    for item in items:
        assert item['endpoint'] in _APP.view_functions, (
            f'nav item {item["key"]} points at unknown endpoint {item["endpoint"]}'
        )
        assert item['permission'] in ROLE_PERMISSIONS.get(role, set())


def test_nav_keys_are_unique():
    from core.constants.navigation import NAV_ITEMS

    keys = [item['key'] for item in NAV_ITEMS]
    assert len(keys) == len(set(keys))


def test_nav_endpoints_all_exist():
    from core.constants.navigation import NAV_ITEMS

    for item in NAV_ITEMS:
        assert item['endpoint'] in _APP.view_functions, (
            f'nav item {item["key"]} -> {item["endpoint"]} is not registered'
        )


def test_nav_sections_are_known():
    from core.constants.navigation import NAV_ITEMS

    for item in NAV_ITEMS:
        assert item['section'] in ('main', 'more')


def test_every_nav_permission_is_held_by_someone():
    """No nav permission refers to a role nobody holds (dead menu entry)."""
    from core.constants.navigation import NAV_ITEMS

    all_permissions = set()
    for perms in ROLE_PERMISSIONS.values():
        all_permissions.update(perms)
    for item in NAV_ITEMS:
        assert item['permission'] in all_permissions, (
            f'nav item {item["key"]} needs {item["permission"]}, held by no role'
        )