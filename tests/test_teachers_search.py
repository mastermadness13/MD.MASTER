"""Tests for the smart (folded) Arabic teachers-search feature.

Layers covered
--------------
A. Pure functions  — ``utils.text`` folding / LIKE escaping and
   ``services.search.search_terms``.
B. SQL shape       — ``build_text_search_where`` / ``build_teacher_search``
   emit exactly the predicates the design promises (ESCAPE clauses, AND
   between token groups, OR between columns, one top-level ORDER BY).
C. Route behaviour — real query execution against a seeded temp DB through
   ``GET /teachers``, the AJAX fragment, ``/teachers/api/bulk-ids`` and
   ``/teachers/api/teacher-pool``.
D. Regression      — the legacy ``else`` branch of ``build_search_query``
   must stay untouched for every non-teacher page, ``paginate``'s
   ``split('ORDER BY')`` count query must stay correct, and a teacher with
   NULL columns must still render without leaking ``None``.

Design notes that must not be "fixed" (approved behaviour)
----------------------------------------------------------
* ``search_terms`` drops punctuation-only tokens, so
  ``build_text_search_where(['t.name'], '%')`` returns ``('', [])`` and the
  route therefore lists *all* rows.  The wildcard-safety guarantee is
  asserted at the route level (test_lone_percent_returns_every_row_by_design).
* ``normalize_arabic_name`` folds ئ (U+0626) -> ي, so
  ``search_terms('رئيس قسم') == ['رييس', 'قسم']``.  Folding is applied to both
  sides of the comparison, so matching still works.
"""

from __future__ import annotations

import re
from urllib.parse import quote

import pytest

try:                                       # current layout
    import database.flask_db as flask_db
except ModuleNotFoundError:                # refactor in flight: adapter hoisted to the root
    import flask_db                        # noqa: F401
from database.connection import connect
from database.schema import ensure_schema
from services.search import (
    MAX_SEARCH_LENGTH,
    build_course_search,
    build_department_search,
    build_room_search,
    build_teacher_search,
    build_text_search_where,
    build_user_search,
    search_terms,
)
from utils.format import paginate
from utils.text import (
    escape_like,
    normalize_arabic_name,
    normalize_search_text,
)

# Reuse (do not re-invent) the teacher-pool fixture + its seeded rows.
from tests.test_teacher_pool import db_fx  # noqa: F401  (fixture reuse)

# ─────────────────────────────────────────────────────────────────────────────
# Arabic literals used by the assertions (kept as escapes so the source file
# stays readable in editors that mangle RTL text).
# ─────────────────────────────────────────────────────────────────────────────
AHMED_FOLDED = '\u0627\u062d\u0645\u062f'                    # احمد
AHMED_HAMZA = '\u0623\u062d\u0645\u062f'                     # أحمد
AHMED_HAMZA_BELOW = '\u0625\u062d\u0645\u062f'               # إحمد
AHMED_MADDA = '\u0622\u062d\u0645\u062f'                     # آحمد
ALEF_WASLA_AHMED = '\u0671\u062d\u0645\u062f'                # ٱحمد
AHMED_MAHMOUD = '\u0623\u062d\u0645\u062f \u0645\u062d\u0645\u0648\u062f'   # أحمد محمود
AHMED_DELETED = '\u0623\u062d\u0645\u062f \u0645\u062d\u0630\u0648\u0641'   # أحمد محذوف
IBRAHIM_SAIF = '\u0625\u0628\u0631\u0627\u0647\u064a\u0645 \u0633\u064a\u0641'  # إبراهيم سيف
AMNE_HADDAD = '\u0622\u0645\u0646\u0629 \u062d\u062f\u0651\u0627\u062f'     # آمنة حدّاد
MUHAMMAD_ALI = '\u0645\u062d\u0645\u062f \u0639\u0644\u064a'                 # محمد علي
POSITION_HOD = ('\u0631\u0626\u064a\u0633 \u0627\u0644\u0642\u0633\u0645 '
                '\u0627\u0644\u0639\u0644\u0645\u0649')                     # رئيس القسم العلمي
POSITION_HAMZA = '\u0631\u0626\u064a\u0633 \u0642\u0633\u0645'              # رئيس قسم
POSITION_SUPERVISOR = '\u0645\u0634\u0631\u0641'                            # مشرف
DEPT_MATH = '\u0642\u0633\u0645 \u0627\u0644\u0631\u064a\u0627\u0636\u064a\u0627\u062a'   # قسم الرياضيات
DEPT_PHYS = '\u0642\u0633\u0645 \u0627\u0644\u0641\u064a\u0632\u064a\u0627\u0621'     # قسم الفيزياء
RANK_ASSISTANT = '\u0623\u0633\u062a\u0627\u0630 \u0645\u0633\u0627\u0639\u062f'        # أستاذ مساعد
QUAL_PHD = '\u062f\u0643\u062a\u0648\u0631\u0627\u0647'                            # دكتوراه
COUNT_SUFFIX = '\u0639\u0636\u0648'    # عضو — the text after the count number


# ─────────────────────────────────────────────────────────────────────────────
# Small assertion helpers
# ─────────────────────────────────────────────────────────────────────────────

