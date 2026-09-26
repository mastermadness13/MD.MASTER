"""§8 — general security defense: response headers, cookies, debug guard, WAF.

Covers `security/security_headers.py`. The header assertions here are the
regression net for the header block that used to be inline in `app.py`.
"""

import pytest
from flask import Flask

from security.security_headers import (
    HSTS_MAX_AGE,
    apply_cookie_config,
    apply_security_headers,
    assert_debug_disabled,
    block_scanner_probes,
    build_csp,
)


# ── helpers ────────────────────────────────────────────────────────────────


def _bare_app(**config):
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config.update(config)

    @app.route('/ok')
    def _ok():
        return 'ok'

    return app


# ── headers actually reach the client ───────────────────────────────────────


def test_hsts_header_is_sent(app_fx):
    """The genuinely new protection: HSTS was missing entirely before."""
    r = app_fx.test_client().get('/static/public/data/teachers.json')
    hsts = r.headers.get('Strict-Transport-Security', '')
    assert hsts, 'Strict-Transport-Security is not set'
    assert f'max-age={HSTS_MAX_AGE}' in hsts
    assert 'includeSubDomains' in hsts


def test_hsts_skipped_when_session_cookie_not_secure():
    """No point advertising HSTS in a deployment that opted out of HTTPS."""
    app = _bare_app(SESSION_COOKIE_SECURE=False)
    apply_security_headers(app)
    assert 'Strict-Transport-Security' not in app.test_client().get('/ok').headers


def test_obsolete_x_xss_protection_is_disabled(app_fx):
    """`1; mode=block` is deprecated and historically introduced XSS holes.

    Modern guidance (OWASP) is `X-XSS-Protection: 0`, which turns the legacy
    auditor off rather than enabling it.
    """
    headers = app_fx.test_client().get('/health').headers
    assert headers.get('X-XSS-Protection') == '0'


def test_baseline_headers_still_present(app_fx):
    r = app_fx.test_client().get('/health')
    assert r.headers.get('X-Content-Type-Options') == 'nosniff'
    assert r.headers.get('X-Frame-Options') == 'SAMEORIGIN'
    assert r.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'
    assert 'camera=()' in r.headers.get('Permissions-Policy', '')


# ── CSP ─────────────────────────────────────────────────────────────────────


def test_csp_keeps_pre_existing_directives(app_fx):
    """Regression net: the old inline block's directives must not vanish."""
    csp = app_fx.test_client().get('/health').headers['Content-Security-Policy']
    for directive in (
        "default-src 'self'",
        "base-uri 'self'",
        "object-src 'none'",
        "form-action 'self'",
        "frame-ancestors 'self'",
        "connect-src 'self'",
    ):
        assert directive in csp, f'CSP lost {directive}: {csp}'


def test_csp_keeps_cdn_allowlist():
    """Tailwind/Tom Select/Google Fonts are still loaded from CDNs.

    Dropping these would unstyle the site. This test exists so that anyone
    tightening the CSP sees exactly which entry pins them.
    """
    csp = build_csp()
    assert 'https://cdn.tailwindcss.com' in csp
    assert 'https://cdn.jsdelivr.net' in csp
    assert 'https://fonts.googleapis.com' in csp
    assert 'https://fonts.gstatic.com' in csp


@pytest.mark.parametrize(
    'directive,value',
    [
        ('frame-src', "'none'"),
        ('worker-src', "'self'"),
        ('manifest-src', "'self'"),
        ('media-src', "'self'"),
    ],
)
def test_csp_adds_directives_that_were_missing(directive, value):
    """Safe additions: no iframes, no service worker, no manifest, no media."""
    assert f'{directive} {value}' in build_csp()


def test_csp_is_rendered_as_directive_pairs():
    csp = build_csp()
    assert csp.count(';') >= 10
    for part in csp.split(';'):
        assert part.strip().split(' ')[0].islower(), part


# ── cookie hardening ────────────────────────────────────────────────────────


def test_apply_cookie_config_forces_httponly_and_samesite():
    app = _bare_app(SESSION_COOKIE_HTTPONLY=False, SESSION_COOKIE_SAMESITE='None')
    apply_cookie_config(app)
    assert app.config['SESSION_COOKIE_HTTPONLY'] is True
    assert app.config['SESSION_COOKIE_SAMESITE'] == 'Lax'


def test_apply_cookie_config_respects_secure_opt_out():
    """Local dev over http://127.0.0.1 must stay usable — config.py resolves
    this from the environment, and we must not override it here."""
    app = _bare_app(SESSION_COOKIE_SECURE=False)
    apply_cookie_config(app)
    assert app.config['SESSION_COOKIE_SECURE'] is False


def test_apply_cookie_config_warns_when_secure_disabled(monkeypatch):
    from security import security_headers as mod
    warned = []
    monkeypatch.setattr(mod.logger, 'warning', lambda msg: warned.append(msg))
    apply_cookie_config(_bare_app(SESSION_COOKIE_SECURE=False))
    assert any('SESSION_COOKIE_SECURE' in m for m in warned)


def test_production_cookie_flags_are_secure(app_fx):
    c = app_fx.config
    assert c['SESSION_COOKIE_HTTPONLY'] is True
    assert c['SESSION_COOKIE_SAMESITE'] == 'Lax'
    assert c['SESSION_COOKIE_SECURE'] is True


# ── debug guard ────────────────────────────────────────────────────────────


