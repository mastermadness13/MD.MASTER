"""Safe back-redirect helper used by error handlers and route guards."""

from urllib.parse import urlsplit

from flask import redirect, request, url_for


def redirect_back(fallback_endpoint='dashboard.dashboard'):
    """Redirect to the referring page only when it is same-origin.

    Prevents open redirects: when there is no referrer or it points to a
    different host, fall back to ``fallback_endpoint``.
    """
    referrer = request.referrer or ''
    if referrer:
        parts = urlsplit(referrer)
        if parts.netloc == request.host:
            return redirect(referrer)
    return redirect(url_for(fallback_endpoint))