def _unwrap(sql: str) -> str:
    """Strip one balanced outer ``(...)`` wrapper, if present.

    ``build_text_search_where`` always wraps its result in one pair of
    parentheses, so the "top level" of the predicate body sits at depth 1 in
    the raw string.
    """
    sql = sql.strip()
    if sql.startswith('(') and sql.endswith(')'):
        return sql[1:-1]
    return sql


def _at_depth_zero(sql: str, needle: str) -> int:
    """Count non-overlapping occurrences of *needle* outside any parentheses."""
    count = 0
    depth = 0
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif depth == 0 and sql.startswith(needle, i):
            count += 1
            i += len(needle)
            continue
        i += 1
    return count


def _unescaped_percent_count(value: str) -> int:
    """Number of ``%`` in *value* that are not preceded by a backslash."""
    total = 0
    for idx, ch in enumerate(value):
        if ch != '%':
            continue
        backslashes = 0
        j = idx - 1
        while j >= 0 and value[j] == '\\':
            backslashes += 1
            j -= 1
        if backslashes % 2 == 0:
            total += 1
    return total


def _names(html: str) -> list:
    """Displayed teacher names from the AJAX fragment, with tags stripped."""
    return [
        re.sub(r'<[^>]+>', '', raw).strip()
        for raw in re.findall(
            r'<p class="font-bold text-on-surface">(.*?)</p>', html, re.S
        )
    ]


def _row_ids(html: str) -> set:
    """Checkbox ``value`` attributes — only rendered for ``teachers.manage``."""
    return {int(m) for m in re.findall(r'name="teacher_ids" value="(\d+)"', html)}


def _search_qs(term, **extra) -> str:
    """Build a percent-encoded query string for ``?search=<term>``."""
    parts = [f'search={quote(str(term))}']
    parts += [f'{k}={quote(str(v))}' for k, v in extra.items()]
    return '?' + '&'.join(parts)


def _count_text(n: int) -> str:
    """The exact ``<span data-count-value>`` payload the fragment must emit."""
    return f'<span data-count-value>{n} {COUNT_SUFFIX}</span>'


# ─────────────────────────────────────────────────────────────────────────────
# Seeded database + logged-in client
# ─────────────────────────────────────────────────────────────────────────────

def _mkdb(tmp_path):
    """Create the seeded database the route tests run against.

    ``teachers.deleted_at`` only exists after ``ensure_schema`` runs, so the
    soft-deleted fixture row is inserted (and stamped) *after* the migration.
    """
    p = tmp_path / 's'
    p.mkdir(parents=True, exist_ok=True)
    db_path = p / 'search.db'
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)

    conn.execute(
        "INSERT INTO departments (name, semesters, majors, hidden, has_sections, type) "
        "VALUES (?, 4, 4, 0, 1, 'academic')", (DEPT_MATH,),
    )
    conn.execute(
        "INSERT INTO departments (name, semesters, majors, hidden, has_sections, type) "
        "VALUES (?, 4, 4, 0, 1, 'academic')", (DEPT_PHYS,),
    )
    math_id = conn.execute(
        'SELECT id FROM departments WHERE name = ?', (DEPT_MATH,)
    ).fetchone()['id']
    phys_id = conn.execute(
        'SELECT id FROM departments WHERE name = ?', (DEPT_PHYS,)
    ).fetchone()['id']

    # The account linked to a teacher — the username/email search columns.
    conn.execute(
        "INSERT INTO users (username, password, role, label, email, department_id) "
        "VALUES ('ahmed.m', 'x', 'faculty_affairs', ?, ?, NULL)",
        (AHMED_MAHMOUD, 'ahmed@uni.edu'),
    )
    user_id = conn.execute(
        'SELECT id FROM users WHERE username = ?', ('ahmed.m',)
    ).fetchone()['id']
    conn.execute(
        'INSERT OR IGNORE INTO user_roles (user_id, role) VALUES (?, ?)',
        (user_id, 'faculty_affairs'),
    )

    # Two *real* accounts so the app resolves the active role from the DB
    # instead of trusting an injected session.  ``app.before_request``'s
    # ``enforce_session_version`` rewrites ``session['role']`` to
    # ``highest_priority_role(user_roles)`` whenever the injected role is not
    # in the account's granted set — and the bootstrap ``office_manager``
    # (id 1) is granted ``faculty_affairs`` only, so logging in as
    # ``head_of_department`` with ``user_id=1`` silently becomes faculty_affairs.
    for username, role, dept in (
        ('ff', 'faculty_affairs', None),
        ('hodm', 'head_of_department', math_id),
    ):
        conn.execute(
            'INSERT INTO users (username, password, role, label, department_id) '
            'VALUES (?, ?, ?, ?, ?)', (username, 'x', role, username, dept),
        )
        uid = conn.execute(
            'SELECT id FROM users WHERE username = ?', (username,)
        ).fetchone()['id']
        conn.execute(
            'INSERT OR IGNORE INTO user_roles (user_id, role) VALUES (?, ?)',
            (uid, role),
        )

    conn.execute(
        'INSERT INTO qualifications (name_ar, name_en) VALUES (?, ?)',
        (QUAL_PHD, 'PhD'),
    )
    qual_id = conn.execute(
        'SELECT id FROM qualifications WHERE name_ar = ?', (QUAL_PHD,)
    ).fetchone()['id']
    conn.execute(
        'INSERT INTO academic_ranks (name_ar, name_en, sort_order) VALUES (?, ?, 1)',
        (RANK_ASSISTANT, 'Assistant Professor'),
    )
    rank_id = conn.execute(
        'SELECT id FROM academic_ranks WHERE name_ar = ?', (RANK_ASSISTANT,)
    ).fetchone()['id']

    rows = [
        # name, position, academic_number, dept, user, qualification_id, rank_id
        (AHMED_MAHMOUD, POSITION_HOD, 'AN-001', math_id, user_id, qual_id, rank_id),
        (IBRAHIM_SAIF, POSITION_SUPERVISOR, 'AN-002', math_id, None, qual_id, None),
        (AMNE_HADDAD, None, 'AN-003', phys_id, None, None, rank_id),
        (MUHAMMAD_ALI, None, None, phys_id, None, None, None),
        (AHMED_DELETED, POSITION_HOD, 'AN-005', math_id, None, None, None),
    ]
    ids = {}
    for name, position, acnum, dept, uid, qid, rid in rows:
        cur = conn.execute(
            'INSERT INTO teachers (name, position, academic_number, department_id, '
            'user_id, qualification_id, rank_id) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (name, position, acnum, dept, uid, qid, rid),
        )
        tid = cur.lastrowid
        ids[name] = tid
        # Many-to-one membership row so the EXISTS branch is exercised.
        conn.execute(
            'INSERT OR IGNORE INTO teacher_departments (teacher_id, department_id) '
            'VALUES (?, ?)', (tid, dept),
        )

    # Soft-delete the twin. ``deleted_at`` is added by ensure_schema, not schema.sql.
    conn.execute(
        'UPDATE teachers SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?',
        (ids[AHMED_DELETED],),
    )

    conn.commit()
    conn.close()
    return str(db_path), {
        'math_id': math_id,
        'phys_id': phys_id,
        'user_id': user_id,
        'ids': ids,
    }


