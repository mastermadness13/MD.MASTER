"""Pure-logic tests for internals a URL sweep cannot reach.

Covers the rate limiter, HTML/XML sanitization, the exception hierarchy,
formatting and Arabic-text utilities, safe back-redirects, HOD resolution,
short-lived recovery codes, the timetable semester rule and the translation
fallback.  Direct calls only, plus the harness ``db_path`` / ``raw_db``
fixtures where a real database is needed.
"""

from __future__ import annotations

import json
import io
import sqlite3
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

from core import rate_limiter as rl
from core.constants.ui import (
    ARABIC_MONTHS,
    DAY_ORDER,
    SEMESTER_SEASON_NEXT,
    SEMESTER_SEASON_ORDER,
    WEEK_DAYS,
)
from core.exceptions import (
    AppError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    DatabaseError,
    ForbiddenError,
    NotFoundError,
    ProtectedAccountError,
    RateLimitError,
    UnauthorizedError,
    ValidationError,
)
from security.sanitize import (
    SAFE_BASIC_TAGS,
    clean_html,
    iter_parse_xml_safe,
    parse_xml_safe,
    sanitize_string,
)
from services import hod_resolution, temp_access_code, timetable_scope, translation_service
from utils.format import (
    academic_title_prefix,
    duration_label,
    format_time12,
    semester_code_next,
    semester_display_name,
    semester_label,
    submission_status_color,
    submission_status_label,
    teacher_display_name,
    teacher_label,
    teaching_semester_label,
)
from utils.redirects import redirect_back
from utils.text import normalize_academic_number, normalize_arabic_name

from tests.harness import raw_db, run_sql, scalar  # noqa: F401  (re-exported by conftest)

# ─────────────────────────────────────────────
# Rate limiter
# ─────────────────────────────────────────────


def _clock(monkeypatch, start=1000.0):
    state = {'t': start}
    monkeypatch.setattr('core.rate_limiter.time.time', lambda: state['t'])
    return state


class TestRateLimiter:
    def test_allows_until_limit_then_rejects(self, monkeypatch):
        clock = _clock(monkeypatch)
        limiter = rl.RateLimiter(max_requests=3, window_seconds=60)
        assert limiter.remaining('k') == 3
        for _ in range(3):
            assert not limiter.is_limited('k')
            limiter.record('k')
        assert limiter.is_limited('k')
        assert limiter.remaining('k') == 0
        assert clock['t'] == 1000.0

    def test_window_expiry_resets_budget(self, monkeypatch):
        clock = _clock(monkeypatch)
        limiter = rl.RateLimiter(max_requests=1, window_seconds=10, storage=rl.InMemoryStorage())
        limiter.record('k')
        assert limiter.is_limited('k')
        clock['t'] = 1010.01
        assert not limiter.is_limited('k')
        assert limiter.remaining('k') == 1

    def test_window_boundary_is_exclusive(self, monkeypatch):
        clock = _clock(monkeypatch)
        limiter = rl.RateLimiter(max_requests=1, window_seconds=10, storage=rl.InMemoryStorage())
        limiter.record('k')
        clock['t'] = 1009.99
        assert limiter.is_limited('k')
        clock['t'] = 1010.0
        assert not limiter.is_limited('k')

    def test_keys_are_isolated(self, monkeypatch):
        _clock(monkeypatch)
        limiter = rl.RateLimiter(max_requests=1, window_seconds=60, storage=rl.InMemoryStorage())
        limiter.record('a')
        assert limiter.is_limited('a')
        assert not limiter.is_limited('b')
        assert limiter.remaining('b') == 1

    def test_reset_clears_one_key(self, monkeypatch):
        _clock(monkeypatch)
        limiter = rl.RateLimiter(max_requests=1, window_seconds=60, storage=rl.InMemoryStorage())
        limiter.record('a')
        limiter.record('b')
        limiter.reset('a')
        assert not limiter.is_limited('a')
        assert limiter.is_limited('b')

    def test_reset_all_clears_everything(self, monkeypatch):
        _clock(monkeypatch)
        limiter = rl.RateLimiter(max_requests=1, window_seconds=60, storage=rl.InMemoryStorage())
        limiter.record('a')
        limiter.record('b')
        limiter.reset_all()
        assert not limiter.is_limited('a')
        assert not limiter.is_limited('b')

    def test_zero_max_always_limited(self, monkeypatch):
        _clock(monkeypatch)
        limiter = rl.RateLimiter(max_requests=0, window_seconds=60, storage=rl.InMemoryStorage())
        assert limiter.is_limited('anything')


class TestInMemoryStorage:
    def test_count_defaults_to_zero(self):
        assert rl.InMemoryStorage().count('missing') == 0

    def test_record_and_trim(self):
        storage = rl.InMemoryStorage()
        storage.record('k', 1.0)
        storage.record('k', 2.0)
        assert storage.count('k') == 2
        storage.trim('k', 1.5)
        assert storage.count('k') == 1

    def test_reset(self):
        storage = rl.InMemoryStorage()
        storage.record('k', 1.0)
        storage.reset('k')
        assert storage._hits.get('k', []) == []


