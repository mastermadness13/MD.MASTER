#!/usr/bin/env python3
"""Import teacher + course NAMES from the college schedule into the database.

Scope (explicit user requirement):
  * Add teacher names to the ``teachers`` list.
  * Add course names to the ``courses`` list.
  * Nothing else: no relationships, no timetable, no teacher_taught_courses,
    no versions, no sections/days/times/rooms.

The schedule text is read from ``scripts/schedule_input.txt`` (or a path given
on the command line).  Two formats are understood:

  1. Tab-separated rows (same table as the HTML source), e.g.::

        Department<TAB>Semester<TAB>...<TAB>Teacher<TAB>Course<TAB>...

  2. Keep-style lines, e.g.::

        **قسم:** | **فصل:** | **مادة:** | **أستاذ:** | ...

Only the teacher and course cells are extracted; everything else is ignored.

No duplicates are inserted: an existing teacher/course is matched by exact
name first, then by :func:`utils.text.normalize_arabic_name` (handles
alef/hamza/teh-marbuta/yeh variants).  Matching is a comparison aid, not an
identity proof; near-duplicates are reported so you can review them.

Usage:
    python scripts/import_teachers_courses_from_schedule.py [path-to-schedule.txt]
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import Config  # noqa: E402
from utils.text import normalize_arabic_name  # noqa: E402

DEFAULT_INPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schedule_input.txt')

# Cell separators in the schedule file.  Tabs are the primary separator for
# pasted table rows; the Keep format uses " | ".
_TAB = '\t'
_PIPE = '|'
_KEEP_MARKER = '**'

# Prefix used for auto-generated course codes (guaranteed not to collide with
# the existing ع/ت/ه/GS/GE/GH conventions).
COURSE_CODE_PREFIX = 'IMP'

# Column label tokens used to locate Teacher / Course cells regardless of
# position in the row.
TEACHER_TOKENS = ('الأستاذ', 'الاستاذ', 'الأستاذة', 'الاستاذة', 'عضو هيئة التدريس',
                  'أعضاء هيئة التدريس', 'member')
COURSE_TOKENS = ('المادة', 'المقرر', 'المقررات', 'المادة الدراسية', 'subject',
                 'course')

# Deprecated/noise cells that should never be treated as names.
_IGNORED = frozenset({
    'الفصل', 'الفصل الدراسي', 'الفصل الاول', 'الفصل الثاني', 'الفصل الثالث',
    'الفصل الرابع', 'الفصل الخامس', 'الفصل السادس', 'الفصل السابع',
    'القسم', 'الوقت', 'الزمن', 'اليوم', 'السبت', 'الأحد', 'الاثنين',
    'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'الشعبة', 'القاعة', 'الرقم',
    'المجموعة', 'الوحدات', 'الساعات', 'المدة', 'الحصة',
})

# Strip prefixes that appear on teacher names in the schedule (أ./م./د. etc.)
_TITLE_PREFIX_RE = re.compile(r'^[أ-يدم]\.\s*', re.UNICODE)


def _split_cells(line: str) -> list[str]:
    """Split a schedule line into cells on tabs, or pipe-separated keep rows."""
    line = line.strip()
    if not line:
        return []
    if _TAB in line:
        return [c.strip() for c in line.split(_TAB)]
    if _PIPE in line:
        return [c.strip() for c in line.split(_PIPE)]
    return []


def _looks_like_keep_row(line: str) -> bool:
    return _KEEP_MARKER in line and _PIPE in line


def _clean_keep_cell(cell: str) -> str:
    """Turn a Keep-style cell like '**الأستاذ:**' into 'الأستاذ'."""
    return (cell.replace('**', '').replace('*', '').rstrip(':：').strip())


def _is_title_prefix(name: str) -> bool:
    """True if the name is just a title fragment (e.g. 'م.', 'أ.') with no name."""
    s = name.strip()
    s = _TITLE_PREFIX_RE.sub('', s)
    return not s


def _extract_teacher_from_cell(cell: str) -> str:
    """Extract a teacher name, removing the leading title (م./أ./د.)."""
    cell = (cell or '').strip()
    if not cell:
        return ''
    # Multi-teacher cell: 'م. انتصار العزابي / م. نسرين سلطان' -> first teacher.
    cell = cell.split('/')[0].strip()
    # Remove leading title like 'م.' 'أ.' 'د.'
    cell = _TITLE_PREFIX_RE.sub('', cell).strip()
    cell = re.sub(r'\s+', ' ', cell).strip(' .-—–')
    if _is_title_prefix(cell):
        return ''
    return cell


def _extract_course_from_cell(cell: str) -> str:
    cell = (cell or '').strip()
    if not cell:
        return ''
    return re.sub(r'\s+', ' ', cell).strip(' "“”".')


def _is_noise(cell: str) -> bool:
    s = cell.strip().strip(' "“”".').replace('\u200f', '')
    if not s:
        return True
    if s.lower() in _IGNORED or s in _IGNORED:
        return True
    if re.fullmatch(r'\d{1,2}(:\d{2})?', s):  # pure time like 8:00
        return True
    if re.fullmatch(r'\d+', s):  # pure number
        return True
    if re.search(r'(الفصل|الوقت|اليوم|القاعة|الشعبة|المجموعة|السبت|الأحد|الاثنين|الثلاثاء|الأربعاء|الخميس)', s):
        return True
    if re.match(r'قسم\s|شعبة\s|دفعة\s|مجموعة\s|فرقة\s', s):
        return True
    return False


def _parse_keep_row(cells: list[str]) -> tuple[str, str]:
    teacher = ''
    course = ''
    for raw in cells:
        cleaned = _clean_keep_cell(raw)
        # Keep cells combine label + value: 'الأستاذ: م. صبري الزروق'.
        if ':' in cleaned:
            head, _, val = cleaned.partition(':')
        else:
            head, val = cleaned, ''
        head = head.strip()
        val = val.strip()
        if head in TEACHER_TOKENS:
            t = _extract_teacher_from_cell(val)
            if t:
                teacher = t
        elif head in COURSE_TOKENS:
            co = _extract_course_from_cell(val)
            if co and not _is_noise(co):
                course = co
    return teacher, course


def _best_cell(cells: list[str], kind: str) -> tuple[str, int]:
    """Return (best cell text, its index) matching *kind* ('teacher'|'course')."""
    best = ''
    best_score = -1
    best_idx = -1
    for i, cell in enumerate(cells):
        s = cell.strip().strip(' "“”".').replace('\u200f', '')
        if not s or _is_noise(s):
            continue
        low = s.lower()
        if low in TEACHER_TOKENS or low in COURSE_TOKENS:
            continue
        has_title = bool(_TITLE_PREFIX_RE.match(s))
        letters = re.sub(r'[^\u0600-\u06FF]', '', s)
        words = len(s.split())
        digits = bool(re.search(r'\d', s))

        if kind == 'teacher':
            score = 0
            if has_title:
                score += 3
            if words >= 2 and len(letters) >= 4:
                score += 2
            if digits:
                score -= 2
            if words < 2 and not has_title:
                score -= 3
        else:
            score = 0
            if has_title:
                score -= 10
            if len(letters) >= 3:
                score += 2
            if 1 <= words <= 4:
                score += 1
            if not digits and words == 1:
                score -= 1
            if digits:
                score += 1
            # Department/faculty cells (قسم الاتصالات, القسم العام, ...) are
            # context, not course names.
            if re.search(r'(قسم|كلية|شعبة)', s):
                score -= 8
            # Prefer cells that appear later in the row (course comes after
            # department/level/day/time in tabular schedules).
            if i <= 2:
                score -= 2

        if score > best_score:
            best_score = score
            best = s
            best_idx = i
    return best, best_idx


def _parse_tab_row(cells: list[str]) -> tuple[str, str]:
    """Best-effort extraction from a free-form tab row."""
    teacher, tidx = _best_cell(cells, kind='teacher')
    course, cidx = _best_cell(cells, kind='course')
    if course and teacher and course == teacher and cidx == tidx:
        course = ''
    if teacher:
        teacher = _extract_teacher_from_cell(teacher)
    if course:
        course = _extract_course_from_cell(course)
    return teacher, course


def parse_schedule_text(text: str) -> list[tuple[str, str]]:
    """Return a list of (teacher, course) pairs extracted from the raw text."""
    pairs: list[tuple[str, str]] = []
    for line in text.splitlines():
        cells = _split_cells(line)
        if not cells or len(cells) < 2:
            continue

        if _looks_like_keep_row(line):
            t, c = _parse_keep_row(cells)
        else:
            t, c = _parse_tab_row(cells)

        if t and c:
            pairs.append((t, c))
    return pairs


def unique_pairs(pairs: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Preserve order, drop exact duplicates; return (unique, duplicates)."""
    seen = set()
    uniq: list[tuple[str, str]] = []
    dups: list[tuple[str, str]] = []
    for t, c in pairs:
        key = (normalize_arabic_name(t), normalize_arabic_name(c))
        if key in seen:
            dups.append((t, c))
        else:
            seen.add(key)
            uniq.append((t, c))
    return uniq, dups


