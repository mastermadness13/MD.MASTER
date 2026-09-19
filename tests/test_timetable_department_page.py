"""Smoke tests for the department weekly-timetable page toolbar UX.

Covers: single status badge wording, per-button tooltips, the helper hint,
and the
create-next-year API activating a fresh version.
"""

import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'tt_department.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))

    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)

    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) VALUES ('superadmin', 'x', 'super_admin', 'مدير')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, has_sections, type) VALUES ('قسم الحاسوب', 8, 8, 0, 1, 'academic')"
    )
    dept_id = conn.execute("SELECT id FROM departments WHERE name='قسم الحاسوب'").fetchone()['id']
    # Active version for the first available semester (2) — current, editable
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
        sess['role'] = 'super_admin'
        sess['username'] = 'superadmin'
        sess['department_id'] = None
        sess['_csrf_token'] = 't'
    return c


def _q(sql, params=()):
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.commit()
    conn.close()
    return rows


def _dept_id():
    return _q("SELECT id FROM departments WHERE name='قسم الحاسوب'")[0]['id']


def _version(status):
    return _q(
        "SELECT id FROM timetable_versions WHERE department_id=? AND status=?",
        (_dept_id(), status),
    )[0]['id']


def _read_js():
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, '..', 'static', 'js', 'timetable_department.js'),
              encoding='utf-8') as fh:
        return fh.read()


def test_current_table_shows_editable_badge_and_hint(client):
    """الجدول الحالي يُظهر شارة «قابل للتعديل» وسطر المساعدة، بأزرار أدوار واضحة."""
    r = client.get('/timetable/department')
    body = r.get_data(as_text=True)
    js = _read_js()
    assert r.status_code == 200
    # The status labels are built client-side in the external script bundle.
    assert 'الجدول الحالي' in js
    assert 'قابل للتعديل' in js
    assert 'أضِف/عدّل الحصص في الجدول، ثم أنشئ نسخة العام القادم' in body
    # شارة واحدة فقط — ما عاد هنالك «وضع التحرير» ولا «محفوظ (نشط)»
    assert js.count('قابل للتعديل') >= 1
    assert 'وضع التحرير' not in js
    assert 'محفوظ (نشط)' not in js
    # أدوار الأزرار عبر title
    assert 'title="طباعة الجدول الحالي"' in body
    assert 'title="إنشاء نسخة العام القادم"' in body
    assert 'id="nextYearBtn"' in body

def test_delete_entry_removes_row(client):
    """زر «حذف» في نافذة تفاصيل المحاضرة: DELETE عبر /timetable/api/delete-entry يزيل السجل فعلاً."""
    dept_id = _dept_id()
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.row_factory = sqlite3.Row
    existing = conn.execute("SELECT id FROM courses WHERE code='TT-DEL'").fetchone()
    if not existing:
        c = conn.execute(
            "INSERT INTO courses (code, name, department_id, year, semester, theoretical_hours, practical_hours, total_hours) "
            "VALUES ('TT-DEL', 'مقرر حذف', ?, 1, 2, 2, 1, 3)",
            (dept_id,),
        )
        cid = c.lastrowid
        t = conn.execute("INSERT INTO teachers (name, department_id) VALUES (?, ?)", ('معلم', dept_id))
        tid = t.lastrowid
        r = conn.execute("INSERT INTO rooms (name, code) VALUES (?, ?)", ('قاعة حذف', 'DEL-1'))
        rid = r.lastrowid
        v = conn.execute("SELECT id FROM timetable_versions WHERE department_id=? AND status='active'", (dept_id,)).fetchone()['id']
        e = conn.execute(
            "INSERT INTO timetable (day, semester, period, course_id, teacher_id, room_id, department_id, version_id) "
            "VALUES ('الأحد', 2, 'C', ?, ?, ?, ?, ?)",
            (cid, tid, rid, dept_id, v),
        )
        eid = e.lastrowid
        conn.commit()
        conn.close()
    else:
        conn.close()
        eid = _q("SELECT id FROM timetable WHERE day='الأحد'")[0]['id']

    r = client.post('/timetable/api/delete-entry', json={
        '_csrf_token': 't',
        'lecture_id': eid,
    })
    data = r.get_json()
    assert r.status_code == 200
    assert data['ok'] is True
    assert _q('SELECT id FROM timetable WHERE id=?', (eid,)) == [], 'row removed from the database'

    r2 = client.post('/timetable/api/delete-entry', json={
        '_csrf_token': 't',
        'lecture_id': eid,
    })
    data2 = r2.get_json()
    assert data2['ok'] is False, 'deleting a missing row reports failure'