def test_assert_debug_disabled_passes_for_healthy_app(app_fx):
    assert_debug_disabled(app_fx) is None


def test_assert_debug_disabled_raises_when_app_debug_on():
    app = _bare_app()
    app.debug = True
    with pytest.raises(RuntimeError, match='Debug mode is enabled'):
        assert_debug_disabled(app)


def test_assert_debug_disabled_raises_when_config_debug_on():
    app = _bare_app(DEBUG=True)
    with pytest.raises(RuntimeError, match='Debug mode is enabled'):
        assert_debug_disabled(app)


def test_assert_debug_disabled_raises_on_flask_debug_env(monkeypatch):
    """FLASK_DEBUG is the variable a PythonAnywhere WSGI file would set.

    Flask 3.1 copies it into ``config['DEBUG']`` at construction, so this
    raises through the ``app.debug`` branch — the point is that the guard
    fires at all, and says what to fix.
    """
    monkeypatch.setenv('FLASK_DEBUG', '1')
    with pytest.raises(RuntimeError, match='Debug mode is enabled'):
        assert_debug_disabled(_bare_app())


def test_assert_debug_disabled_raises_on_plain_debug_env(monkeypatch):
    """Flask reads FLASK_DEBUG only — a bare DEBUG env var is ours to catch."""
    monkeypatch.delenv('FLASK_DEBUG', raising=False)
    monkeypatch.setenv('DEBUG', '1')
    with pytest.raises(RuntimeError, match='DEBUG is set to a truthy value'):
        assert_debug_disabled(_bare_app())


def test_flask_debug_off_still_enables_debug(monkeypatch):
    """Documents a Flask 3.1 footgun rather than asserting our own opinion.

    Flask's falsy set is ``{'0', 'false', 'no', ''}`` — ``'off'`` is absent,
    so ``FLASK_DEBUG=off`` turns the debugger **on**. Unset the variable; do
    not "disable" it with ``off``.
    """
    monkeypatch.setenv('FLASK_DEBUG', 'off')
    assert _bare_app().debug is True
    with pytest.raises(RuntimeError, match='Debug mode is enabled'):
        assert_debug_disabled(_bare_app())


@pytest.mark.parametrize('value', ['0', 'false', 'no', ''])
def test_assert_debug_disabled_ignores_falsy_env(monkeypatch, value):
    monkeypatch.setenv('FLASK_DEBUG', value)
    monkeypatch.setenv('DEBUG', value)
    assert_debug_disabled(_bare_app()) is None


# ── scanner probe blocklist ────────────────────────────────────────────────

# /     /     >---- التطبيق الحقيقي ما عنده أي مسار بهالأسماء، فالاختبار
# /     /     >---- فيهن 404 سواء كان الفلتر شغّال أو لأ. عشان كذا نختبر
# /     /     >---- الفلتر على تطبيق صناعي فيه مسار يطابق فعلاً — وإلا
# /     /     >---- الاختبار يمر بلا ما يثبت أي شي


def _probe_app():
    """A synthetic app with a catch-all route that the blocklist must shadow."""
    app = _bare_app()
    block_scanner_probes(app)

    @app.route('/<path:path>')
    def _echo(path):
        return f'reached:{path}'

    return app


@pytest.mark.parametrize(
    'path',
    [
        '/wp-admin/install.php',
        '/wp-login.php',
        '/wp-content/plugins/x',
        '/wp-includes/x.js',
        '/.env',
        '/.env.local',
        '/.git/config',
        '/.svn/entries',
        '/.hg/store',
        '/.aws/credentials',
        '/phpinfo.php',
        '/xmlrpc.php',
        '/config.php.bak',
        '/admin.php',
        '/wp-config.php',
        '/cgi-bin/test',
        '/shell.php',
        '/.DS_Store',
    ],
)
def test_scanner_probes_get_404(path):
    assert _probe_app().test_client().get(path).status_code == 404


@pytest.mark.parametrize(
    'path',
    ['/WP-ADMIN/', '/.ENV', '/.Git/config', '/CONFIG.PHP.BAK', '/Cgi-Bin/x'],
)
def test_probe_match_is_case_insensitive(path):
    """Scanners randomise case to slip past naive `in` checks."""
    assert _probe_app().test_client().get(path).status_code == 404


def test_non_probe_paths_pass_through():
    r = _probe_app().test_client().get('/courses/1/edit')
    assert r.status_code == 200
    assert r.get_data(as_text=True) == 'reached:courses/1/edit'


def test_uploads_path_is_exempt_from_probe_block():
    """A teacher may legitimately upload a file called `admin.php`; the
    upload-serving route must not be blocked by the scanner blocklist."""
    app = _probe_app()

    @app.route('/uploads/<path:filename>')
    def _uploaded(filename):
        return filename

    r = app.test_client().get('/uploads/admin.php')
    assert r.status_code == 200
    assert r.get_data(as_text=True) == 'admin.php'


def test_blocklist_is_wired_into_the_real_app(app_fx):
    assert app_fx.test_client().get('/login').status_code == 200
    names = [f.__name__ for f in app_fx.before_request_funcs.get(None, [])]
    assert '_reject_known_probes' in names


def test_probe_block_runs_before_session_lookup():
    """Registered first, so a probe never reaches the DB."""
    app = _bare_app()
    block_scanner_probes(app)
    order = [f.__name__ for f in app.before_request_funcs.get(None, [])]
    assert order[0] == '_reject_known_probes'
