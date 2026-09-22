"""Deferred-hardening follow-ups — the "low-risk only" set.

M2: authenticate() must run a password-hash check even for unknown usernames.
M3: create_password_reset() runs one dummy hash unconditionally.
M4: proxy headers are honored ONLY from allow-listed peers (wsgi_proxy).
M10: CSP gains base-uri/object-src/form-action hardening.
L9: templates/public/ dead duplicate is gone; static/ is the single source.
"""

import json

import pytest

from core.wsgi_proxy import build_wsgi_chain
from services import user_service


class _FakeRepo:
    """Repo stub returning a fixed "unknown user" for lookup methods."""

    def __init__(self, user=None):
        self.user = user

    def find_by_username(self, username):
        return self.user

    def find_by_username_or_email(self, username):
        return self.user


@pytest.fixture
def dummy_repo():
    return _FakeRepo(user=None)


# ── M2 / M3: constant-time lookups ──────────────────────────────────────────


def test_authenticate_unknown_user_still_checks_hash(monkeypatch, dummy_repo):
    calls = []

    def _counting(pw_hash, password):
        calls.append(password)
        return True  # pretend match so we reach the `not user` guard

    monkeypatch.setattr(user_service, 'check_password_hash', _counting)
    svc = user_service.UserService(db=None, user_repository=dummy_repo)
    ok, user = svc.authenticate('ghost', 'wrong', remember=False, session_dict={})
    assert ok is False and user is None
    assert calls == ['wrong']


def test_create_password_reset_unknown_user_still_checks_hash(monkeypatch, dummy_repo):
    calls = []
    monkeypatch.setattr(user_service, 'check_password_hash',
                        lambda *a: calls.append(a))
    svc = user_service.UserService(db=None, user_repository=dummy_repo)
    assert svc.create_password_reset('ghost@example.com') is None
    assert len(calls) == 1


# ── M4: trusted-proxy WSGI chain ─────────────────────────────────────────────


def _dummy_wsgi(recorder):
    def app(environ, start_response):
        recorder.append(dict(environ))
        start_response('200 OK', [('Content-Type', 'text/plain')])
        return [b'ok']
    return app


def _hit(wsgi_app, recorder, remote_addr='1.1.1.1', xff='5.6.7.8'):
    environ = {
        'REQUEST_METHOD': 'GET',
        'REMOTE_ADDR': remote_addr,
        'HTTP_X_FORWARDED_FOR': xff,
        'HTTP_X_FORWARDED_PROTO': 'https',
        'HTTP_X_FORWARDED_HOST': 'evil.example',
    }

    def start_response(status, headers):
        pass

    wsgi_app(environ, start_response)
    return recorder[0]


def test_proxy_disabled_returns_app_unwrapped():
    app = _dummy_wsgi([])
    assert build_wsgi_chain(app, trust_proxy_headers=False) is app


def test_proxy_without_allowlist_is_failsafe(monkeypatch):
    app = _dummy_wsgi([])
    warned = []
    monkeypatch.setattr('core.wsgi_proxy.logger.warning',
                        lambda msg: warned.append(msg))
    assert build_wsgi_chain(app, trust_proxy_headers=True, trusted_proxy_ips='') is app
    assert warned


def test_trusted_peer_gets_proxy_fix():
    recorder = []
    chain = build_wsgi_chain(
        _dummy_wsgi(recorder),
        trust_proxy_headers=True,
        trusted_proxy_ips='10.0.0.1, 10.0.0.2',
    )
    seen = _hit(chain, recorder, remote_addr='10.0.0.1', xff='5.6.7.8')
    assert seen['REMOTE_ADDR'] == '5.6.7.8'


def test_untrusted_peer_is_served_untouched():
    recorder = []
    chain = build_wsgi_chain(
        _dummy_wsgi(recorder),
        trust_proxy_headers=True,
        trusted_proxy_ips='10.0.0.1',
    )
    seen = _hit(chain, recorder, remote_addr='203.0.113.9', xff='5.6.7.8')
    assert seen['REMOTE_ADDR'] == '203.0.113.9'


# ── M10: CSP hardening header ────────────────────────────────────────────────


def test_csp_includes_hardening_directives(app_fx):
    client = app_fx.test_client()
    r = client.get('/static/public/data/teachers.json')
    csp = r.headers.get('Content-Security-Policy', '')
    for directive in ("base-uri 'self'", "object-src 'none'", "form-action 'self'"):
        assert directive in csp, f'CSP missing {directive}: {csp}'


# ── L9: single source for public data ────────────────────────────────────────


def test_templates_public_duplicate_is_removed():
    assert not __import__('pathlib').Path('templates/public').exists()


def test_served_public_data_is_git_tracked():
    assert __import__('pathlib').Path('static/public/data/teachers.json').exists()
    with open('static/public/data/teachers.json', encoding='utf-8') as f:
        data = json.load(f)
    assert data.get('teachers'), 'authoritative teachers.json exists and holds data'