def load_existing_normalized(db: sqlite3.Connection, table: str) -> dict[str, int]:
    rows = db.execute(f'SELECT id, name FROM {table}').fetchall()
    return {normalize_arabic_name(r[1]): r[0] for r in rows}


def next_course_code(db: sqlite3.Connection) -> str:
    existing = {
        r[0].strip().lower()
        for r in db.execute('SELECT code FROM courses WHERE code IS NOT NULL')
        if r[0]
    }
    n = 1
    while True:
        code = f'{COURSE_CODE_PREFIX}{n:03d}'
        if code.lower() not in existing:
            return code
        n += 1


def import_names(db_path: str, pairs: list[tuple[str, str]]) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        existing_t = load_existing_normalized(conn, 'teachers')
        existing_c = load_existing_normalized(conn, 'courses')

        # Unique course names and teacher names requested.
        req_teachers: dict[str, str] = {}  # norm -> display name
        req_courses: dict[str, str] = {}
        for t, c in pairs:
            if t:
                n = normalize_arabic_name(t)
                req_teachers.setdefault(n, t)
            if c:
                n = normalize_arabic_name(c)
                req_courses.setdefault(n, c)

        new_teachers: list[str] = []
        existing_teachers: list[str] = []
        for norm, display in req_teachers.items():
            if norm in existing_t:
                existing_teachers.append(display)
            else:
                new_teachers.append(display)

        new_courses: list[str] = []
        existing_courses: list[str] = []
        for norm, display in req_courses.items():
            if norm in existing_c:
                existing_courses.append(display)
            else:
                new_courses.append(display)

        # Insert new teachers (name is the only NOT NULL column).
        for name in new_teachers:
            conn.execute('INSERT INTO teachers (name) VALUES (?)', (name,))
        # Insert new courses (code NOT NULL, name NOT NULL; year defaults to 1).
        for name in new_courses:
            code = next_course_code(conn)
            conn.execute(
                'INSERT INTO courses (code, name) VALUES (?, ?)',
                (code, name),
            )
        conn.commit()

        return {
            'teachers_requested': len(req_teachers),
            'new_teachers': new_teachers,
            'existing_teachers': existing_teachers,
            'courses_requested': len(req_courses),
            'new_courses': new_courses,
            'existing_courses': existing_courses,
        }
    finally:
        conn.close()