#: Single-slot holder so :func:`_login` can resolve ids without a fixture.
FIXTURE_DB_PATH = [None]


def _login(c, username, role, **extra):
    """Populate the session the way the real login path does.

    ``user_id`` must be the account that actually *holds* the role: the
    ``enforce_session_version`` before_request hook re-derives
    ``session['role']`` from ``user_roles`` whenever the injected role is not
    in the granted set, which silently turns a ``head_of_department`` session
    into ``faculty_affairs`` for the bootstrap ``office_manager`` account.
    """
    db = connect(FIXTURE_DB_PATH[0])
    row = db.execute(
        'SELECT id, session_version FROM users WHERE username = ?', (username,)
    ).fetchone()
    db.close()
    assert row is not None, f'no seeded users row named {username!r}'
    with c.session_transaction() as s:
        s['user_id'] = row['id']
        s['role'] = role
        s['roles'] = [role]
        s['username'] = username
        s['session_version'] = row['session_version']
        s['department_id'] = None
        s['_csrf_token'] = 't'
        for key, value in extra.items():
            s[key] = value


@pytest.fixture
def search_setup(tmp_path, monkeypatch, app_fx):
    """Seeded DB wired into ``flask_db`` + a test client.

    ``get_db()`` calls ``database.connection.connect`` per request, which is
    what registers the ``normalize_search`` UDF, so no UDF needs priming here.
    """
    db_path, ids = _mkdb(tmp_path)
    monkeypatch.setattr(flask_db, 'DATABASE', db_path)
    FIXTURE_DB_PATH[0] = db_path
    ids['db_path'] = db_path
    ids['app'] = app_fx
    ids['client'] = app_fx.test_client()
    return ids


@pytest.fixture
def office(search_setup):
    """The client already logged in as faculty_affairs (teachers.view+manage)."""
    _login(search_setup['client'], 'ff', 'faculty_affairs')
    return search_setup['client']


# ═════════════════════════════════════════════════════════════════════════════
# A. Pure-function unit tests (no DB)
# ═════════════════════════════════════════════════════════════════════════════

def test_alef_and_hamza_forms_all_fold_together():
    """Every alef/hamza carrier folds onto bare alef."""
    for raw in (AHMED_HAMZA, AHMED_HAMZA_BELOW, AHMED_MADDA,
                ALEF_WASLA_AHMED, AHMED_FOLDED):
        assert normalize_search_text(raw) == AHMED_FOLDED, (
            f'{raw!r} did not fold to {AHMED_FOLDED!r}; got '
            f'{normalize_search_text(raw)!r}'
        )


def test_alef_maqsura_and_yeh_fold_together():
    left = normalize_search_text('\u0645\u0635\u0637\u0641\u0649')   # مصطفى
    right = normalize_search_text('\u0645\u0635\u0637\u0641\u064a')   # مصطفي
    assert left == right == '\u0645\u0635\u0637\u0641\u064a'


