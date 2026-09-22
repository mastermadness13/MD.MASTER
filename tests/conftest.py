"""Shared pytest fixtures.

The Flask app must be created only ONCE per test session — ``create_app()``
registers global blueprints and a second call raises
``AssertionError: setup method 'errorhandler' can no longer be called``.
"""

import pytest

from app import create_app
from core import auth_limits

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
    app = create_app()
    app.config['TESTING'] = True
    yield app


@pytest.fixture(autouse=True)
def _isolate_rate_limiters():
    """The module-global limiters are process singletons; reset them so every
    test starts with a fresh budget regardless of run order."""
    for limiter in _FAIL_LIMITERS:
        limiter.reset_all()
    yield
