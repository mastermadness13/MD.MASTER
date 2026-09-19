"""System-wide constants — paths, pagination, grading, security knobs."""

import os

# /     /     >---- المسار الجذري للمشروع
basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

# ── ترقيم الصفحات ──────────────────────────────────────────────────────────
# /     /     >---- عدد العناصر في الصفحة الوحدة
PER_PAGE = 20

# ── الدرجات ───────────────────────────────────────────────────────────────
# /     /     >---- نسبة النجاح (المكان الوحيد لتغييرها)
PASS_THRESHOLD = 50  # percentage — the single place to change it

# ── الأمان ────────────────────────────────────────────────────────────────
PASSWORD_MIN_LENGTH = 6          # /     /     >---- أقل عدد حروف لكلمة المرور
PASSWORD_RESET_EXPIRY_HOURS = 1  # /     /     >---- رابط استرجاع كلمة المرور يصير لو تجاوز ساعة
LOGIN_RATE_LIMIT_MAX = 3         # /     /     >---- أقصى عدد محاولات دخول خاطئة
LOGIN_RATE_WINDOW_SECONDS = 300  # /     /     >---- نافذة الوقت (5 دقائق)