def test_taa_marbuta_folds_to_ha():
    """ة (U+0629) folds onto ه (U+0647).

    NOTE: the literal example in the brief — ``normalize_search_text('قسم') ==
    normalize_search_text('قسمة')`` — is unsatisfiable: 'قسم' contains no taa
    marbuta at all, so the two strings differ by a character.  The pair below
    is the real ة -> ه case and the direction is pinned explicitly.
    """
    assert normalize_search_text(
        '\u0645\u062f\u0631\u0633\u0629'          # مدرسة
    ) == normalize_search_text(
        '\u0645\u062f\u0631\u0633\u0647'          # مدرسه
    )
    assert normalize_search_text('\u0642\u0633\u0645\u0629') == '\u0642\u0633\u0645\u0647'
    # A word with no ة is of course unaffected.
    assert normalize_search_text('\u0642\u0633\u0645') == '\u0642\u0633\u0645'


def test_tashkeel_and_tatweel_are_stripped():
    raw = '\u0623\u062d\u0645\u064e\u0640\u0640\u0640\u0640\u062f'   # أحمَــــد
    assert normalize_search_text(raw) == AHMED_FOLDED


def test_arabic_indic_and_extended_digits_fold_to_ascii():
    assert normalize_search_text(
        '\u0631\u0642\u0645 \u0664\u0662'          # رقم ٤٢
    ) == '\u0631\u0642\u0645 42'
    assert normalize_search_text(
        '\u0631\u0642\u0645 \u06f4\u06f2'          # رقم ۴۲
    ) == '\u0631\u0642\u0645 42'


def test_latin_is_lowercased():
    assert normalize_search_text('AhMed') == 'ahmed'


@pytest.mark.parametrize('falsy', [None, '', 0, [], {}])
def test_falsy_input_returns_empty_string(falsy):
    assert normalize_search_text(falsy) == ''


def test_bidi_marks_and_whitespace_are_stripped():
    raw = '\u200f\u0623\u062d\u0645\u062f\u200e  \u00a0 '
    assert normalize_search_text(raw) == AHMED_FOLDED


def test_legacy_normalize_arabic_name_does_not_fold_taa_marbuta():
    """``normalize_arabic_name`` is unchanged — it must NOT fold ة -> ه.

    Guards the dedup migration: if the legacy helper were made to delegate to
    :func:`normalize_search_text`, two genuinely different names
    (``قسم`` / ``قسمة``) would collapse into one.
    """
    assert normalize_arabic_name('\u0642\u0633\u0645\u0629') == '\u0642\u0633\u0645\u0629'
    assert normalize_arabic_name('\u0642\u0633\u0645') == '\u0642\u0633\u0645'
    assert normalize_arabic_name('\u0642\u0633\u0645\u0629') != normalize_arabic_name(
        '\u0642\u0633\u0645'
    )


def test_escape_like_escapes_every_like_metacharacter():
    raw = '100%_x\\'
    out = escape_like(raw)
    assert out == '100\\%\\_x\\\\'
    # Only the *intentionally* escaped forms remain: nothing is left bare.
    assert _unescaped_percent_count(out) == 0
    assert not re.search(r'(?<!\\)_', out)
    # Falsy input short-circuits to ''.
    assert escape_like(None) == ''
    assert escape_like('') == ''


def test_search_terms_splits_dedups_and_preserves_order():
    ali = '\u0639\u0644\u064a'                       # علي
    raw = f'\u0645\u062d\u0645\u0648\u062f {AHMED_FOLDED} {AHMED_FOLDED} {ali}'
    terms = search_terms(raw)
    assert terms == ['\u0645\u062d\u0645\u0648\u062f', AHMED_FOLDED, ali]
    # Non-vacuity: none of the chosen tokens contains ئ, so they are
    # unaffected by the legacy ئ -> ي fold.
    for term in terms:
        assert '\u0626' not in term


@pytest.mark.parametrize('junk', ['', '   ', '...', '%%', '%%%', '-.,;:/\\',
                                  '\u061f\u061f', None])
def test_search_terms_returns_empty_for_unusable_input(junk):
    assert search_terms(junk) == []


def test_underscore_alone_is_a_usable_but_escaped_token():
    """``_`` is a word character, so it survives tokenisation — but it is
    escaped, so it only ever matches a literal underscore (never any char)."""
    assert search_terms('_') == ['_']
    sql, params = build_text_search_where(['t.name'], '_')
    assert params == ['%\\_%']
    assert "ESCAPE '\\'" in sql


def test_search_terms_caps_token_count_at_max_tokens():
    assert search_terms('a b c d e f', max_tokens=2) == ['a', 'b']
    assert search_terms('a b c d', max_tokens=1) == ['a']
    # The default cap is 4.
    assert search_terms('a b c d e') == ['a', 'b', 'c', 'd']
    assert len(search_terms('a b c d e f g h', max_tokens=4)) == 4