def read_input(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', nargs='?', default=DEFAULT_INPUT,
                        help='Path to the schedule text file (default: %(default)s)')
    parser.add_argument('--db', default=Config.DATABASE,
                        help='Database path (default: config.ini DATABASE)')
    parser.add_argument('--skip-backup', action='store_true',
                        help='Do not create a backup before importing')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f'ERROR: schedule input not found: {args.input}')
        print('Paste the schedule text into scripts/schedule_input.txt and re-run.')
        return 2

    text = read_input(args.input)
    pairs = parse_schedule_text(text)
    if not pairs:
        print('ERROR: no (teacher, course) pairs could be parsed from the input.')
        print('Check that the schedule is pasted in scripts/schedule_input.txt')
        return 3

    uniq, dups = unique_pairs(pairs)
    print(f'Parsed {len(pairs)} cell-pairs, {len(uniq)} unique after normalization, '
          f'{len(dups)} duplicate pairs skipped.')
    print()

    if not args.skip_backup:
        from scripts.backup_db import backup_database
        try:
            backup_database()
        except SystemExit:
            print('WARNING: backup failed; continuing without it.')

    result = import_names(args.db, uniq)
    print('===== RESULTS =====')
    print(f'Teachers requested : {result["teachers_requested"]}')
    print(f'  new (added)      : {len(result["new_teachers"])}')
    print(f'  already existed  : {len(result["existing_teachers"])}')
    print(f'Courses requested  : {result["courses_requested"]}')
    print(f'  new (added)      : {len(result["new_courses"])}')
    print(f'  already existed  : {len(result["existing_courses"])}')
    if result['new_teachers']:
        print('\nNew teachers:')
        for n in result['new_teachers']:
            print('  +', n)
    if result['new_courses']:
        print('\nNew courses (with generated codes):')
        placeholders = ','.join('?' * len(result['new_courses']))
        conn = sqlite3.connect(args.db)
        code_map = {r[1]: r[0] for r in conn.execute(
            f'SELECT code, name FROM courses WHERE name IN ({placeholders})',
            result['new_courses'])}
        conn.close()
        for n in result['new_courses']:
            print(f'  + {code_map.get(n, "?")}  {n}')
    if result['existing_courses']:
        print('\nAlready existing courses:')
        for n in result['existing_courses']:
            print('  =', n)
    return 0


if __name__ == '__main__':
    sys.exit(main())