class TestSQLiteStorage:
    def test_roundtrip(self, tmp_path):
        storage = rl.SQLiteStorage(str(tmp_path / 'rl.sqlite'))
        assert storage.count('k') == 0
        storage.record('k', 1.0)
        storage.record('k', 2.0)
        assert storage.count('k') == 2
        storage.trim('k', 1.5)
        assert storage.count('k') == 1
        storage.reset('k')
        assert storage.count('k') == 0

    def test_reset_all(self, tmp_path):
        storage = rl.SQLiteStorage(str(tmp_path / 'rl.sqlite'))
        storage.record('a', 1.0)
        storage.record('b', 1.0)
        storage.reset_all()
        assert storage.count('a') == 0
        assert storage.count('b') == 0

    def test_two_instances_share_the_file(self, tmp_path):
        path = str(tmp_path / 'rl.sqlite')
        first = rl.SQLiteStorage(path)
        second = rl.SQLiteStorage(path)
        first.record('k', 1.0)
        assert second.count('k') == 1

    def test_limiter_integration(self, tmp_path, monkeypatch):
        clock = _clock(monkeypatch)
        limiter = rl.RateLimiter(
            max_requests=2, window_seconds=10,
            storage=rl.SQLiteStorage(str(tmp_path / 'rl.sqlite')),
        )
        limiter.record('k')
        limiter.record('k')
        assert limiter.is_limited('k')
        clock['t'] = 1010.01
        assert not limiter.is_limited('k')


class TestDefaultStorage:
    def test_memory_is_default(self, monkeypatch):
        monkeypatch.delenv('RATE_LIMITER_BACKEND', raising=False)
        assert isinstance(rl.default_storage(), rl.InMemoryStorage)

    def test_sqlite_selected_from_env(self, monkeypatch, tmp_path):
        path = str(tmp_path / 'shared.sqlite')
        monkeypatch.setenv('RATE_LIMITER_BACKEND', 'sqlite')
        monkeypatch.setenv('RATE_LIMITER_SQLITE_PATH', path)
        storage = rl.default_storage()
        assert isinstance(storage, rl.SQLiteStorage)
        assert storage.path == path

    def test_file_alias_maps_to_sqlite(self, monkeypatch, tmp_path):
        monkeypatch.setenv('RATE_LIMITER_BACKEND', 'file')
        monkeypatch.setenv('RATE_LIMITER_SQLITE_PATH', str(tmp_path / 'f.sqlite'))
        assert isinstance(rl.default_storage(), rl.SQLiteStorage)


# ─────────────────────────────────────────────
# Sanitization
# ─────────────────────────────────────────────

class TestSanitizeString:
    def test_none_becomes_empty(self):
        assert sanitize_string(None) == ''

    def test_strips_markup_but_keeps_text(self):
        assert sanitize_string('<script>alert(1)</script>') == 'alert(1)'

    def test_leading_trailing_space_trimmed(self):
        assert sanitize_string('  hi  there  ') == 'hi  there'

    def test_plain_text_passes_through(self):
        assert sanitize_string('أحمد محمد') == 'أحمد محمد'


class TestCleanHtml:
    def test_none_becomes_empty(self):
        assert clean_html(None) == ''

    def test_default_strips_every_tag(self):
        assert clean_html('<b>Hi</b>') == 'Hi'

    def test_plain_text_passes_through(self):
        assert clean_html('just text') == 'just text'

    def test_opt_in_rich_text(self):
        out = clean_html('<b>Hi</b> <i>x</i>', tags=SAFE_BASIC_TAGS)
        assert '<b>Hi</b>' in out
        assert '<i>x</i>' in out

    def test_inline_handlers_dropped(self):
        out = clean_html('<p onclick="steal()">t</p>', tags={'p'})
        assert out.startswith('<p')
        assert 'onclick' not in out
        assert 'steal' not in out

    def test_javascript_protocol_dropped(self):
        out = clean_html('<a href="javascript:alert(1)">x</a>', tags={'a'})
        assert 'javascript' not in out
        assert 'href' not in out


class TestParseXmlSafe:
    def test_valid_document(self):
        root = parse_xml_safe('<root><a>1</a></root>')
        assert root.find('a').text == '1'

    def test_rejects_doctype(self):
        with pytest.raises(ValueError):
            parse_xml_safe('<!DOCTYPE foo><foo/>')

    def test_rejects_internal_entities(self):
        payload = '<!DOCTYPE r [<!ENTITY e "x">]><r>&e;</r>'
        with pytest.raises(ValueError):
            parse_xml_safe(payload)

    def test_rejects_external_entity_xxe(self):
        payload = '<!DOCTYPE r [<!ENTITY e SYSTEM "file:///etc/passwd">]><r>&e;</r>'
        with pytest.raises(ValueError):
            parse_xml_safe(payload)

    def test_iterparse_valid(self):
        source = io.StringIO('<root><a/></root>')
        events = sum(1 for _ in iter_parse_xml_safe(source))
        assert events >= 1

    def test_iterparse_rejects_forbidden(self):
        with pytest.raises(ValueError):
            list(iter_parse_xml_safe(io.StringIO('<!DOCTYPE x><x/>')))


