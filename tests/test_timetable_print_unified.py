"""Print timeline unification tests.

The standalone department print page (/print/timetables/department) shares the
same ``get_department_view`` payload as the unified live grid, applies the same
role scoping (HOD always prints only their own department, like other HOD
scoped views), rejects invalid semesters with a redirect to the allowed one,
and stamps the printed sheet with the same semantic version fingerprint shown
on the live grid. The unified grid's print button opens this fresh print page
(never stale after live-sync polling).
"""

import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'tt_print.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) VALUES ('exam', 'x', 'exam', 'الامتحانات')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) VALUES ('hod', 'x', 'head_of_department', 'رئيس قسم')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, has_sections, type) VALUES ('قسم الحاسوب', 8, 8, 0, 1, 'academic')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, has_sections, type) VALUES ('القسم العام', 1, 1, 0, 0, 'academic')"
    )
    dept_id = conn.execute("SELECT id FROM departments WHERE name='قسم الحاسوب'").fetchone()['id']
    conn.execute(
        "INSERT INTO timetable_versions (department_id, semester, semester_code, status) VALUES (?, 2, 'fall_2026', 'active')",
        (dept_id,),
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(app_fx, db_fx):
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'research_development'
        sess['username'] = 'rnd'
        sess['department_id'] = None
        sess['_csrf_token'] = 't'
    return c


@pytest.fixture
def hod_client(app_fx, db_fx):
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = 2
        sess['role'] = 'head_of_department'
        sess['username'] = 'hod'
        sess['department_id'] = _dept_id('قسم الحاسوب')
        sess['hod_department_id'] = _dept_id('القسم العام')
        sess['_csrf_token'] = 't'
    return c


def _dept_id(name='قسم الحاسوب'):
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.row_factory = sqlite3.Row
    row = conn.execute('SELECT id FROM departments WHERE name=?', (name,)).fetchone()
    conn.close()
    return row['id']


def _print(client, dept_id, semester=2, version_id=None):
    params = {'department_id': dept_id, 'semester': semester}
    if version_id is not None:
        params['version_id'] = version_id
    return client.get('/print/timetables/department', query_string=params)


def _token(client, dept_id, semester):
    return client.get('/api/timetable/version/token',
                      query_string={'department_id': dept_id, 'semester': semester})


def test_print_department_shares_live_payload_and_stamps_version(client):
    """طباعة القسم تشارك حمولة الجدول الحي وتضرب نفس رمز النسخة."""
    dept_id = _dept_id()
    r = _print(client, dept_id, 2)
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'قسم الحاسوب' in body
    assert 'الجدول الدراسي' in body
    assert 'رمز الإصدار' in body
    token = _token(client, dept_id, 2).get_json()['data']['token']
    assert token in body, 'printed fingerprint must match the live token'
    assert 'عودة للجدول' in body
    assert '/timetable/department?department_id={}&amp;semester=2'.format(dept_id) in body


def test_print_department_header_shows_period_times(client):
    """رأس الجدول المطبوع يعرض وقت الفترة تحت الرمز مثل الجدول الحي."""
    r = _print(client, _dept_id(), 2)
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'الفترة الأولى' in body
    assert '9:00 ص' in body
    assert '12:00 م' in body
    assert 'dir="ltr"' in body


def test_print_department_invalid_semester_redirects_to_allowed(client):
    """فصل غير مسموح (القسم العام) يُعاد توجيهه إلى الفصل المسموح الأول."""
    general = _dept_id('القسم العام')
    r = _print(client, general, 2)
    assert r.status_code == 302
    assert '/print/timetables/department' in r.headers['Location']
    assert 'department_id={}'.format(general) in r.headers['Location']
    assert 'semester=1' in r.headers['Location']


def test_print_department_missing_dept_redirects_to_unified(client):
    """طباعة بدون قسم تُعيد إلى صفحة الجدول الموحّدة."""
    r = client.get('/print/timetables/department')
    assert r.status_code == 302
    assert r.headers['Location'] == '/timetable/department'


def test_print_department_unknown_dept_redirects_to_unified(client):
    """قسم غير موجود يُعاد إلى صفحة الجدول الموحّدة."""
    r = _print(client, 99999, 1)
    assert r.status_code == 302
    assert r.headers['Location'] == '/timetable/department'


def test_print_department_hod_scoped_to_own_department(hod_client):
    """رئيس القسم يطبع قسمه دائماً حتى لو طلب قسماً آخر في الرابط."""
    other = _dept_id('قسم الحاسوب')
    body = _print(hod_client, other, 1).get_data(as_text=True)
    assert 'القسم العام' in body
    assert 'قسم الحاسوب' not in body


def test_unified_page_wires_separate_print_route(client):
    """صفحة الجدول الموحّدة تمرر رابط الطباعة للجلبة."""
    body = client.get('/timetable/department?department_id={}&semester=2'.format(_dept_id())).get_data(as_text=True)
    assert 'printUrl' in body
    assert '/print/timetables/department' in body


def test_live_bundle_opens_print_route_with_live_state():
    """زر الطباعة يفتح صفحة الطباعة بحالة الجدول الفعلية بدل طباعة الحالة القديمة."""
    with open('static/js/timetable_live.js', encoding='utf-8') as f:
        js = f.read()
    assert 'BOOT.printUrl' in js
    assert "searchParams.set('department_id'" in js
    assert "searchParams.set('semester'" in js
    assert 'window.open(u.toString(), \'_blank\')' in js
    assert '[TIMETABLE PRINT]' in js
    assert 'window.print()' not in js


def test_print_department_missing_semester_redirects_to_unified(client):
    """طباعة بدون فصل تُعاد إلى صفحة الجدول الموحّدة (لا فاصل افتراضي صامت)."""
    dept_id = _dept_id()
    r = client.get('/print/timetables/department', query_string={'department_id': dept_id})
    assert r.status_code == 302
    assert r.headers['Location'].startswith('/timetable/department')


def test_print_department_semester_4_preserved_and_prints_fourth(client):
    """الفصل الرابع لا يُسقَط ليصبح الثاني — الطباعة تمرّر semester=4 كما هو."""
    dept_id = _dept_id()
    r = client.get('/print/timetables/department',
                   query_string={'department_id': dept_id, 'semester': 4})
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'الفصل الرابع' in body
    assert 'قسم الحاسوب' in body
    assert 'الفصل الثاني' not in body


def test_print_matches_live_semester_and_fingerprint_at_four(client):
    """طباعة الفصل الرابع تتطابق مع سمستر الواجهة ونفس رمز النسخة."""
    dept_id = _dept_id()
    live = client.get('/timetable/department',
                      query_string={'department_id': dept_id, 'semester': 4, 'format': 'json'}).get_json()
    assert live['ok'] is True
    body = live['data']
    assert body['selected_semester'] == 4
    token = _token(client, dept_id, 4).get_json()['data']['token']
    print_body = client.get('/print/timetables/department',
                            query_string={'department_id': dept_id, 'semester': 4}).get_data(as_text=True)
    assert token in print_body