def test_search_terms_truncates_input_at_max_search_length():
    assert MAX_SEARCH_LENGTH == 120
    over = 'x' * (MAX_SEARCH_LENGTH + 50)
    assert search_terms(over) == search_terms('x' * MAX_SEARCH_LENGTH)
    # A long multi-token query is cut at the same point as its own prefix.
    long_query = ' '.join(f'tok{i}' for i in range(60))
    assert len(long_query) > MAX_SEARCH_LENGTH
    assert search_terms(long_query, max_tokens=100) == search_terms(
        long_query[:MAX_SEARCH_LENGTH], max_tokens=100
    )
    assert len(search_terms(long_query, max_tokens=100)) < 100


def test_search_terms_folds_hamza_on_ayin_before_splitting():
    """Lock in the ACTUAL folded behaviour for a token that contains ئ.

    ``normalize_arabic_name`` maps ئ (U+0626) -> ي, so ``رئيس`` becomes
    ``رييس``.  Both sides of the SQL comparison are folded, so matching still
    works; this test exists so that a future change to the fold table is a
    deliberate, visible edit rather than a silent behaviour shift.
    """
    assert search_terms(POSITION_HAMZA) == [
        '\u0631\u064a\u064a\u0633', '\u0642\u0633\u0645'
    ]
    # ... and the fold is symmetric, which is what keeps matching correct.
    assert normalize_search_text(POSITION_HAMZA).startswith('\u0631\u064a\u064a\u0633')


# ═════════════════════════════════════════════════════════════════════════════
# B. SQL-shape unit tests
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('junk', ['', '   ', '%%', '%', '%%%', '...'])
def test_no_usable_token_yields_no_clause(junk):
    assert build_text_search_where(['t.name'], junk) == ('', [])


def test_no_columns_yields_no_clause():
    """An empty column list must not emit a malformed predicate."""
    assert build_text_search_where([], 'ahmed') == ('', [])
    assert build_text_search_where((), AHMED_FOLDED) == ('', [])


def test_ascii_token_uses_plain_like_and_skips_the_udf():
    sql, params = build_text_search_where(['t.name'], 'ahmed')
    assert 'normalize_search(' not in sql
    assert 'LIKE ?' in sql
    assert params == ['%ahmed%']


def test_arabic_token_uses_udf_and_every_like_carries_escape():
    sql, params = build_text_search_where(['t.name'], AHMED_FOLDED)
    assert f"normalize_search(t.name) LIKE ? ESCAPE '\\'" in sql
    assert sql.count('LIKE ?') == 2, 'expected folded predicate + raw fallback'
    assert sql.count("ESCAPE '\\'") == sql.count('LIKE ?')
    assert params == [f'%{AHMED_FOLDED}%'] * 2


def test_raw_fallback_can_be_disabled():
    sql, _params = build_text_search_where(
        ['t.name'], AHMED_FOLDED, raw_fallback=False
    )
    assert sql.count('LIKE ?') == 1
    assert f"normalize_search(t.name) LIKE ? ESCAPE '\\'" in sql


def test_two_tokens_produce_one_top_level_and_between_parenthesised_groups():
    sql, _params = build_text_search_where(
        ['t.name', 't.position'], f'{AHMED_FOLDED} \u0642\u0633\u0645'
    )
    assert _at_depth_zero(_unwrap(sql), 'AND') == 1, sql
    # The whole thing is one parenthesised group of two parenthesised groups.
    assert sql.startswith('((') and sql.endswith('))')
    # No further AND was smuggled inside a token group.
    assert sql.count(' AND ') == 1


def test_placeholder_count_matches_parameter_count():
    for term in (AHMED_FOLDED, 'ahmed', f'{AHMED_FOLDED} \u0642\u0633\u0645',
                 'a_b', 'ahmed AN-001'):
        sql, params = build_text_search_where(
            ['t.name', 't.position', 'd.name'], term
        )
        assert sql.count('?') == len(params), (term, sql, params)


def test_wildcards_in_params_are_escaped():
    term = '100%_x\\'
    _sql, params = build_text_search_where(['t.name'], term)
    assert params, 'expected at least one bound pattern'
    for pattern in params:
        assert pattern == f'%{escape_like(term)}%'
        # The wrap delimiters are the ONLY unescaped '%' in the pattern.
        assert _unescaped_percent_count(pattern) == 2, pattern
        assert pattern.startswith('%') and pattern.endswith('%')


def test_teacher_search_emits_exactly_one_top_level_order_by():
    """``utils.format.paginate`` builds its count query from
    ``query.split('ORDER BY')[0]`` — a second ORDER BY would be swallowed
    into the WHERE and the count would silently be wrong."""
    query, _params, _dept = build_teacher_search(AHMED_FOLDED, '', None, 1)
    assert query.upper().count('ORDER BY') == 1
    assert _at_depth_zero(query.upper(), 'ORDER BY') == 1
    assert query.rstrip().upper().endswith('ORDER BY T.NAME')


def test_teacher_search_without_a_search_term_emits_no_udf():
    query, params, _dept = build_teacher_search('', '', None, 1)
    assert 'normalize_search(' not in query
    assert params == []
    assert query.upper().count('ORDER BY') == 1