# ─────────────────────────────────────────────
# Exception hierarchy
# ─────────────────────────────────────────────

_EXCEPTION_CASES = [
    (NotFoundError, 404),
    (AuthenticationError, 401),
    (AuthorizationError, 403),
    (ValidationError, 422),
    (ConflictError, 409),
    (ProtectedAccountError, 403),
    (RateLimitError, 429),
    (DatabaseError, 500),
    (AppError, 500),
]
_EXCEPTION_IDS = [cls.__name__ for cls, _ in _EXCEPTION_CASES]


class TestExceptions:
    @pytest.mark.parametrize('cls,code', _EXCEPTION_CASES, ids=_EXCEPTION_IDS)
    def test_status_codes(self, cls, code):
        assert cls().status_code == code
        assert isinstance(cls(), AppError)

    @pytest.mark.parametrize('cls,code', _EXCEPTION_CASES, ids=_EXCEPTION_IDS)
    def test_defaults_are_truthy(self, cls, code):
        err = cls()
        assert err.message
        assert err.detail

    def test_custom_message_and_detail(self):
        err = NotFoundError('مفقود', 'gone')
        assert err.message == 'مفقود'
        assert err.detail == 'gone'

    def test_str_is_message(self):
        assert str(NotFoundError('مفقود')) == 'مفقود'

    def test_validation_errors_default_empty(self):
        assert ValidationError().errors == {}

    def test_validation_errors_override(self):
        err = ValidationError(errors={'name': ['required']})
        assert err.errors == {'name': ['required']}

    def test_aliases(self):
        assert UnauthorizedError is AuthenticationError
        assert ForbiddenError is AuthorizationError


# ─────────────────────────────────────────────
# Formatting helpers
# ─────────────────────────────────────────────

class TestSemesterLabels:
    def test_known_semester(self):
        assert semester_label(1) == 'الفصل الأول'

    def test_fallback_for_unknown(self):
        assert semester_label(9) == 'الفصل 9'

    def test_empty_value(self):
        assert semester_label(None) == ''
        assert semester_label(0) == '' or semester_label('') == ''

    def test_teaching_semester_one_and_two(self):
        assert teaching_semester_label(1) == 'الفصل الخريفي'
        assert teaching_semester_label(2) == 'الفصل الربيعي'

    def test_teaching_semester_mapped_number(self):
        assert teaching_semester_label(3) == 'الفصل الثالث'

    def test_teaching_semester_fallback(self):
        assert teaching_semester_label(9) == 'الفصل 9'

    def test_teaching_semester_empty(self):
        assert teaching_semester_label(None) == '—'


class TestSemesterDisplayName:
    def test_fall_code(self):
        assert semester_display_name('fall_2026') == 'خريف 2026'

    def test_spring_code(self):
        assert semester_display_name('spring_2025') == 'ربيع 2025'

    def test_database_name_overrides(self):
        assert semester_display_name('fall_2026', name_ar='الفصل الخاص') == 'الفصل الخاص'

    def test_unknown_season_passes_through(self):
        assert semester_display_name('x_2026') == 'x 2026'

    def test_malformed_code_returned_unchanged(self):
        assert semester_display_name('not-a-code') == 'not-a-code'

    def test_empty_code(self):
        assert semester_display_name('') == ''
        assert semester_display_name(None) == ''


class TestSemesterCodeNext:
    def test_fall_to_spring_next_year(self):
        assert semester_code_next('fall_2026') == 'spring_2027'

    def test_spring_to_fall_same_year(self):
        assert semester_code_next('spring_2025') == 'fall_2025'

    def test_unknown_season_falls_back_to_fall(self):
        assert semester_code_next('x_2026') == 'fall_2026'

    def test_empty(self):
        assert semester_code_next('') == ''
        assert semester_code_next(None) == ''

    def test_malformed_returned_unchanged(self):
        assert semester_code_next('garbage') == 'garbage'


