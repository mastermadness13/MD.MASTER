"""Rate limiter with pluggable storage backend.

Default backend is in-memory — exactly right for the single‑process Waitress
deployment and the same behavior the app has shipped with. To share a limit
across processes, set ``RATE_LIMITER_BACKEND=sqlite`` (a WAL sqlite file
doubles as a shared store) or swap in another storage object:

    RateLimiter(storage=SQLiteStorage('rate_limit.sqlite'))

The public ``RateLimiter`` API is unchanged regardless of backend.
"""

from __future__ import annotations

import os
import sqlite3
import time
from collections import defaultdict
from typing import Dict, List

# /     /     >---- محدد معدل الطلبات (يحد كم طلب مسموح في وقت معين)
# /     /     >---- نستعمله مثلاً لمنع الهجمات على تسجيل الدخول


class InMemoryStorage:
    """Sliding‑window hits kept per key in a dict of timestamps."""

    def __init__(self):
        self._hits: Dict[str, List[float]] = defaultdict(list)

    def count(self, key: str) -> int:
        return len(self._hits[key])

    def record(self, key: str, ts: float) -> None:
        self._hits[key].append(ts)

    def trim(self, key: str, cutoff: float) -> None:
        self._hits[key] = [t for t in self._hits[key] if t > cutoff]

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)

    def reset_all(self) -> None:
        self._hits.clear()


class SQLiteStorage:
    """Sliding‑window hits stored in a shared WAL sqlite file.

    Lets multiple processes enforce one budget, at the cost of a per‑record
    write. Connections are reused per thread only; the file is created on
    first use. Garbage is trimmed lazily on each access.
    """

    def __init__(self, path: str):
        self.path = path
        self._local = {}

    def _conn(self):
        local = self._local.get('conn')
        if local is None:
            local = sqlite3.connect(self.path, check_same_thread=False)
            local.execute(
                'CREATE TABLE IF NOT EXISTS limiter_hits ('
                ' key TEXT NOT NULL, ts REAL NOT NULL)')
            local.execute('CREATE INDEX IF NOT EXISTS idx_limiter_key ON limiter_hits (key, ts)')
            local.execute('PRAGMA journal_mode=WAL')
            local.commit()
            self._local['conn'] = local
        return local

    def count(self, key: str) -> int:
        row = self._conn().execute(
            'SELECT COUNT(*) FROM limiter_hits WHERE key = ?', (key,)).fetchone()
        return row[0] if row else 0

    def record(self, key: str, ts: float) -> None:
        self._conn().execute('INSERT INTO limiter_hits (key, ts) VALUES (?, ?)', (key, ts))
        self._conn().commit()

    def trim(self, key: str, cutoff: float) -> None:
        self._conn().execute('DELETE FROM limiter_hits WHERE key = ? AND ts <= ?', (key, cutoff))
        self._conn().commit()

    def reset(self, key: str) -> None:
        self._conn().execute('DELETE FROM limiter_hits WHERE key = ?', (key,))
        self._conn().commit()

    def reset_all(self) -> None:
        self._conn().execute('DELETE FROM limiter_hits')
        self._conn().commit()


def default_storage():
    """Pick a storage backend from the environment.

    ``RATE_LIMITER_BACKEND``: ``memory`` (default) or ``sqlite``.
    ``RATE_LIMITER_SQLITE_PATH`` overrides the shared file location.
    """
    backend = os.environ.get('RATE_LIMITER_BACKEND', 'memory').strip().lower()
    if backend in ('sqlite', 'file'):
        path = os.environ.get('RATE_LIMITER_SQLITE_PATH') or 'rate_limit.sqlite'
        return SQLiteStorage(path)
    return InMemoryStorage()


class RateLimiter:
    """Sliding‑window rate limiter keyed by an arbitrary string."""

    # /     /     >---- البداية: نضبط الحد الأقصى والوقت ومخزن الطلبات
    def __init__(self, max_requests: int = 5, window_seconds: int = 60, storage=None):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._storage = storage or default_storage()

    # /     /     >---- نشيل الطلبات القديمة اللي خلص وقتها
    def _cleanup(self, key: str) -> None:
        self._storage.trim(key, time.time() - self.window_seconds)

    # /     /     >---- نشوف إذا المفتاح تعدى الحد
    def is_limited(self, key: str) -> bool:
        """Return *True* if *key* has exceeded the limit."""
        self._cleanup(key)
        return self._storage.count(key) >= self.max_requests

    # /     /     >---- نسجل طلب جديد لهذا المفتاح
    def record(self, key: str) -> None:
        """Record a hit for *key*."""
        self._cleanup(key)
        self._storage.record(key, time.time())

    # /     /     >---- كم طلب فاضل في النافذة الحالية
    def remaining(self, key: str) -> int:
        """How many requests remain in the current window."""
        self._cleanup(key)
        return max(0, self.max_requests - self._storage.count(key))

    # /     /     >---- نمسح سجل هذا المفتاح (بعد نجاح تسجيل الدخول مثلاً)
    def reset(self, key: str) -> None:
        """Clear history for *key*."""
        self._storage.reset(key)

    # /     /     >---- نمسح سجل كل المفاتيح (تستخدمه الاختبارات للعزل)
    def reset_all(self) -> None:
        """Clear history for every key."""
        self._storage.reset_all()