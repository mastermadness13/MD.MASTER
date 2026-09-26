"""Application-layer response hardening for section 8 (general security defense).

Scope note -- this module deliberately does **not** use `flask-talisman`.
Talisman would install a *second* `after_request` that overwrites the
headers set here, and its default policy (`script-src 'self'`) would
break every page in this project:

* `templates/shared/components/head_preamble.html` loads Tailwind from
  `cdn.tailwindcss.com` -- a JIT compiler that requires `'unsafe-eval'`.
* 146 inline `on*` handlers and 6 inline `<script>` blocks
  across 33 templates require `'unsafe-inline'`.

A hard `script-src 'self'` would leave the site unstyled and inert.
The headers are therefore managed here, as one auditable source of truth, and the real
CSP tightening is tracked as its own piece of work (Tailwind self-hosted + inline
handlers moved to `/static/js`) rather than done as a header swap that looks
secure and is not.

What this module adds over the previous inline block in `app.py`:

1. `Strict-Transport-Security` -- was **missing entirely**. This is the
   one genuinely new protection here: it stops the browser from ever retrying
   the site over plain HTTP, which `SESSION_COOKIE_SECURE` alone does not
   do (a secure cookie is simply not *sent* over HTTP, so the request still
   happens and can be observed or tampered with).
2. Removal of `X-XSS-Protection` -- deprecated since 2018. The legacy
   auditor in old browsers has itself been used to *introduce* XSS holes
   (CVE-2019-11358 et al.). Modern guidance is `X-XSS-Protection: 0`.
3. The CSP directives that were missing and cost nothing to add (`frame-src`, `worker-src`, `manifest-src`, `media-src`;
   `form-action` was already present).
4. `assert_debug_disabled` -- a hard failure at startup if the Werkzeug
   interactive debugger is reachable in production.
5. `block_scanner_probes` -- a cheap blocklist for automated
   vulnerability scanner noise.
"""
from __future__ import annotations

import logging
import os

from flask import abort, request

# /     /     >---- اللوقنق
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
# Content-Security-Policy
# ─────────────────────────────────────────────────────────────────────

# /     /     >---- نجمع السياسة من قطع عشان تبقى في مكان واحد
# /     /     >---- 'unsafe-inline' و 'unsafe-eval' ضروريين حالياً — اقرأ
# /     /     >---- شرح ومدة الإصلاح في توثيق الوحدة أعلاه.

CSP_DIRECTIVES: dict[str, str] = {
    "default-src": "'self'",
    "script-src": "'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://cdn.jsdelivr.net",
    "style-src": "'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdn.tailwindcss.com https://cdnjs.cloudflare.com",
    "font-src": "'self' https://fonts.gstatic.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
    "img-src": "'self' data: blob:",
    # لا يوجد أي fetch/WebSocket لعنوان خارجي في static/js
    "connect-src": "'self'",
    # لا يوجد iframe في أي قالب — نقفلها تماماً
    "frame-src": "'none'",
    "media-src": "'self'",
    "worker-src": "'self'",
    "manifest-src": "'self'",
    "base-uri": "'self'",
    "frame-ancestors": "'self'",
    "object-src": "'none'",
    "form-action": "'self'",
}


def build_csp() -> str:
    """Render the CSP as a header value.

    Exposed separately so tests (and any future config) can assert on the
    policy without going through a full request.
    """
    return "; ".join(f"{name} {value}" for name, value in CSP_DIRECTIVES.items())


# /     /     >---- قيمة HSTS: سنة كاملة، مع كل النطاقات الفرعية
# /     /     >---- preload متروك عمداً: تسجيل النطاق في قائمة preload
# /     /     >---- للمتصفحات يتطلب تحكماً كاملاً بالدومين، وهذا مو متاح
# /     /     >---- على العنوان المجاني — اتركه للمتصفح يطبقه من الاستجابة
HSTS_MAX_AGE = 31536000

# ─────────────────────────────────────────────────────────────────────
# Response headers
# ─────────────────────────────────────────────────────────────────────


def apply_security_headers(app) -> None:
    """Register the ``after_request`` hook that hardens every response.

    Call once from the app factory. Safe in tests and local dev: HSTS is only
    honoured by browsers when it arrives over HTTPS, so it is inert on
    ``http://127.0.0.1:5000`` and cannot lock you out of your own machine.
    """
    csp = build_csp()

    @app.after_request
    def _harden_response(response):
        # /     /     >---- sniffed content: يمنع المتصفح من تخمين نوع المحتوى
        response.headers['X-Content-Type-Options'] = 'nosniff'
        # /     /     >---- منع التضمين في iframe (مكرَر مع frame-ancestors للقديم)
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        # /     /     >---- ما نكشف عنوان الصفحة إلا لنفس الأصل
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        # /     /     >---- الموقع ما يحتاج كاميرا ولا موقع
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'

        # /     /     >---- HSTS: المتصفح يلتزم بـHTTPS لمدة سنة
        # /     /     >---- يشمل includeSubDomains لأن النطاق كله عندنا
        if app.config.get('SESSION_COOKIE_SECURE'):
            response.headers['Strict-Transport-Security'] = (
                f'max-age={HSTS_MAX_AGE}; includeSubDomains'
            )

        # /     /     >---- X-XSS-Protection مهجور منذ 2018، وما يمنع XSS في
        # /     /     >---- المتصفحات الحديثة إطلاقاً، وفتّح ثغرات في القديمة
        # /     /     >---- (CVE-2019-11358 وما بعدها). نرسل 0 صراحةً لأن
        # /     /     >---- 0 يمنع المتصفح من تشغيل الفلتر القديم نهائياً
        response.headers['X-XSS-Protection'] = '0'

        response.headers['Content-Security-Policy'] = csp

        # /     /     >---- إعداد الكاش حسب نوع المسار
        path = request.path
        if path.startswith('/static/'):
            # /     /     >---- الملفات الثابتة تكاش لمدة سنة
            response.cache_control.public = True
            response.cache_control.max_age = 31536000
        elif path.startswith('/uploads/'):
            # /     /     >---- الملفات المرفوعة تكاش لمدة ساعة
            response.cache_control.private = True
            response.cache_control.max_age = 3600

        return response