class TestTeacherNameFormatting:
    def test_single_title_prefix(self):
        assert teacher_label('د. أحمد') == 'أحمد'
        assert teacher_label('أ. خالد') == 'خالد'

    def test_professor_prefix_strips_first_part(self):
        assert teacher_label('أ.د. سامي') == 'د. سامي'

    def test_no_prefix_unchanged(self):
        assert teacher_label('علي حسن') == 'علي حسن'

    def test_empty_is_dash(self):
        assert teacher_label('') == '—'
        assert teacher_label(None) == '—'

    def test_whitespace_trimmed(self):
        assert teacher_label('  د. أحمد  ') == 'أحمد'

    def test_rank_title_prefix(self):
        assert academic_title_prefix(rank_name='أستاذ') == 'أ.د.'
        assert academic_title_prefix(rank_name='أستاذ مساعد') == 'د.'
        assert academic_title_prefix(rank_name='معيد') == 'أ.'

    def test_qualification_title_prefix(self):
        assert academic_title_prefix(rank_name=None, qual_name='دكتوراه') == 'د.'
        assert academic_title_prefix(rank_name=None, qual_name='ماجستير إدارة') == 'أ.'
        assert academic_title_prefix(rank_name=None, qual_name='Bachelor') == 'أ.'

    def test_no_source_matches(self):
        assert academic_title_prefix(rank_name=None, qual_name=None) == ''
        assert academic_title_prefix(rank_name='لا شيء', qual_name='لا شيء') == ''

    def test_display_name_prefers_rank_title(self):
        assert teacher_display_name('أحمد محمد', rank_name='أستاذ') == 'أ.د. أحمد محمد'

    def test_display_name_no_duplicate_prefix(self):
        assert teacher_display_name('د. أحمد محمد', rank_name='أستاذ مساعد') == 'د. أحمد محمد'

    def test_display_name_without_metadata(self):
        assert teacher_display_name('أحمد محمد') == 'أحمد محمد'

    def test_display_name_title_only_is_dash(self):
        assert teacher_display_name('د.') == '—'


class TestDurationLabel:
    def test_one_hour(self):
        assert duration_label('09:00', '10:00') == 'ساعة'

    def test_two_hours(self):
        assert duration_label('09:00', '11:00') == 'ساعتان'

    def test_three_hours(self):
        assert duration_label('09:00', '12:00') == '3 ساعات'

    def test_eleven_hours(self):
        assert duration_label('09:00', '20:00') == '11 ساعة'

    def test_twelve_hours(self):
        assert duration_label('09:00', '21:00') == '12 ساعة'

    def test_partial_hour_rounds_to_hour(self):
        assert duration_label('09:00', '09:30') == 'ساعة'
        assert duration_label('10:30', '13:45') == '3 ساعات'

    def test_missing_or_malformed(self):
        assert duration_label('', '10:00') == ''
        assert duration_label('09:00', '') == ''
        assert duration_label('aa:bb', '10:00') == ''
        assert duration_label('09:00', '08:00') == ''

    def test_none_inputs(self):
        assert duration_label(None, '10:00') == ''
        assert duration_label('09:00', None) == ''


class TestFormatTime12:
    def test_morning_leading_zero(self):
        assert format_time12('09:00') == '9:00 ص'

    def test_midnight(self):
        assert format_time12('00:05') == '12:05 ص'

    def test_noon_is_pm(self):
        assert format_time12('12:00') == '12:00 م'
        assert format_time12('12:01') == '12:01 م'

    def test_afternoon(self):
        assert format_time12('15:01') == '3:01 م'

    def test_empty_and_malformed_pass_through(self):
        assert format_time12('') == ''
        assert format_time12(None) == ''
        assert format_time12('9:00') == '9:00 ص'
        assert format_time12('x:y') == 'x:y'


class TestSubmissionStatusLabels:
    def test_known_statuses(self):
        assert submission_status_label('draft') == 'مسودة'
        assert submission_status_label('published') == 'منشور'
        assert submission_status_label('approved') == 'منشور'
        assert submission_status_label('rejected') == 'مرفوض'

    def test_unknown_and_empty(self):
        assert submission_status_label('nope') == ''
        assert submission_status_label(None) == ''
        assert submission_status_label('') == ''

    def test_colors_map_to_tailwind_classes(self):
        assert submission_status_color('rejected').startswith('bg-red')
        assert submission_status_color('approved').startswith('bg-green')

    def test_unknown_color_defaults(self):
        assert submission_status_color('nope') == 'bg-surface-dim text-on-surface-variant'
        assert submission_status_color(None) == 'bg-surface-dim text-on-surface-variant'


# ─────────────────────────────────────────────
# Arabic text normalization
# ─────────────────────────────────────────────

class TestNormalizeArabicName:
    def test_alef_variants_unify(self):
        assert normalize_arabic_name('أحمد') == 'احمد'
        assert normalize_arabic_name('إبراهيم') == 'ابراهيم'
        assert normalize_arabic_name('آدم') == 'ادم'

    def test_waw_and_yeh_hamza(self):
        assert normalize_arabic_name('مؤمن') == 'مومن'
        assert normalize_arabic_name('مبادئ') == 'مبادي'
        assert normalize_arabic_name('مصطفى') == 'مصطفي'

    def test_diacritics_stripped(self):
        assert normalize_arabic_name('أَحْمَد') == 'احمد'

    def test_whitespace_collapsed(self):
        assert normalize_arabic_name('  أحمد   محمد  ') == 'احمد محمد'

    def test_empty_value(self):
        assert normalize_arabic_name(None) == ''
        assert normalize_arabic_name('') == ''
        assert normalize_arabic_name('   ') == ''


