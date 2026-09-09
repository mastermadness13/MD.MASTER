"""System-wide constants — paths, pagination, grading, security knobs."""

import os

basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

# ── Pagination ────────────────────────────────────────────────────────────────
PER_PAGE = 20

# ── Grading ───────────────────────────────────────────────────────────────────
PASS_THRESHOLD = 50  # percentage — the single place to change it

# ── Security ──────────────────────────────────────────────────────────────────
PASSWORD_MIN_LENGTH = 6
PASSWORD_RESET_EXPIRY_HOURS = 1
LOGIN_RATE_LIMIT_MAX = 3
LOGIN_RATE_WINDOW_SECONDS = 300
