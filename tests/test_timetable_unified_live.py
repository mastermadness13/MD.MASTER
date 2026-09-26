"""Live-sync tests for the unified timetable page.

Covers: the semantic version token endpoint (GET /api/timetable/version/token)
that fingerprints the current version for a department/semester, the
``?format=json`` payload mode used by the poller, and the unified page boot.
"""

import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'tt_live.db'
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


def _hod_client(app_fx, dept_id):
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = 2
        sess['role'] = 'head_of_department'
        sess['username'] = 'hod'
        sess['department_id'] = dept_id
        sess['hod_department_id'] = dept_id
        sess['_csrf_token'] = 't'
    return c


def _dept_id(name='قسم الحاسوب'):
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.row_factory = sqlite3.Row
    row = conn.execute('SELECT id FROM departments WHERE name=?', (name,)).fetchone()
    conn.close()
    return row['id']


def _token(client, dept_id, semester):
    r = client.get('/api/timetable/version/token',
                   query_string={'department_id': dept_id, 'semester': semester})
    return r


def test_token_endpoint_returns_fingerprint(client):
    """القطة الجوهرية تعيد رمزاً نصياً ثابت المفعول لكل قسم/فصل."""
    r = _token(client, _dept_id(), 2)
    data = r.get_json()
    assert r.status_code == 200
    assert data['ok'] is True
    assert isinstance(data['data']['token'], str)
    assert data['data']['token']


def test_token_changes_when_entries_change(client):
    """تغيير الحصص يغيّر رمز النسخة — إشارة تحديث للعمليات المتزامنة."""
    dept_id = _dept_id()
    before = _token(client, dept_id, 2).get_json()['data']['token']

    conn = sqlite3.connect(flask_db.DATABASE)
    conn.row_factory = sqlite3.Row
    v = conn.execute(
        "SELECT id FROM timetable_versions WHERE department_id=? AND status='active'",
        (dept_id,),
    ).fetchone()['id']
    c = conn.execute(
        "INSERT INTO courses (code, name, department_id, year, semester, theoretical_hours, practical_hours, total_hours) "
        "VALUES ('TT-LIVE', 'مقرر حي', ?, 1, 2, 2, 1, 3)",
        (dept_id,),
    )
    cid = c.lastrowid
    t = conn.execute("INSERT INTO teachers (name, department_id) VALUES (?, ?)", ('أ. الحي', dept_id))
    tid = t.lastrowid
    r = conn.execute("INSERT INTO rooms (name, code) VALUES (?, ?)", ('قاعة الحي', 'LV-1'))
    rid = r.lastrowid
    conn.execute(
        "INSERT INTO timetable (day, semester, period, course_id, teacher_id, room_id, department_id, version_id) "
        "VALUES ('الأحد', 2, 'A', ?, ?, ?, ?, ?)",
        (cid, tid, rid, dept_id, v),
    )
    conn.commit()
    conn.close()

    after = _token(client, dept_id, 2).get_json()['data']['token']
    assert after != before, 'adding an entry must bump the version fingerprint'


def test_token_invalid_semester_rejected(client):
    """الفصل غير المسموح (القسم العام) يُرفض برمز 422 — نفس رسالة الفصل."""
    general = _dept_id('القسم العام')
    r = _token(client, general, 2)
    data = r.get_json()
    assert r.status_code == 422
    assert data['ok'] is False
    assert 'الفصل المختار غير مسموح لهذا القسم' in data['message']


def test_token_missing_department_404(client):
    """قسم غير موجود يُعيد 404."""
    r = _token(client, 99999, 1)
    assert r.status_code == 404
    assert r.get_json()['ok'] is False


def test_department_page_json_payload_mode(app_fx, db_fx):
    """الوضع ?format=json يُعيد نفس حمولة صفحة الجدول لفاحص التحديث."""
    dept_id = _dept_id()
    client = _hod_client(app_fx, dept_id)
    r = client.get('/timetable/department',
                   query_string={'department_id': dept_id, 'semester': 2, 'format': 'json'})
    data = r.get_json()
    assert r.status_code == 200
    assert data['ok'] is True
    body = data['data']
    assert body['dept']['name'] == 'قسم الحاسوب'
    assert body['selected_semester'] == 2
    assert body['can_manage'] is True
    assert 'form' in body
    assert 'syllabus' in body
    assert 'entries' in body


def test_rnd_page_json_payload_is_read_only(app_fx, db_fx):
    """شخصية البحث والتطوير (can_manage=False) تظهر في الحمولة حتى في وضع JSON."""
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) VALUES ('rnd', 'x', 'research_development', 'البحث والتطوير')"
    )
    rnd_id = conn.execute("SELECT id FROM users WHERE username='rnd'").fetchone()[0]
    conn.commit()
    conn.close()
    rc = app_fx.test_client()
    with rc.session_transaction() as sess:
        sess['user_id'] = rnd_id
        sess['role'] = 'research_development'
        sess['username'] = 'rnd'
        sess['department_id'] = None
        sess['_csrf_token'] = 't'
    r = rc.get('/timetable/rnd',
               query_string={'department_id': _dept_id(), 'semester': 2, 'format': 'json'})
    data = r.get_json()
    assert r.status_code == 200
    assert data['ok'] is True
    assert data['data']['can_manage'] is False


def test_unified_page_boots_live_assets(client):
    """صفحة الجدول الموحّدة تحمّل ملف التحديث الحي مع نقطة الرمز الأولي."""
    body = client.get('/timetable/department?department_id={}&semester=2'.format(_dept_id())).get_data(as_text=True)
    assert 'TIMETABLE_UNIFIED_BOOT' in body
    assert 'id="liveBadge"' in body
    assert 'timetable_live.js' in body
    assert 'initialToken' in body
    assert 'syllabusUrls' in body


def test_modal_department_is_fixed_for_department_scoped_user(app_fx, db_fx):
    dept_id = _dept_id()
    hod = _hod_client(app_fx, dept_id)
    body = hod.get(
        '/timetable/department?department_id={}&semester=2'.format(dept_id)
    ).get_data(as_text=True)

    assert 'id="lecDept" type="hidden"' in body
    assert 'id="lecDept" class="mt-1' not in body


def test_modal_keeps_department_selector_for_switchable_user(client):
    body = client.get(
        '/timetable/department?department_id={}&semester=2'.format(_dept_id())
    ).get_data(as_text=True)

    assert 'id="lecDept" class="mt-1' in body
    assert 'id="lecDept" type="hidden"' not in body


def test_modal_options_follow_current_department_and_semester(client):
    with open('static/js/timetable_live.js', encoding='utf-8') as source:
        js = source.read()
    body = client.get(
        '/timetable/department?department_id={}&semester=2'.format(_dept_id())
    ).get_data(as_text=True)

    assert 'id="semFilter"' in body
    assert '>الفصل:</label>' in body
    assert 'setModalSemesters(availableSemesters, selSem)' in js
    assert "semSel.value = String(selected || '')" in js
    assert "slotRow.classList.toggle('hidden', !!(day && period))" in js
    assert "format: 'json'" in js
    assert 'function deptCourses()' in js