class TestNormalizeAcademicNumber:
    @pytest.mark.parametrize('value', [None, '', '0', 'غير محدد', '—', '-', 'N/A', 'null', '  '])
    def test_sentinels_become_none(self, value):
        assert normalize_academic_number(value) is None

    def test_keeps_real_numbers(self):
        assert normalize_academic_number('12345') == '12345'
        assert normalize_academic_number(' 12345 ') == '12345'
        assert normalize_academic_number('AB-12') == 'AB-12'


# ─────────────────────────────────────────────
# Safe back-redirect
# ─────────────────────────────────────────────

class TestRedirectBack:
    def test_same_origin_referrer_is_kept(self, app_fx):
        with app_fx.test_request_context('/', headers={'Referer': 'http://localhost/foo'}):
            resp = redirect_back()
            assert resp.status_code == 302
            assert resp.location == 'http://localhost/foo'

    def test_foreign_referrer_is_rejected(self, app_fx):
        with app_fx.test_request_context('/', headers={'Referer': 'https://evil.example/phish'}):
            resp = redirect_back()
            assert resp.status_code == 302
            assert not resp.location.startswith('https://evil')

    def test_missing_referrer_falls_back(self, app_fx):
        with app_fx.test_request_context('/'):
            resp = redirect_back()
            assert resp.status_code == 302
            assert resp.location.startswith('/')


# ─────────────────────────────────────────────
# HOD resolution
# ─────────────────────────────────────────────

def _make_departments(db_path, specs):
    """Insert departments and return ``{name: id}``."""
    ids = {}
    for name, semesters in specs:
        run_sql(db_path, 'INSERT INTO departments (name, semesters) VALUES (?, ?)', (name, semesters))
        ids[name] = scalar(db_path, 'SELECT id FROM departments WHERE name = ?', (name,))
    return ids


def _make_user(db_path, username, role='head_of_department', label='رئيس القسم'):
    run_sql(
        db_path,
        'INSERT INTO users (username, password, role, label) VALUES (?, ?, ?, ?)',
        (username, 'x', role, label),
    )
    return scalar(db_path, 'SELECT id FROM users WHERE username = ?', (username,))


def _make_teacher(db_path, name, dept_id, user_id=None, deleted_at=None):
    if deleted_at is None:
        run_sql(
            db_path,
            'INSERT INTO teachers (name, hod_department_id, user_id) VALUES (?, ?, ?)',
            (name, dept_id, user_id),
        )
    else:
        run_sql(
            db_path,
            'INSERT INTO teachers (name, hod_department_id, user_id, deleted_at) '
            'VALUES (?, ?, ?, ?)',
            (name, dept_id, user_id, deleted_at),
        )
    return scalar(db_path, 'SELECT id FROM teachers WHERE name = ? ORDER BY id DESC LIMIT 1', (name,))


def _rows(db):
    if getattr(db, 'row_factory', None) is not sqlite3.Row:
        db.row_factory = sqlite3.Row
    return db


class TestGetCurrentHod:
    def test_returns_none_without_department(self, raw_db):
        assert hod_resolution.get_current_hod(raw_db, None) is None
        assert hod_resolution.get_current_hod(raw_db, 0) is None
        assert hod_resolution.get_current_hod(raw_db, 9999) is None

    def test_teacher_is_the_hod(self, raw_db, db_path):
        depts = _make_departments(db_path, [('قسم الشؤون', 2)])
        dept_id = depts['قسم الشؤون']
        user_id = _make_user(db_path, 'hodacct1')
        _make_teacher(db_path, 'د. رئيس الأستاذ', dept_id, user_id=user_id)
        hod = hod_resolution.get_current_hod(_rows(raw_db), dept_id)
        assert hod is not None
        assert hod['source'] == 'teacher'
        assert hod['teacher_id'] is not None
        assert hod['name'] == 'د. رئيس الأستاذ'

    def test_deleted_teacher_is_ignored(self, raw_db, db_path):
        depts = _make_departments(db_path, [('قسم المحاسبة', 2)])
        dept_id = depts['قسم المحاسبة']
        user_id = _make_user(db_path, 'hodacct2')
        run_sql(
            db_path, 'UPDATE users SET department_id = ? WHERE id = ?', (dept_id, user_id),
        )
        _make_teacher(db_path, 'متقاعد', dept_id, user_id=user_id, deleted_at='2024-01-01')
        hod = hod_resolution.get_current_hod(_rows(raw_db), dept_id)
        assert hod is not None
        assert hod['source'] == 'account'
        assert hod['name'] == 'رئيس القسم'

    def test_account_fallback_uses_label(self, raw_db, db_path):
        depts = _make_departments(db_path, [('قسم اللغة', 2)])
        dept_id = depts['قسم اللغة']
        user_id = _make_user(db_path, 'hodacct3', label='د. رئيس اللغة')
        run_sql(
            db_path, 'UPDATE users SET department_id = ? WHERE id = ?', (dept_id, user_id),
        )
        hod = hod_resolution.get_current_hod(_rows(raw_db), dept_id)
        assert hod is not None
        assert hod['source'] == 'account'
        assert hod['name'] == 'د. رئيس اللغة'


