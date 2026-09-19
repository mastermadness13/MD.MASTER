"""Formatting and query helpers shared across routes and services."""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from core.constants import PER_PAGE, SEMESTER_LABELS, SEMESTER_SEASONS
from flask_db import get_db

# ─────────────────────────────────────────────

# /     /     >---- نرجع اسم الفصل الدراسي بالعربي (مثلاً الفصل الأول)
def semester_label(sem) -> str:
    if not sem:
        return ''
    return SEMESTER_LABELS.get(sem, 'الفصل {}'.format(sem))

# ─────────────────────────────────────────────

# /     /     >---- حالة تسليم المحتوى الدراسي — الوسوم العربية لكل حالة
SUBMISSION_STATUS_LABELS = {
    'draft': 'مسودة',
    'published': 'منشور',
    'pending_teacher': 'بانتظار تعبئة عضو هيئة التدريس',
    'pending_rnd': 'بانتظار المراجعة',
    'pending_hod': 'بانتظار رئيس القسم',
    'pending_exam': 'بانتظار قسم الامتحانات',
    'approved': 'منشور',
    'rejected': 'مرفوض',
}

# /     /     >---- ألوان البادجات (Tailwind) لكل حالة تسليم
SUBMISSION_STATUS_COLORS = {
    'draft': 'bg-surface-dim text-on-surface-variant',
    'published': 'bg-green-100 text-green-700',
    'pending_teacher': 'bg-yellow-100 text-yellow-700',
    'pending_rnd': 'bg-blue-50 text-blue-700',
    'pending_hod': 'bg-yellow-100 text-yellow-700',
    'pending_exam': 'bg-blue-50 text-blue-700',
    'approved': 'bg-green-100 text-green-700',
    'rejected': 'bg-red-100 text-red-700',
}

# ─────────────────────────────────────────────

# /     /     >---- الاسم العربي لحالة تسليم المحتوى
def submission_status_label(status) -> str:
    """Arabic display label for a course-content submission status."""
    return SUBMISSION_STATUS_LABELS.get(status or '', '')

# ─────────────────────────────────────────────

# /     /     >---- الألوان للحالة (في الواجهة)
def submission_status_color(status) -> str:
    """Tailwind badge classes for a course-content submission status."""
    return SUBMISSION_STATUS_COLORS.get(
        status or '', 'bg-surface-dim text-on-surface-variant')

# ─────────────────────────────────────────────

# /     /     >---- اسم الفصل الدراسي لسجل السير الذاتي (الخريفي، الربيعي...)
def teaching_semester_label(sem) -> str:
    if not sem:
        return '—'
    if sem == 1:
        return 'الفصل الخريفي'
    if sem == 2:
        return 'الفصل الربيعي'
    return SEMESTER_LABELS.get(sem, 'الفصل {}'.format(sem))

# ─────────────────────────────────────────────

# /     /     >---- نرجع الاسم العربي لشيفرة فصل دراسي (مثلاً fall_2026 = خريفي 2026)
def semester_display_name(code: str, name_ar: str = None) -> str:
    """Return the Arabic display name for a named semester code.

    ``code`` examples: ``'fall_2026'``, ``'spring_2025'``.
    ``name_ar`` is an optional override from the database row.
    """
    # /     /     >---- إذا فيه اسم في قاعدة البيانات نستعمله
    if name_ar:
        return name_ar
    if not code:
        return ''
    try:
        # /     /     >---- نقسم الشيفرة: الموسم + السنة
        season, year = code.split('_', 1)
        return '{} {}'.format(SEMESTER_SEASONS.get(season, season), year)
    except (ValueError, AttributeError):
        return code

# ─────────────────────────────────────────────

# /     /     >---- نرجع الشيفرة التالية بعد شيفرة معينة
# /     /     >---- fall_2026 ← spring_2027، و spring_2025 ← fall_2025
def semester_code_next(code: str) -> str:
    """Return the next semester code after the given one.

    ``fall_2026`` → ``spring_2027``, ``spring_2025`` → ``fall_2025``.
    """
    if not code:
        return ''
    try:
        season, year = code.split('_', 1)
        from core.constants.ui import SEMESTER_SEASON_NEXT
        next_season = SEMESTER_SEASON_NEXT.get(season, 'fall')
        next_year = int(year) + (1 if next_season == 'fall' and season == 'spring' else 0)
        # /     /     >---- spring→fall: نفس السنة؛ fall→spring: السنة اللي بعده
        if season == 'fall' and next_season == 'spring':
            next_year = int(year) + 1
        return '{}_{}'.format(next_season, next_year)
    except (ValueError, AttributeError):
        return code

# ─────────────────────────────────────────────

# /     /     >---- نشيل اللقب الأكاديمي من الاسم لعرضه في الجداول
def teacher_label(name) -> str:
    if not name:
        return '—'
    text = str(name).strip()
    # /     /     >---- نشيل البادئات مثل (أ. / د. / أ.د.)
    for prefix in ('أ .', 'أ.', 'د .', 'د.'):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    return text or '—'

# ─────────────────────────────────────────────

# /     /     >---- اللقب الأكاديمي المُستنتج (د. / أ. / أ.د.) من الدرجة العلمية
_RANK_TITLE_PREFIXES = {
    'أستاذ': 'أ.د.',
    'أستاذ مشارك': 'أ.د.',
    'أستاذ مساعد': 'د.',
    'محاضر': 'م.',
    'مساعد محاضر': 'م.',
    'معيد': 'أ.',
}

