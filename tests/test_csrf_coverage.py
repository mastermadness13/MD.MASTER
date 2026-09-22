"""CSRF coverage regression tests.

CSRF is enforced at the framework level in ``app.before_request`` (see
``app.enforce_csrf`` and ``security/csrf.is_request_protected``): every
state-changing request needs a valid per-session token unless the endpoint is
explicitly marked ``csrf_exempt``.

These tests lock down that invariant so a future route can't quietly turn a
write endpoint into an unprotected one.
"""

import pytest

from security.csrf import STATE_CHANGING_METHODS

STATE_CHANGING = set(STATE_CHANGING_METHODS)

# /     /     >---- قائمة الإعفاءات المراجعة يدوياً من CSRF (فارغة افتراضياً)
# Adding an exemption here requires a conscious security review; the test below
# fails for any ``csrf_exempt`` endpoint not listed here.
REVIEWED_CSRF_EXEMPT = set()


def _state_changing_endpoints(app):
    endpoints = set()
    for rule in app.url_map.iter_rules():
        methods = set(rule.methods or [])
        if methods & STATE_CHANGING and rule.endpoint:
            endpoints.add(rule.endpoint)
    return endpoints


def _framework_csrf_hooks(app):
    for fns in app.before_request_funcs.values():
        for fn in fns:
            if getattr(fn, '__name__', '') == 'enforce_csrf':
                return True
    return False


def test_framework_csrf_hook_is_registered(app_fx):
    assert _framework_csrf_hooks(app_fx), (
        'Framework-level CSRF enforcement (app.enforce_csrf) is not registered.'
    )


def test_every_exemption_is_reviewed(app_fx):
    """No endpoint may opt out of CSRF silently."""
    exempt = {
        rule.endpoint
        for rule in app_fx.url_map.iter_rules()
        if set(rule.methods or []) & STATE_CHANGING and rule.endpoint
        and getattr(app_fx.view_functions.get(rule.endpoint), '_csrf_exempt', False)
    }
    assert exempt <= REVIEWED_CSRF_EXEMPT, (
        f'csrf_exempt endpoints not in REVIEWED_CSRF_EXEMPT: {exempt - REVIEWED_CSRF_EXEMPT}'
    )


def test_every_state_changing_endpoint_resolves_to_a_view(app_fx):
    """Every write endpoint must map to a real view (no dead routes)."""
    unresolved = [
        ep for ep in _state_changing_endpoints(app_fx)
        if ep not in app_fx.view_functions
    ]
    assert not unresolved, f'Unresolved write endpoints: {unresolved}'


JSON_ACCEPT = {'Accept': 'application/json'}


def test_post_without_token_is_rejected(app_fx):
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r = c.post('/api/auth/login', json={'username': 'x', 'password': 'y'},
               headers=JSON_ACCEPT)
    assert r.status_code == 403
    assert r.get_json()['ok'] is False
    assert 'CSRF' in r.get_json()['message']


def test_post_with_wrong_token_is_rejected(app_fx):
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r = c.post('/api/auth/login',
               json={'username': 'x', 'password': 'y', '_csrf_token': 'wrong'},
               headers=JSON_ACCEPT)
    assert r.status_code == 403
    assert r.get_json()['ok'] is False


def test_post_with_valid_token_passes_csrf_stage(app_fx):
    """The token must be accepted; failures here must not be CSRF 403s."""
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r = c.post('/api/auth/login',
               json={'username': 'x', 'password': 'y', '_csrf_token': 'test-token'},
               headers=JSON_ACCEPT)
    assert r.status_code != 403, 'Valid CSRF token was rejected'


def test_html_post_without_token_redirects_not_json(app_fx):
    """Browser CSRF failure must flash + redirect, not return JSON."""
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    # /logout is public + state-changing: an unprotected POST must be blocked.
    r = c.post('/logout', data={}, follow_redirects=False)
    assert r.status_code == 302
    # Browser path falls back to the dashboard (no off-origin redirect).
    loc = r.headers.get('Location', '')
    assert loc.startswith('/'), f'CSRF failure redirected off-origin: {loc}'


def test_logout_is_post_only(app_fx):
    """GET /logout must no longer exist (CSRF-able logout via <img>)."""
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r = c.get('/logout')
    assert r.status_code == 405


@pytest.mark.parametrize('method,url', [
    ('PUT', '/api/rooms/1'),
    ('PATCH', '/api/exams/department-schedule/cell/1/room'),
    ('DELETE', '/api/rooms/1'),
])
def test_other_state_changing_methods_require_token(app_fx, method, url):
    """PUT/PATCH/DELETE without a token must be rejected at the framework
    layer before the view can run side effects."""
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['_csrf_token'] = 'test-token'
    r = c.open(url, method=method, json={}, headers=JSON_ACCEPT)
    assert r.status_code == 403, f'{method} {url} without token was not rejected'