class TestDepartmentHodMap:
    def test_builds_full_map_with_teacher_priority(self, raw_db, db_path):
        depts = _make_departments(
            db_path, [('قسم أ', 2), ('قسم ب', 2), ('قسم ج', 2)],
        )
        a_id, b_id, c_id = depts['قسم أ'], depts['قسم ب'], depts['قسم ج']

        hod_a = _make_user(db_path, 'hodmap-a')
        _make_teacher(db_path, 'رئيس أ', a_id, user_id=hod_a)

        _make_user(db_path, 'hodmap-b')
        run_sql(db_path, 'UPDATE users SET department_id = ? WHERE username = ?', (b_id, 'hodmap-b'))

        _make_user(db_path, 'hodmap-c')
        run_sql(db_path, 'UPDATE users SET department_id = ? WHERE username = ?', (c_id, 'hodmap-c'))
        _make_teacher(db_path, 'رئيس ج القديم', c_id, user_id=None, deleted_at='2024-01-01')

        result = hod_resolution.department_hod_map(_rows(raw_db), [a_id, b_id, c_id])
        assert set(result) == {a_id, b_id, c_id}
        assert result[a_id]['source'] == 'teacher'
        assert result[a_id]['name'] == 'رئيس أ'
        assert result[b_id]['source'] == 'account'
        assert result[c_id]['source'] == 'account'

    def test_filters_to_requested_departments(self, raw_db, db_path):
        depts = _make_departments(db_path, [('قسم س', 2), ('قسم ص', 2)])
        s_id = depts['قسم س']
        user = _make_user(db_path, 'hod-filter')
        run_sql(db_path, 'UPDATE users SET department_id = ? WHERE id = ?', (s_id, user))
        result = hod_resolution.department_hod_map(_rows(raw_db), [9999])
        assert result == {}

    def test_empty_and_full_maps(self, raw_db, db_path):
        depts = _make_departments(db_path, [('قسم واحد', 2)])
        dept_id = depts['قسم واحد']
        user = _make_user(db_path, 'hod-empty')
        run_sql(db_path, 'UPDATE users SET department_id = ? WHERE id = ?', (dept_id, user))
        result = hod_resolution.department_hod_map(_rows(raw_db))
        assert dept_id in result


# ─────────────────────────────────────────────
# Recovery codes
# ─────────────────────────────────────────────

def _fresh_user(db_path, username='recover_user'):
    run_sql(
        db_path,
        'INSERT INTO users (username, password, role) VALUES (?, ?, ?)',
        (username, 'x', 'teacher'),
    )
    return scalar(db_path, 'SELECT id FROM users WHERE username = ?', (username,))


def _user_row(db_path, user_id):
    from tests.harness import read_row
    return read_row(db_path, 'SELECT * FROM users WHERE id = ?', (user_id,))


class TestValidateUsername:
    @pytest.mark.parametrize('name', ['ahmed', 'A1_b', 'zzz', 'AssistantHead123'])
    def test_valid_usernames(self, name):
        assert temp_access_code.validate_username(name) is None

    @pytest.mark.parametrize('name', ['', '1abc', 'a', 'ab', 'a b', 'a-b', 'أحمد'])
    def test_invalid_usernames_rejected(self, name):
        assert temp_access_code.validate_username(name) is not None


