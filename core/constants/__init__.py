"""Application-wide constants package.

Split of the former single `core/constants.py` into focused modules:

- `roles.py`        ROLE_NAMES / ROLE_LABELS
- `permissions.py`  ROLE_PERMISSIONS
- `navigation.py`   NAV_ITEMS (navigation registry)
- `uploads.py`      MAX_CONTENT_LENGTH, ALLOWED_UPLOAD_EXTENSIONS
- `ui.py`           Arabic labels, calendars, palettes, course icons
- `system.py`       pagination, grading, security knobs, basedir

`SOFT_DELETE_TABLES` lives in `database/constants.py` (schema concern).

Backward compatibility: every name is re-exported here so the former
`from core.constants import X` imports keep working during the migration.
"""

# /     /     >---- هذا هو الحزمة الرئيسية للثوابت في التطبيق كله
# /     /     >---- قبل كان ملف واحد، قابلوه لعدة موديولات صغيرة

from core.constants import navigation, permissions, roles, system, ui, uploads

# ── إعادة تصدير الصلاحيات والتنقل والأدوار ────────────────────────
from core.constants.permissions import ROLE_PERMISSIONS
from core.constants.navigation import NAV_ITEMS
from core.constants.roles import ROLE_LABELS, ROLE_NAMES

# ── إعادة تصدير ثوابت النظام (الأمان، الترقيم، الدرجات) ────────────
from core.constants.system import (
    LOGIN_RATE_LIMIT_MAX,
    LOGIN_RATE_WINDOW_SECONDS,
    PASSWORD_MIN_LENGTH,
    PASSWORD_RESET_EXPIRY_HOURS,
    PASS_THRESHOLD,
    PER_PAGE,
    basedir,
)

# ── إعادة تصدير ثوابت الواجهة (الايام، الشهور، الألوان، الأيقونات) ──
from core.constants.ui import (
    ARABIC_DAYS,
    ARABIC_MONTHS,
    COURSE_ICON_MAP,
    DAY_ORDER,
    SEMESTER_LABELS,
    SEMESTER_SEASONS,
    SEMESTER_SEASONS_EN,
    SEMESTER_SEASON_NEXT,
    SEMESTER_SEASON_ORDER,
    TIMETABLE_PALETTE,
    WEEK_DAYS,
    WEEK_DAYS_ALT,
)

# ── إعادة تصدير ثوابت الرفع ───────────────────────────────────────
from core.constants.uploads import ALLOWED_UPLOAD_EXTENSIONS, MAX_CONTENT_LENGTH

# /     /     >---- الليست النهائية للأسماء اللي تقدر تستوردها من هذي الحزمة
__all__ = [
    'ROLE_NAMES',
    'ROLE_LABELS',
    'ROLE_PERMISSIONS',
    'NAV_ITEMS',
    'MAX_CONTENT_LENGTH',
    'ALLOWED_UPLOAD_EXTENSIONS',
    'SEMESTER_LABELS',
    'SEMESTER_SEASONS',
    'SEMESTER_SEASONS_EN',
    'SEMESTER_SEASON_NEXT',
    'SEMESTER_SEASON_ORDER',
    'WEEK_DAYS',
    'WEEK_DAYS_ALT',
    'DAY_ORDER',
    'PASS_THRESHOLD',
    'PASSWORD_MIN_LENGTH',
    'PASSWORD_RESET_EXPIRY_HOURS',
    'LOGIN_RATE_LIMIT_MAX',
    'LOGIN_RATE_WINDOW_SECONDS',
    'PER_PAGE',
    'ARABIC_MONTHS',
    'ARABIC_DAYS',
    'TIMETABLE_PALETTE',
    'COURSE_ICON_MAP',
    'basedir',
]