def test_print_timetable_cells_have_download_buttons(client):
    """الجدول الدراسي (list.html) يعرض زرّي تحميل المقرر/المنهج في الخلايا عبر /course-file/."""
    dept_id = _dept_id()
    v = _version('active')
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.row_factory = sqlite3.Row
    c = conn.execute(
        "INSERT INTO courses (code, name, department_id, year, semester, theoretical_hours, practical_hours, total_hours) "
        "VALUES ('TT-LIST', 'مقرر الجدول', ?, 1, 1, 2, 1, 3)",
        (dept_id,),
    )
    cid = c.lastrowid
    t = conn.execute("INSERT INTO teachers (name, department_id) VALUES (?, ?)", ('معلم الجدول', dept_id))
    tid = t.lastrowid
    r = conn.execute("INSERT INTO rooms (name, code) VALUES (?, ?)", ('قاعة الجدول', 'LST-1'))
    rid = r.lastrowid
    conn.execute(
        "INSERT INTO timetable (day, semester, period, course_id, teacher_id, room_id, department_id, version_id) "
        "VALUES ('الأحد', 1, 'C', ?, ?, ?, ?, ?)",
        (cid, tid, rid, dept_id, v),
    )
    sid = conn.execute(
        "INSERT INTO course_content_submissions (user_id, department_id, course_id, course_name, course_code, status) "
        "VALUES (1, ?, ?, 'مقرر الجدول', 'TT-LIST', 'published')",
        (dept_id, cid),
    ).lastrowid
    conn.execute(
        "INSERT INTO course_files (course_id, submission_id, file_type, filename, original_filename, file_size, status) "
        "VALUES (?, ?, 'form', 'form.pdf', 'form.pdf', 9, 'published')",
        (cid, sid),
    )
    conn.execute(
        "INSERT INTO course_files (course_id, submission_id, file_type, filename, original_filename, file_size, status) "
        "VALUES (?, ?, 'syllabus', 'syl.pdf', 'syl.pdf', 9, 'approved')",
        (cid, sid),
    )
    conn.commit()
    conn.close()

    body = client.get('/print/timetable').get_data(as_text=True)
    assert '/course-file/' in body
    assert 'تحميل المقرر' in body
    assert 'تحميل المنهج' in body


def test_create_next_year_activates_new_version(client):
    """واجهة برمجة التطبيقات تنشئ نسخة الفصل القادم وتجعلها نشطة بدل القديمة."""
    active = _version('active')
    r = client.post('/timetable/api/version/create-next', json={
        '_csrf_token': 't',
        'version_id': active,
        'copy_entries': False,
    })
    data = r.get_json()
    assert r.status_code == 200
    assert data['ok'] is True
    assert data['url']
    new_id = data['version_id']

    rows = _q('SELECT id, semester_code, status FROM timetable_versions WHERE department_id=?',
              (_dept_id(),))
    statuses = {row['status'] for row in rows}
    assert 'superseded' in statuses, 'the old current version is superseded'
    new_row = [row for row in rows if row['id'] == new_id][0]
    assert new_row['status'] == 'active', 'the freshly created version becomes active'
    assert new_row['semester_code'] != 'fall_2026', 'name advances to the next semester'