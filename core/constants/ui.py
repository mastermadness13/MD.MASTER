"""UI / presentation constants — Arabic labels, calendars, and palettes."""

# ── Academic calendar ─────────────────────────────────────────────────────────
SEMESTER_LABELS = {
    1: 'الفصل الأول',
    2: 'الفصل الثاني',
    3: 'الفصل الثالث',
    4: 'الفصل الرابع',
    5: 'الفصل الخامس',
    6: 'الفصل السادس',
    7: 'الفصل السابع',
}

# ── Named semester seasons (ربيع / خريف) ────────────────────────────────────
SEMESTER_SEASONS = {
    'spring': 'ربيع',
    'fall': 'خريف',
}

SEMESTER_SEASONS_EN = {
    'spring': 'Spring',
    'fall': 'Fall',
}

SEMESTER_SEASON_ORDER = ['fall', 'spring']

SEMESTER_SEASON_NEXT = {
    'fall': 'spring',
    'spring': 'fall',
}

WEEK_DAYS = ['السبت', 'الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس']

# Alternate spelling used in some timetable queries — kept for compatibility.
WEEK_DAYS_ALT = ['السبت', 'الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس']

DAY_ORDER = ['السبت', 'الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس']

# ── Exam periods ──────────────────────────────────────────────────────────────
ARABIC_MONTHS = {
    1: 'يناير', 2: 'فبراير', 3: 'مارس', 4: 'أبريل',
    5: 'مايو', 6: 'يونيو', 7: 'يوليو', 8: 'أغسطس',
    9: 'سبتمبر', 10: 'أكتوبر', 11: 'نوفمبر', 12: 'ديسمبر',
}

ARABIC_DAYS = {
    'Saturday': 'السبت', 'Sunday': 'الأحد', 'Monday': 'الاثنين',
    'Tuesday': 'الثلاثاء', 'Wednesday': 'الأربعاء', 'Thursday': 'الخميس',
    'Friday': 'الجمعة',
}

# ── Teacher color palette (for timetable grid) ────────────────────────────────
TIMETABLE_PALETTE = [
    '#3B82F6', '#10B981', '#F59E0B', '#EF4444',
    '#8B5CF6', '#EC4899', '#14B8A6', '#F97316',
]

# ── Course icon map ───────────────────────────────────────────────────────────
COURSE_ICON_MAP = {
    'هندسة وصفية': '\U0001f4d0',
    'أسس كهرباء': '\u26a1',
    'استاتيكا': '\U0001f3d7\ufe0f',
    'رياضيات': '\U0001f4cf',
    'فيزياء': '\U0001f52c',
    'كيمياء': '\u2697\ufe0f',
    'حاسب آلي': '\U0001f4bb',
    'شبكات': '\U0001f517',
    'برمجة': '\U0001f4dd',
    'قواعد بيانات': '\U0001f4da',
    'أنظمة تشغيل': '\U0001f5a5\ufe0f',
    'هندسة برمجيات': '\U0001f6e0\ufe0f',
    'أمن معلومات': '\U0001f512',
    'ذكاء اصطناعي': '\U0001f916',
    'تصميم': '\U0001f3a8',
    'عمارة': '\U0001f3d8\ufe0f',
    'إلكترونيات': '\U0001f4e1',
    'اتصالات': '\U0001f4e1',
    'مدني': '\U0001f3d7\ufe0f',
    'نفط': '\U0001f6e2\ufe0f',
    'ميkanika': '\u2699\ufe0f',
    'thermodynamics': '\U0001f321\ufe0f',
    'fluids': '\U0001f4a7',
    'materials': '\U0001faa8',
    'control': '\U0001f39b\ufe0f',
    'power': '\u26a1',
    'signals': '\U0001f4e1',
    'circuits': '\U0001f50c',
    'microprocessor': '\U0001f4a0',
    'dsp': '\U0001f3b5',
    'communication': '\U0001f4ac',
    'antenna': '\U0001f4e1',
    'microwave': '\U0001f375',
    'optics': '\U0001f526',
    'satellite': '\U0001f6f0\ufe0f',
    'os': '\U0001f5a5\ufe0f',
    'data structures': '\U0001f4da',
    'algorithms': '\U0001f9ee',
    'compiler': '\U0001f4dc',
    'ai': '\U0001f916',
    'machine learning': '\U0001f9e0',
    'web': '\U0001f310',
    'mobile': '\U0001f4f1',
    'security': '\U0001f512',
    'database': '\U0001f4c2',
    'network': '\U0001f517',
    'cloud': '\u2601\ufe0f',
    'devops': '\U0001f6e0\ufe0f',
    'testing': '\u2705',
    'project': '\U0001f4c5',
    'management': '\U0001f4ca',
    'math': '\U0001f4cf',
    'statistics': '\U0001f4ca',
    'physics': '\U0001f52c',
    'chemistry': '\u2697\ufe0f',
    'english': '\U0001f4d6',
    'arabic': '\U0001f4dc',
    'islamic': '\U0001f54c',
    'general': '\U0001f4da',
}
