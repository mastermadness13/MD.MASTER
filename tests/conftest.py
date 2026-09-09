"""Shared pytest fixtures.

The Flask app must be created only ONCE per test session — ``create_app()``
registers global blueprints and a second call raises
``AssertionError: setup method 'errorhandler' can no longer be called``.
"""

import pytest

from app import create_app


@pytest.fixture(scope='session')
def app_fx():
    app = create_app()
    app.config['TESTING'] = True
    yield app
