"""In‑memory rate limiter.

Not production‑grade for multi‑process deployments, but perfectly fine for
a single‑process Flask dev server.  Drop‑in replacement: swap the storage
backend to Redis later without changing the public API.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, List, Tuple

# /     /     >---- محدد معدل الطلبات (يحد كم طلب مسموح في وقت معين)
# /     /     >---- نستعمله مثلاً لمنع الهجمات على تسجيل الدخول

# /     /     >---- كلاس محدد المعدل
class RateLimiter:
    """Simple sliding‑window rate limiter keyed by an arbitrary string."""

    # /     /     >---- البداية: نضبط الحد الأقصى والوقت
    def __init__(self, max_requests: int = 5, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: Dict[str, List[float]] = defaultdict(list)

    # /     /     >---- نشيل الطلبات القديمة اللي خلص وقتها
    def _cleanup(self, key: str) -> None:
        cutoff = time.time() - self.window_seconds
        self._hits[key] = [t for t in self._hits[key] if t > cutoff]

    # /     /     >---- نشوف إذا المفتاح تعدى الحد
    def is_limited(self, key: str) -> bool:
        """Return *True* if *key* has exceeded the limit."""
        self._cleanup(key)
        return len(self._hits[key]) >= self.max_requests

    # /     /     >---- نسجل طلب جديد لهذا المفتاح
    def record(self, key: str) -> None:
        """Record a hit for *key*."""
        self._cleanup(key)
        self._hits[key].append(time.time())

    # /     /     >---- كم طلب فاضل في النافذة الحالية
    def remaining(self, key: str) -> int:
        """How many requests remain in the current window."""
        self._cleanup(key)
        return max(0, self.max_requests - len(self._hits[key]))

    # /     /     >---- نمسح سجل هذا المفتاح (بعد نجاح تسجيل الدخول مثلاً)
    def reset(self, key: str) -> None:
        """Clear history for *key*."""
        self._hits.pop(key, None)