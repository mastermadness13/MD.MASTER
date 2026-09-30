"""Shared pytest fixtures.

The Flask app must be created only ONCE per test session — ``create_app()``
registers global blueprints and a second call raises
``AssertionError: setup method 'errorhandler' can no longer be called``.
"""

import pytest

from core import auth_limits

# The harness owns the fixtures; re-exporting them here makes them discoverable
# by pytest without every test module having to import them.
from tests.harness import db_path, get_app, matrix_db, raw_db, seeded  # noqa: F401

_FAIL_LIMITERS = (
    auth_limits.login_limiter,
    auth_limits.login_user_limiter,
    auth_limits.forgot_limiter,
    auth_limits.forgot_user_limiter,
    auth_limits.reset_limiter,
    auth_limits.reset_token_limiter,
)


@pytest.fixture(scope='session')
def app_fx():
    """The one application instance for the whole session (see ``get_app``)."""
    return get_app()


@pytest.fixture(autouse=True)
def _isolate_rate_limiters():
    """The module-global limiters are process singletons; reset them so every
    test starts with a fresh budget regardless of run order."""
    for limiter in _FAIL_LIMITERS:
        limiter.reset_all()
    yield