# /     /     >---- لاحقات المؤهل العلمي
_QUALIFICATION_TITLE_PREFIXES = {
    'دكتوراه': 'د.',
    'Ph.D': 'د.',
    'PhD': 'د.',
    'Doctorate': 'د.',
    'ماجستير': 'أ.',
    'ماجستير علوم': 'أ.',
    'Master': 'أ.',
    'بكالوريوس': 'أ.',
    'Bachelor': 'أ.',
    'دبلوم': 'أ.',
    'Diploma': 'أ.',
}

# ─────────────────────────────────────────────

# /     /     >---- نستنتج اللقب الأكاديمي من الرتبة أو المؤهل
def academic_title_prefix(rank_name=None, qual_name=None) -> str:
    """Return the academic title prefix derived from rank / qualification."""
    # /     /     >---- أول شي نشوف الرتبة العلمية
    if rank_name:
        prefix = _RANK_TITLE_PREFIXES.get(str(rank_name).strip())
        if prefix:
            return prefix
    # /     /     >---- إذا ما لقينا، نشوف المؤهل
    if qual_name:
        q = str(qual_name).strip()
        for key, prefix in _QUALIFICATION_TITLE_PREFIXES.items():
            if q == key or q.startswith(key):
                return prefix
    return ''

# ─────────────────────────────────────────────

# /     /     >---- الاسم الكامل للعرض: اللقب المُستنتج + الاسم
def teacher_display_name(name, rank_name=None, qual_name=None) -> str:
    """Full display name: derived academic title + plain stored name.

    Any prefix already embedded in the stored *name* is stripped first so the
    title is never duplicated, even for legacy rows like ``'د. أحمد محمد'``.
    """
    # /     /     >---- نشيل اللقب اللي في الاسم الأصلي أولاً
    plain = teacher_label(name)
    if plain in ('—', ''):
        return plain
    prefix = academic_title_prefix(rank_name, qual_name)
    return '{} {}'.format(prefix, plain) if prefix else plain

# ─────────────────────────────────────────────

# /     /     >---- نحسب مدة المحاضرة من وقت البدء والانتهاء (ساعة، ساعتان...)
def duration_label(start: str, end: str) -> str:
    if not start or not end:
        return ''
    try:
        # /     /     >---- نقرا الساعة والدقيقة من النص
        sh, sm = start.strip().split(':')[:2]
        eh, em = end.strip().split(':')[:2]
        total_min = (int(eh) * 60 + int(em)) - (int(sh) * 60 + int(sm))
    except (ValueError, TypeError):
        return ''
    # /     /     >---- إذا المدة ماعندش معنى نرجع فاضي
    if total_min <= 0:
        return ''
    hours = total_min // 60
    rem = total_min % 60
    # /     /     >---- إذا فيه باقي دقائق نرجع بالتقدير
    if rem:
        return 'ساعة' if hours == 0 else ('ساعتان' if hours == 2 else ('{} ساعة'.format(hours) if hours >= 11 else '{} ساعات'.format(hours)))
    # /     /     >---- المدة كاملة بالساعات مع الاسم العربي الصحيح
    if hours == 1:
        return 'ساعة'
    if hours == 2:
        return 'ساعتان'
    if hours >= 11:
        return '{} ساعة'.format(hours)
    return '{} ساعات'.format(hours)

# ─────────────────────────────────────────────

# /     /     >---- نحول الساعة من صيغة 24 إلى 12 ساعة مع مؤشر ص/م
def format_time12(value):
    """Convert a 'HH:MM' 24-hour string to 12-hour Arabic (ص/م) for display only.

    Examples: 09:00 -> '9:00 ص', 12:01 -> '12:01 م', 15:01 -> '3:01 م'.
    Empty or malformed values are returned unchanged.
    """
    if not value:
        return value or ''
    try:
        parts = str(value).strip().split(':')
        if len(parts) < 2:
            return value
        h = int(parts[0])
        m = int(parts[1])
    except (ValueError, TypeError):
        return value
    # /     /     >---- نشوف صباح (ص) أو مساء (م)
    period = 'ص' if h < 12 else 'م'
    h12 = h % 12
    if h12 == 0:
        h12 = 12
    return '{}:{:02d} {}'.format(h12, m, period)

# ─────────────────────────────────────────────

# /     /     >---- دالة الترقيم: تشغّل COUNT + صفحة من استعلام SQL
def paginate(
    query: str,
    params: Optional[List[Any]] = None,
    page: int = 1,
    per_page: int = PER_PAGE,
) -> Tuple[List[dict], int, int, int]:
    """Run a count + page query against a raw SQL SELECT string.

    Returns ``(rows, total, page, per_page)`` where *rows* is a list of dicts.
    """
    # /     /     >---- نحسب العدد الإجمالي بدون ORDER BY
    db = get_db()
    count_query = f"SELECT COUNT(*) FROM ({query.split('ORDER BY')[0]}) AS cnt"
    total = db.execute(count_query, params or []).fetchone()[0]
    # /     /     >---- نحسب الحيز ونجلب الصفوف
    offset = (page - 1) * per_page
    rows = db.execute(
        f'{query} LIMIT ? OFFSET ?', (params or []) + [per_page, offset]
    ).fetchall()
    # /     /     >---- نرجع الصفوف كقواميس مع الكل
    return [dict(r) for r in rows], total, page, per_page