# ─────────────────────────────────────────────────────────────────────
# Cookie hardening
# ─────────────────────────────────────────────────────────────────────


def apply_cookie_config(app) -> None:
    """Enforce the cookie flags that must never be downgraded.

    ``SESSION_COOKIE_SECURE`` is deliberately **not** forced on here: it is
    already resolved from the environment in ``config.py`` so that local dev
    over ``http://127.0.0.1:5000`` can turn it off without editing code.
    Downgrading it is logged, not silently allowed.
    """
    # /     /     >---- جافاسكربت ما يقدر يقرأ كوكي الجلسة (حماية من XSS)
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    # /     /     >---- SameSite=Lax يمنع معظم هجمات CSRF على مستوى الكوكي،
    # /     /     >---- فوق حماية CSRF الموجودة أصلاً
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    if not app.config.get('SESSION_COOKIE_SECURE'):
        # /     /     >---- نتركه false محلياً، لكن نسجّله بصوت عالٍ
        logger.warning(
            'SESSION_COOKIE_SECURE is False — the session cookie will be '
            'sent over plain HTTP. Never set SESSION_COOKIE_SECURE=false in '
            'production.'
        )


# ─────────────────────────────────────────────────────────────────────
# Debug-mode safety net (P0 misconfiguration)
# ─────────────────────────────────────────────────────────────────────


def _debug_env_requested() -> str | None:
    """Return the name of the env var asking for debug mode, if any.

    The truthy set matches Flask's own ``get_debug_flag()`` deliberately.

    Note the Flask 3.1 quirk this inherits: ``FLASK_DEBUG=off`` still turns
    debug **on**, because Flask's falsy set is ``{'0', 'false', 'no', ''}`` and
    does not include ``'off'``. Flask reads ``FLASK_DEBUG`` into
    ``config['DEBUG']`` at construction time, so setting it to ``off`` is
    *worse* than leaving it unset.
    """
    for name in ('FLASK_DEBUG', 'DEBUG'):
        value = os.environ.get(name, '').strip().lower()
        if value in ('1', 'true', 'yes', 'on'):
            return name
    return None


def assert_debug_disabled(app) -> None:
    """Raise ``RuntimeError`` if the interactive debugger is reachable.

    Flask's debug mode exposes the Werkzeug console on any unhandled
    exception. That console is arbitrary code execution inside the app
    process, so leaving it on in production is a full-compromise bug, not a
    minor misconfiguration.

    Checked signals:

    * ``app.debug`` / ``app.config['DEBUG']`` — the debugger is live.
    * ``FLASK_DEBUG`` / ``DEBUG`` env vars — the deployment is *asking* for
      it. ``create_app()`` itself does not read these (only the ``__main__``
      block does), so without this check a PythonAnywhere WSGI file that
      sets the variable would pass the first two tests and still be
      misconfigured for the next person to run ``flask run``.
    """
    if app.debug or app.config.get('DEBUG'):
        raise RuntimeError(
            'Debug mode is enabled — the Werkzeug interactive debugger would be '
            'reachable in production, which is arbitrary code execution inside '
            'the app process. Unset FLASK_DEBUG and check the WSGI file on '
            'PythonAnywhere.'
        )

    env_name = _debug_env_requested()
    if env_name:
        raise RuntimeError(
            f'{env_name} is set to a truthy value — this deployment is '
            f'configured for debug mode. Unset {env_name} in the PythonAnywhere '
            'WSGI configuration file / environment variables.'
        )


# ─────────────────────────────────────────────────────────────────────
# Poor-man's WAF: automated scanner probes
# ─────────────────────────────────────────────────────────────────────

# /     /     >---- مسارات بوتات الفحص الآلي تجربها على كل موقع تقريباً
SCANNER_PROBE_PATTERNS = (
    '/wp-admin', '/wp-login', '/wp-content', '/wp-includes',
    '/.env', '/.git/', '/.svn/', '/.hg/', '/.aws/',
    '/phpinfo.php', '/xmlrpc.php', '/config.php.bak', '/admin.php',
    '/cgi-bin/', '/shell.php',     # /     /     >---- كل الأنماط صغيرة حروف: نقارنها مع path بعد lower()
    '/shell.php', '/.ds_store', '/wp-config.php',
)

# /     /     >---- أسماء ملفات الرفع يتحكم فيها المستخدم، وفحصها هنا
# /     /     >---- كان بيلغي تحميل ملف شرعي اسم admin.php
PROBE_EXEMPT_PREFIXES = ('/static/', '/uploads/')


def block_scanner_probes(app) -> None:
    """Return 404 for well-known automated scanner probe paths.

    404 rather than 403 on purpose: a 403 confirms the host is running
    something worth probing. Not a real WAF — it just keeps background noise
    out of the logs and away from the auth rate-limiters' budget.
    """

    @app.before_request
    def _reject_known_probes():
        if request.path.startswith(PROBE_EXEMPT_PREFIXES):
            return None
        lowered = request.path.lower()
        if any(pattern in lowered for pattern in SCANNER_PROBE_PATTERNS):
            abort(404)
        return None
