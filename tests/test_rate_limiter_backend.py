"""Phase 4 — pluggable rate-limiter backend.

The public RateLimiter API must keep working identically with the default
in-memory backend, and a shared (SQLite) backend must enforce one budget
across separate limiter instances (the multi-process case).
"""

import os
import time

import pytest

from core.rate_limiter import (
    InMemoryStorage,
    RateLimiter,
    SQLiteStorage,
    default_storage,
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    monkeypatch.delenv('RATE_LIMITER_BACKEND', raising=False)
    monkeypatch.delenv('RATE_LIMITER_SQLITE_PATH', raising=False)


def test_default_backend_is_memory():
    assert isinstance(default_storage(), InMemoryStorage)


def test_backend_env_selects_sqlite(monkeypatch):
    monkeypatch.setenv('RATE_LIMITER_BACKEND', 'sqlite')
    assert isinstance(default_storage(), SQLiteStorage)


def test_limiter_honors_max_requests():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    for _ in range(3):
        assert not limiter.is_limited('user')
        assert limiter.remaining('user') > 0
        limiter.record('user')
    assert limiter.is_limited('user')
    assert limiter.remaining('user') == 0


def test_reset_clears_budget():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    limiter.record('user')
    assert limiter.is_limited('user')
    limiter.reset('user')
    assert not limiter.is_limited('user')


def test_window_expires_hits(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, 'time', lambda: now[0])
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    limiter.record('user')
    assert limiter.is_limited('user')
    now[0] += 61
    assert not limiter.is_limited('user')


def test_sqlite_backend_shared_across_limiters(tmp_path):
    store = SQLiteStorage(str(tmp_path / 'limiter.sqlite'))
    a = RateLimiter(max_requests=2, window_seconds=60, storage=store)
    b = RateLimiter(max_requests=2, window_seconds=60, storage=store)
    a.record('login:admin')
    a.record('login:admin')
    # A separate limiter instance over the same store sees the same budget.
    assert b.is_limited('login:admin')
    b.reset('login:admin')
    assert not a.is_limited('login:admin')


def test_independent_in_memory_limiters_do_not_share():
    a = RateLimiter(max_requests=1, window_seconds=60)
    b = RateLimiter(max_requests=1, window_seconds=60)
    a.record('k')
    assert a.is_limited('k')
    assert not b.is_limited('k')