class TestRecoveryCodeFlow:
    def test_none_issued_without_code(self, raw_db, db_path):
        user_id = _fresh_user(db_path)
        result = temp_access_code.verify_recovery_code(raw_db, _user_row(db_path, user_id), '000000')
        assert result is temp_access_code.RecoveryCodeResult.NONE_ISSUED

    def test_generated_code_is_six_digits(self, raw_db, db_path):
        user_id = _fresh_user(db_path)
        for _ in range(5):
            code = temp_access_code.generate_recovery_code()
            assert code.isdigit() and len(code) == 6

    def test_issue_does_not_touch_password_or_session(self, raw_db, db_path):
        user_id = _fresh_user(db_path)
        before = _user_row(db_path, user_id)
        code = temp_access_code.issue_recovery_code(raw_db, user_id=user_id, issued_by=user_id)
        after = _user_row(db_path, user_id)
        assert len(code) == 6
        assert after['password'] == before['password']
        assert after['session_version'] == before['session_version']
        assert after['recovery_code_hash'] is not None
        assert after['recovery_code_attempts'] == 0
        assert after['recovery_code_issued_by'] == user_id

    def test_valid_code_roundtrip(self, raw_db, db_path):
        user_id = _fresh_user(db_path)
        code = temp_access_code.issue_recovery_code(raw_db, user_id=user_id, issued_by=user_id)
        result = temp_access_code.verify_recovery_code(raw_db, _user_row(db_path, user_id), code)
        assert result is temp_access_code.RecoveryCodeResult.VALID
        assert _user_row(db_path, user_id)['recovery_code_hash'] is None

    def test_wrong_code_increments_attempts_then_locks(self, raw_db, db_path):
        user_id = _fresh_user(db_path)
        code = temp_access_code.issue_recovery_code(raw_db, user_id=user_id, issued_by=user_id)
        assert code.isdigit()
        for _ in range(temp_access_code.MAX_ATTEMPTS - 1):
            result = temp_access_code.verify_recovery_code(raw_db, _user_row(db_path, user_id), '000000')
            assert result is temp_access_code.RecoveryCodeResult.INVALID
        result = temp_access_code.verify_recovery_code(raw_db, _user_row(db_path, user_id), '000000')
        assert result is temp_access_code.RecoveryCodeResult.LOCKED
        assert _user_row(db_path, user_id)['recovery_code_hash'] is None

    def test_expired_code_is_cleared(self, raw_db, db_path):
        user_id = _fresh_user(db_path)
        temp_access_code.issue_recovery_code(raw_db, user_id=user_id, issued_by=user_id)
        past = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        run_sql(db_path, 'UPDATE users SET recovery_code_expires_at = ? WHERE id = ?', (past, user_id))
        result = temp_access_code.verify_recovery_code(raw_db, _user_row(db_path, user_id), '000000')
        assert result is temp_access_code.RecoveryCodeResult.EXPIRED
        assert _user_row(db_path, user_id)['recovery_code_hash'] is None


# ─────────────────────────────────────────────
# Timetable semester scope
# ─────────────────────────────────────────────

class TestIsGeneralDept:
    def test_matches_by_name(self):
        assert timetable_scope.is_general_dept({'name': 'القسم العام', 'semesters': 8})

    def test_matches_by_single_semester(self):
        assert timetable_scope.is_general_dept({'name': 'قسم خاص', 'semesters': 1})

    def test_name_wins_over_semesters(self):
        assert timetable_scope.is_general_dept({'name': 'القسم العام', 'semesters': 8}) is True

    def test_normal_department_is_not_general(self):
        assert not timetable_scope.is_general_dept({'name': 'قسم الحاسوب', 'semesters': 5})

    def test_missing_name_is_not_general(self):
        assert not timetable_scope.is_general_dept({'semesters': 5})

    def test_blank_and_unparsable(self):
        assert not timetable_scope.is_general_dept(None)
        assert not timetable_scope.is_general_dept({})
        assert not timetable_scope.is_general_dept({'name': 'قسم', 'semesters': 'x'})


class TestAllowedSemesters:
    def test_general_dept_one_semester(self):
        assert timetable_scope.allowed_semesters_for({'name': 'القسم العام', 'semesters': 8}) == [1]

    def test_bounded_by_department_semesters(self):
        assert timetable_scope.allowed_semesters_for({'name': 'قسم', 'semesters': 5}) == [2, 3, 4, 5]

    def test_capped_at_eight(self):
        assert timetable_scope.allowed_semesters_for({'name': 'قسم', 'semesters': 12}) == [2, 3, 4, 5, 6, 7, 8]

    def test_missing_semesters_defaults_to_eight(self):
        assert timetable_scope.allowed_semesters_for({'name': 'قسم'}) == [2, 3, 4, 5, 6, 7, 8]

    def test_unparsable_semesters_default_to_eight(self):
        assert timetable_scope.allowed_semesters_for({'name': 'قسم', 'semesters': 'x'}) == [2, 3, 4, 5, 6, 7, 8]

    def test_none_department_is_general(self):
        assert timetable_scope.allowed_semesters_for(None) == [1]


class TestValidateSemesterAllowed:
    def test_allowed_semester_passes(self, raw_db, db_path):
        depts = _make_departments(db_path, [('قسم الفروع', 4)])
        timetable_scope.validate_semester_allowed(raw_db, depts['قسم الفروع'], 3)
        timetable_scope.validate_semester_allowed(raw_db, depts['قسم الفروع'], '2')

    def test_disallowed_semester_raises(self, raw_db, db_path):
        depts = _make_departments(db_path, [('قسم الرقابة', 4)])
        with pytest.raises(timetable_scope.InvalidSemesterError):
            timetable_scope.validate_semester_allowed(raw_db, depts['قسم الرقابة'], 1)
        with pytest.raises(timetable_scope.InvalidSemesterError):
            timetable_scope.validate_semester_allowed(raw_db, depts['قسم الرقابة'], 9)

    def test_general_dept_allows_semester_one_only(self, raw_db, db_path):
        depts = _make_departments(db_path, [('القسم العام', 8)])
        timetable_scope.validate_semester_allowed(raw_db, depts['القسم العام'], 1)
        with pytest.raises(timetable_scope.InvalidSemesterError):
            timetable_scope.validate_semester_allowed(raw_db, depts['القسم العام'], 2)

    def test_unparsable_semester_raises(self, raw_db, db_path):
        depts = _make_departments(db_path, [('قسم المراجعة', 4)])
        with pytest.raises(timetable_scope.InvalidSemesterError):
            timetable_scope.validate_semester_allowed(raw_db, depts['قسم المراجعة'], 'x')

    def test_missing_department_is_tolerated(self, raw_db):
        timetable_scope.validate_semester_allowed(raw_db, None, 1)
        timetable_scope.validate_semester_allowed(raw_db, 9999, 1)


