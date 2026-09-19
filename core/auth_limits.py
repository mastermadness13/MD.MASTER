"""Unified rate limiters for all authentication flows.

Shared between ``routes/auth.py`` (HTML form login, forgot/reset password)
and ``api/auth.py`` (SPA/API login) so that an attacker cannot double their
attempts by alternating between the two entry points.

All limiters are module-level singletons — they survive across requests within
the same process lifetime, which is the expected scope for the in-memory
``RateLimiter`` backend.

Rate policy (login):
  5 attempts per 60-second sliding window, tracked **per client IP** and
  **per username** (whichever limit is hit first blocks the request).

Rate policy (forgot / reset):
  5 requests per 60-second sliding window, tracked per IP and per
  username / token respectively.
"""

from core.rate_limiter import RateLimiter

# ── Login ──────────────────────────────────────────────────────────────────

login_limiter = RateLimiter(max_requests=5, window_seconds=60)
login_user_limiter = RateLimiter(max_requests=5, window_seconds=60)

# ── Forgot password ────────────────────────────────────────────────────────

forgot_limiter = RateLimiter(max_requests=5, window_seconds=60)
forgot_user_limiter = RateLimiter(max_requests=5, window_seconds=60)

# ── Reset password (per-IP + per-token) ────────────────────────────────────

reset_limiter = RateLimiter(max_requests=5, window_seconds=60)
reset_token_limiter = RateLimiter(max_requests=5, window_seconds=60)


# ── convenience helpers ────────────────────────────────────────────────────

def is_login_blocked(client_ip: str, username: str) -> bool:
    """Return True if the login should be refused (rate limit exceeded)."""
    return login_limiter.is_limited(client_ip) or login_user_limiter.is_limited(
        'user:' + (username or '').lower()
    )


def record_login_failure(client_ip: str, username: str) -> None:
    """Record one failed login attempt."""
    login_limiter.record(client_ip)
    login_user_limiter.record('user:' + (username or '').lower())


def reset_login(client_ip: str, username: str) -> None:
    """Clear rate-limit history for a successful login."""
    login_limiter.reset(client_ip)
    login_user_limiter.reset('user:' + (username or '').lower())


def is_forgot_blocked(client_ip: str, username: str) -> bool:
    """Return True if the forgot-password request should be refused."""
    return forgot_limiter.is_limited(client_ip) or forgot_user_limiter.is_limited(
        'user:' + (username or '').lower()
    )


def record_forgot(client_ip: str, username: str) -> None:
    """Record a forgot-password request."""
    forgot_limiter.record(client_ip)
    forgot_user_limiter.record('user:' + (username or '').lower())


def is_reset_blocked(client_ip: str, token: str) -> bool:
    """Return True if the reset-password POST should be refused."""
    return reset_limiter.is_limited(client_ip) or reset_token_limiter.is_limited(
        'token:' + token
    )


def record_reset(client_ip: str, token: str) -> None:
    """Record a reset-password POST attempt."""
    reset_limiter.record(client_ip)
    reset_token_limiter.record('token:' + token)