def test_teacher_search_keeps_teacher_departments_inside_exists():
    query, params, dept = build_teacher_search(AHMED_FOLDED, '7', None, 1)
    assert 'JOIN teacher_departments' not in query
    assert 'FROM teacher_departments tdx' in query
    assert params[-2:] == [7, 7]
    assert dept == '7'


def test_teacher_search_user_department_overrides_the_request_filter():
    query, params, dept = build_teacher_search('', '2', 1, 1)
    assert dept == '1'
    assert params == [1, 1]
    assert '= ?' in query


def test_search_text_is_never_interpolated_into_the_sql_string():
    needle = '\u0630\u0647\u0628\u0627\u0633\u064a'
    query, params, _dept = build_teacher_search(needle, '', None, 1)
    assert needle not in query
    assert f'%{needle}%' in params

    # A SQL-injection attempt is tokenised, folded and bound — never spliced.
    # (search_terms splits on spaces, so 'DROP TABLE' arrives as two tokens;
    # what matters is that nothing but the LIKE pattern reaches a parameter
    # and no statement terminator reaches the SQL string.)
    boom = "x'; DROP TABLE teachers; --"
    query2, params2, _ = build_teacher_search(boom, '', None, 1)
    assert 'DROP' not in query2
    assert '--' not in query2
    for pattern in params2:
        assert pattern.startswith('%') and pattern.endswith('%'), pattern
        assert not any(ord(ch) < 32 for ch in pattern), pattern
    assert query2.count('?') == len(params2)


# ═════════════════════════════════════════════════════════════════════════════
# C. Route integration tests (real query execution)
# ═════════════════════════════════════════════════════════════════════════════

def _ajax(client, query_string=''):
    return client.get(
        f'/teachers{query_string}',
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )


@pytest.mark.parametrize('term', [AHMED_FOLDED, AHMED_HAMZA, AHMED_HAMZA_BELOW])
def test_search_without_hamza_finds_the_hamza_row(office, search_setup, term):
    r = _ajax(office, _search_qs(term))
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert _row_ids(html) == {search_setup['ids'][AHMED_MAHMOUD]}, _names(html)


def test_search_result_is_not_vacuous(office, search_setup):
    """The same request without a search term returns more than one row."""
    html = office.get('/teachers').get_data(as_text=True)
    assert len(_row_ids(html)) == 4
    assert any(AMNE_HADDAD in n for n in _names(html)), (
        'fixture row آمنة حدّاد missing — the exclusion assertions elsewhere '
        'would pass vacuously'
    )
    assert not any(AHMED_DELETED in n for n in _names(html))


def test_search_position_only_matches_the_hod_row(office, search_setup):
    r = _ajax(office, _search_qs(POSITION_HAMZA))
    html = r.get_data(as_text=True)
    assert _row_ids(html) == {search_setup['ids'][AHMED_MAHMOUD]}, _names(html)
    # The soft-deleted twin shares the position but must never surface.
    assert AHMED_DELETED not in html


def test_search_matches_joined_user_columns(office, search_setup):
    expected = {search_setup['ids'][AHMED_MAHMOUD]}
    for term, column in (
        ('ahmed.m', 'users.username'),
        ('ahmed@uni.edu', 'users.email'),
        ('AN-001', 'teachers.academic_number'),
    ):
        r = _ajax(office, _search_qs(term))
        html = r.get_data(as_text=True)
        assert _row_ids(html) == expected, f'{term} ({column}): {_names(html)}'


def test_search_matches_department_and_rank_lookup_tables(office, search_setup):
    html = _ajax(office, _search_qs(DEPT_MATH)).get_data(as_text=True)
    got = _row_ids(html)
    assert got == {
        search_setup['ids'][AHMED_MAHMOUD],
        search_setup['ids'][IBRAHIM_SAIF],
    }, _names(html)

    html = _ajax(office, _search_qs(RANK_ASSISTANT)).get_data(as_text=True)
    assert _row_ids(html) == {
        search_setup['ids'][AHMED_MAHMOUD],
        search_setup['ids'][AMNE_HADDAD],
    }, _names(html)


def test_two_tokens_may_match_different_columns(office, search_setup):
    """term 1 -> t.name, term 2 -> t.position (AND across columns)."""
    html = _ajax(
        office, _search_qs(f'{AHMED_FOLDED} \u0642\u0633\u0645')
    ).get_data(as_text=True)
    assert _row_ids(html) == {search_setup['ids'][AHMED_MAHMOUD]}, _names(html)


def test_over_long_search_input_is_truncated_not_rejected(office):
    """More than ``MAX_SEARCH_LENGTH`` characters must be cut, not 500.

    Truncation happens *before* folding/splitting, so a long query must return
    exactly what its own ``MAX_SEARCH_LENGTH``-char prefix returns.
    """
    long_term = f'{AHMED_FOLDED} ' + ('x' * (MAX_SEARCH_LENGTH + 200))
    assert len(long_term) > MAX_SEARCH_LENGTH
    r = _ajax(office, _search_qs(long_term))
    assert r.status_code == 200, 'search input past MAX_SEARCH_LENGTH crashed'
    got = _row_ids(r.get_data(as_text=True))
    assert got == _row_ids(
        _ajax(office, _search_qs(long_term[:MAX_SEARCH_LENGTH])).get_data(as_text=True)
    ), 'the tail beyond MAX_SEARCH_LENGTH was not discarded'