class TestComputeScope:
    def test_anonymous_user(self):
        scope = timetable_scope.compute_scope(None)
        assert scope['can_view'] is False
        assert scope['can_edit'] is False
        assert scope['is_hod'] is False
        assert scope['editable_dept_id'] is None
        assert scope['own_teacher_id'] is None

    def test_empty_user(self):
        scope = timetable_scope.compute_scope({})
        assert scope['can_view'] is False
        assert scope['can_edit'] is False

    def test_rnd_user_can_view_not_edit(self):
        scope = timetable_scope.compute_scope({'id': 1, 'roles': ['research_development']})
        assert scope['can_view'] is True
        assert scope['can_edit'] is False
        assert scope['can_print_all'] is True

    def test_hod_can_edit_own_department(self):
        user = {
            'id': 1,
            'roles': ['head_of_department'],
            'hod_department_id': 7,
            'teacher_id': 9,
        }
        scope = timetable_scope.compute_scope(user)
        assert scope['is_hod'] is True
        assert scope['can_edit'] is True
        assert scope['user_dept'] == 7
        assert scope['editable_dept_id'] == 7
        assert scope['own_teacher_id'] == 9

    def test_single_string_role(self):
        scope = timetable_scope.compute_scope({'id': 1, 'role': 'teacher'})
        assert scope['can_edit'] is False
        assert scope['own_teacher_id'] is None


class TestCanEditEntry:
    def test_non_hod_without_edit_is_refused(self):
        assert not timetable_scope.can_edit_entry({'id': 1, 'roles': ['research_development']}, 5)

    def test_hod_edits_only_own_department(self):
        hod = {'id': 1, 'roles': ['head_of_department'], 'hod_department_id': 7}
        assert timetable_scope.can_edit_entry(hod, 7)
        assert not timetable_scope.can_edit_entry(hod, 8)

    def test_hod_without_department_cannot_edit(self):
        hod = {'id': 1, 'roles': ['head_of_department']}
        assert not timetable_scope.can_edit_entry(hod, 7)


# ─────────────────────────────────────────────
# Translation fallback
# ─────────────────────────────────────────────

class FakeUrlResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestTranslationService:
    def test_empty_input_is_empty_output(self):
        assert translation_service.translate_ar_to_en('') == ''
        assert translation_service.translate_ar_to_en(None) == ''
        assert translation_service.translate_ar_to_en('   ') == ''

    def test_safe_translate_returns_empty_on_failure(self, monkeypatch):
        def boom(_text):
            raise RuntimeError('network down')

        monkeypatch.setattr(translation_service, 'translate_ar_to_en', boom)
        assert translation_service.safe_translate_ar_to_en('نص') == ''

    def test_joins_segments(self, monkeypatch):
        payload = json.dumps([[['engineering', 'هندسة', None, None, 10]]]).encode('utf-8')
        monkeypatch.setattr(
            urllib.request, 'urlopen', lambda _req, timeout=None: FakeUrlResponse(payload),
        )
        assert translation_service.translate_ar_to_en('هندسة') == 'engineering'

    def test_invalid_payload_raises_value_error(self, monkeypatch):
        payload = json.dumps({'weird': True}).encode('utf-8')
        monkeypatch.setattr(
            urllib.request, 'urlopen', lambda _req, timeout=None: FakeUrlResponse(payload),
        )
        with pytest.raises(ValueError):
            translation_service.translate_ar_to_en('هندسة')


# ─────────────────────────────────────────────
# UI constants consistency
# ─────────────────────────────────────────────

class TestUiConstants:
    def test_week_has_six_days(self):
        assert len(WEEK_DAYS) == 6
        assert DAY_ORDER == WEEK_DAYS

    def test_season_order_cycles(self):
        assert SEMESTER_SEASON_ORDER == ['fall', 'spring']
        for season in SEMESTER_SEASON_ORDER:
            after = SEMESTER_SEASON_NEXT[season]
            assert SEMESTER_SEASON_NEXT[after] == season

    def test_arabic_months_complete(self):
        assert len(ARABIC_MONTHS) == 12
        assert set(ARABIC_MONTHS) == set(range(1, 13))