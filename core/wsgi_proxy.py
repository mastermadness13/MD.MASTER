"""WSGI chain builder for production serving behind a reverse proxy (M4).

``ProxyFix`` rewrites ``REMOTE_ADDR``/``HTTP_HOST`` from client-supplied
``X-Forwarded-*`` headers, so it must only ever be applied when the *direct
peer* is a proxy we control. This module applies the fix exclusively for
peers listed in ``TRUSTED_PROXY_IPS``; every other peer is served untouched.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def build_wsgi_chain(app, trust_proxy_headers=False, trusted_proxy_ips=''):
    """Return a WSGI app for *app* honoring proxy headers only from trusted peers.

    - ``trust_proxy_headers`` False (default): *app* is returned unchanged.
    - True but no allowlist: proxy headers are IGNORED (fail-safe) and a
      warning is logged; *app* is returned unchanged.
    - True + allowlist: a wrapper applies ``ProxyFix`` only when
      ``environ['REMOTE_ADDR']`` is in the allowlist.
    """
    if not trust_proxy_headers:
        return app

    allowed = {ip.strip() for ip in trusted_proxy_ips.split(',') if ip.strip()}
    if not allowed:
        logger.warning(
            'TRUST_PROXY_HEADERS=true but no TRUSTED_PROXY_IPS configured; '
            'X-Forwarded-* headers will be IGNORED (fail-safe).'
        )
        return app

    from werkzeug.middleware.proxy_fix import ProxyFix

    proxy = ProxyFix(app, x_for=1, x_proto=1, x_host=1)

    def _conditional(environ, start_response):
        if environ.get('REMOTE_ADDR') in allowed:
            return proxy(environ, start_response)
        return app(environ, start_response)

    return _conditional