def test_malformed_department_id_does_not_crash_the_route(office):
    """``?department_id=`` is attacker-controlled and reaches ``int()``.

    ``build_teacher_search`` does ``int(effective_dept)`` with no guard, so a
    non-numeric value must not surface as a 500.
    """
    r = office.get('/teachers?department_id=abc')
    assert r.status_code == 200, f'malformed department_id returned {r.status_code}'


def test_department_filter_combines_with_search(office, search_setup):
    phys, math = search_setup['phys_id'], search_setup['math_id']

    html = _ajax(
        office, _search_qs(AHMED_FOLDED, department_id=phys)
    ).get_data(as_text=True)
    assert _row_ids(html) == set(), _names(html)
    assert 'empty-state' in html

    html = _ajax(
        office, _search_qs('', department_id=math)
    ).get_data(as_text=True)
    assert _row_ids(html) == {
        search_setup['ids'][AHMED_MAHMOUD],
        search_setup['ids'][IBRAHIM_SAIF],
    }, _names(html)


def test_hod_scoping_overrides_the_department_param(search_setup):
    """A HOD only ever sees their own department, whatever
    ``?department_id=`` says."""
    c = search_setup['client']
    math, phys = search_setup['math_id'], search_setup['phys_id']
    _login(c, 'hodm', 'head_of_department', hod_department_id=math)

    # Without the override ?department_id=phys would show physics rows.
    html = _ajax(c, _search_qs('', department_id=phys)).get_data(as_text=True)
    assert not any(MUHAMMAD_ALI in n for n in _names(html)), _names(html)
    assert any(IBRAHIM_SAIF in n for n in _names(html)), _names(html)

    # A physics-only match under the HOD scope is empty, even when the caller
    # passes the physics department explicitly.
    html = _ajax(
        c, _search_qs('\u0639\u0644\u064a', department_id=phys)
    ).get_data(as_text=True)
    assert MUHAMMAD_ALI not in html
    assert 'empty-state' in html
    assert _count_text(0) in html


def test_lone_percent_returns_every_row_by_design(office, search_setup):
    """DOCUMENTED BEHAVIOUR — do not "fix" this.

    ``search_terms`` drops punctuation-only tokens, so ``?search=%`` produces
    NO search clause at all and the route lists every row.  That is still
    wildcard-safe (it is not a ``LIKE '%%%'`` bomb), but it does not filter.
    """
    unfiltered = _row_ids(office.get('/teachers').get_data(as_text=True))
    assert len(unfiltered) == 4

    html = _ajax(office, _search_qs('%')).get_data(as_text=True)
    assert _row_ids(html) == unfiltered
    assert _count_text(4) in html


def test_underscore_in_search_is_literal(office):
    html = _ajax(office, _search_qs('a_b')).get_data(as_text=True)
    assert _row_ids(html) == set(), _names(html)
    assert _count_text(0) in html


def test_ajax_fragment_contract(office):
    r = _ajax(office, _search_qs(AHMED_FOLDED))
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert '<html' not in html, 'fragment response leaked the full layout'
    assert 'search-results-count' in html
    assert 'data-count-value' in html
    assert _count_text(1) in html


def test_ajax_fragment_highlights_the_folded_match(office):
    html = _ajax(office, _search_qs(AHMED_FOLDED)).get_data(as_text=True)
    # The stored name carries أ (U+0623); the search term does not. The
    # highlight must still land on it.
    assert '<mark class="search-highlight">' in html
    assert re.search(
        r'<mark class="search-highlight">' + re.escape(AHMED_HAMZA) + r'</mark>',
        html,
    ), 'the matched Arabic name is not wrapped in a <mark>'


def test_highlight_escapes_html_in_the_cell():
    """``highlight_search_terms`` is rendered with ``|safe``."""
    from services.search import highlight_search_terms
    out = highlight_search_terms('<script>alert(1)</script>', 'alert')
    assert '<script>' not in out
    assert '&lt;script&gt;' in out


def test_full_page_preserves_the_selected_department(office, search_setup):
    phys = search_setup['phys_id']
    html = office.get(f'/teachers?department_id={phys}').get_data(as_text=True)
    assert f'<option value="{phys}" selected>' in html


def test_plain_list_page_selects_the_all_departments_option(office, search_setup):
    html = office.get('/teachers').get_data(as_text=True)
    assert '<option value="">\u062c\u0645\u064a\u0639 \u0627\u0644\u0623\u0642\u0633\u0627\u0645</option>' in html
    for dept_id in (search_setup['math_id'], search_setup['phys_id']):
        assert f'<option value="{dept_id}" selected>' not in html


def test_bulk_ids_matches_the_list_page(office, search_setup):
    html = _ajax(office, _search_qs(AHMED_FOLDED)).get_data(as_text=True)
    r = office.get(f'/teachers/api/bulk-ids{_search_qs(AHMED_FOLDED)}')
    assert r.status_code == 200
    payload = r.get_json()
    assert set(payload['ids']) == _row_ids(html)
    assert payload['total'] == len(_row_ids(html)) == 1


