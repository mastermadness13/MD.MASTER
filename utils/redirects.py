"""Safe back-redirect helper used by error handlers and route guards."""

from urllib.parse import urlsplit

from flask import redirect, request, url_for

# ─────────────────────────────────────────────

# /     /     >---- نرجع المستخدم للصفحة السابقة بس إذا كانت من نفس الموقع
def redirect_back(fallback_endpoint='dashboard.dashboard'):
    """Redirect to the referring page only when it is same-origin.

    Prevents open redirects: when there is no referrer or it points to a
    different host, fall back to ``fallback_endpoint``.
    """
    referrer = request.referrer or ''
    if referrer:
        # /     /     >---- نتأكد الرابط من نفس السيرفر
        parts = urlsplit(referrer)
        if parts.netloc == request.host:
            return redirect(referrer)
    # /     /     >---- إذا ما فيش رابط نرجع للوحة التحكم
    return redirect(url_for(fallback_endpoint))