def test_bulk_ids_excludes_the_soft_deleted_teacher(office, search_setup):
    r = office.get(f'/teachers/api/bulk-ids{_search_qs(AHMED_FOLDED)}')
    assert r.status_code == 200
    assert search_setup['ids'][AHMED_DELETED] not in r.get_json()['ids']


def test_teacher_pool_route_uses_the_folded_search(db_fx, app_fx):
    """Reuses tests/test_teacher_pool.py's fixture + seed rows.

    Targets the *second* department, because pool membership excludes teachers
    who already belong to the target department — the "computer science"
    (math-analogue) department in that fixture already holds أحمد علي, so
    searching for him there would (correctly) return nothing.
    """
    FIXTURE_DB_PATH[0] = str(db_fx)
    client = app_fx.test_client()
    _login(client, 'admin', 'faculty_affairs')

    conn = connect(str(db_fx))
    dept2 = conn.execute(
        "SELECT id FROM departments WHERE name=?",
        ('\u0642\u0633\u0645 \u0627\u0644\u0627\u062a\u0635\u0627\u0644\u0627\u062a',),
    ).fetchone()['id']
    dept1 = conn.execute(
        "SELECT id FROM departments WHERE name=?",
        ('\u0642\u0633\u0645 \u0627\u0644\u062d\u0627\u0633\u0648\u0628',),
    ).fetchone()['id']
    conn.close()

    expected_name = AHMED_HAMZA + ' \u0639\u0644\u064a'   # أحمد علي

    r = client.get(
        f'/teachers/api/teacher-pool?dept_id={dept2}&search=' + quote(AHMED_FOLDED)
    )
    assert r.status_code == 200
    rows = r.get_json()
    assert [row['name'] for row in rows] == [expected_name], rows

    # The hamza form and the folded form resolve to the same single row.
    r2 = client.get(
        f'/teachers/api/teacher-pool?dept_id={dept2}&search=' + quote(AHMED_HAMZA)
    )
    assert r2.get_json() == rows

    # Punctuation-only input drops the clause (same rule as the list page).
    r3 = client.get(f'/teachers/api/teacher-pool?dept_id={dept2}&search=%25')
    assert len(r3.get_json()) == 3

    # An existing member of the target department is excluded regardless.
    r4 = client.get(
        f'/teachers/api/teacher-pool?dept_id={dept1}&search=' + quote(AHMED_FOLDED)
    )
    assert r4.get_json() == []


# ═════════════════════════════════════════════════════════════════════════════
# D. Regression guards
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    'builder, term, expected_columns',
    [
        ('build_course_search', 'phy', 4),
        ('build_room_search', 'lab', 4),
        ('build_department_search', '\u0642', 1),
        ('build_user_search', 'ah', 3),
    ],
)
def test_legacy_search_builders_are_untouched(builder, term, expected_columns):
    """Only the teachers page opted into ``smart_search``.

    Every other builder must keep the legacy ``else`` branch: a single raw
    ``LIKE`` per column with the *unfolded* term and no UDF.
    """
    fn = {
        'build_course_search': build_course_search,
        'build_room_search': build_room_search,
        'build_department_search': build_department_search,
        'build_user_search': build_user_search,
    }[builder]
    query, params = fn(term)[0], fn(term)[1]
    assert 'normalize_search(' not in query
    assert params == [f'%{term}%'] * expected_columns
    assert query.count('?') == len(params)


def test_paginate_total_matches_row_count_for_a_filtered_search(search_setup):
    """``paginate`` splits on 'ORDER BY' to build its COUNT — the 1:1 joins the
    teacher query added must not inflate it, nor duplicate rows."""
    app = search_setup['app']
    query, params, _dept = build_teacher_search(AHMED_FOLDED, '', None, 1)
    with app.test_request_context():
        rows, total, _page, _per_page = paginate(query, params, 1)
    assert total == len(rows) == 1


def test_paginate_total_matches_row_count_for_a_filtered_search_with_dept(search_setup):
    """Same guard, but with a department filter (EXISTS subquery + 8 joins)."""
    app = search_setup['app']
    query, params, _dept = build_teacher_search(
        '', str(search_setup['math_id']), None, 1
    )
    with app.test_request_context():
        rows, total, _page, _per_page = paginate(query, params, 1)
    assert total == len(rows) == 2


def test_teacher_with_null_columns_renders_without_none(office, search_setup):
    """محمد علي has NULL email / academic_number / phone.

    Widening the search columns must not start rendering their raw values.
    """
    html = office.get(
        '/teachers' + _search_qs('\u0639\u0644\u064a')
    ).get_data(as_text=True)
    assert _row_ids(html) == {search_setup['ids'][MUHAMMAD_ALI]}, _names(html)
    assert MUHAMMAD_ALI in html, 'fixture row is missing — the check is vacuous'
    assert 'None' not in html
    # The em-dash placeholder the template falls back to is still there.
    assert '\u2014' in html
