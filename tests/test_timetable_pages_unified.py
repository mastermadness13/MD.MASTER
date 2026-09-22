"""Phase 3: unified timetable pages.

The remaining timetable templates (teacher weekly schedule, all-departments
list, create/edit form, lecture hub) adopt the shared config-boot pattern:
one ``static/js/timetable_pages.js`` bundle replaces the old
``timetable_list.js`` and ``pages/timetable_teacher.js`` scripts, and the
form/hub chrome match the module's ``page-header`` language.
"""

import os
import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'tt_pages.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) VALUES ('exam', 'x', 'exam', 'الامتحانات')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, has_sections, type) VALUES ('قسم الحاسوب', 8, 8, 0, 1, 'academic')"
    )
    dept_id = conn.execute("SELECT id FROM departments WHERE name='قسم الحاسوب'").fetchone()['id']
    conn.execute(
        "INSERT INTO timetable_versions (department_id, semester, semester_code, status) VALUES (?, 2, 'fall_2026', 'active')",
        (dept_id,),
    )
    c = conn.execute(
        "INSERT INTO courses (code, name, department_id, year, semester, theoretical_hours, practical_hours, total_hours) "
        "VALUES ('TT-P3', 'مقرر المرحلة الثالثة', ?, 1, 2, 2, 1, 3)",
        (dept_id,),
    )
    cid = c.lastrowid
    t = conn.execute("INSERT INTO teachers (name, department_id) VALUES (?, ?)", ('أ. سلمى', dept_id))
    tid = t.lastrowid
    r = conn.execute("INSERT INTO rooms (name, code) VALUES (?, ?)", ('قاعة 3', 'R3'))
    rid = r.lastrowid
    v = conn.execute("SELECT id FROM timetable_versions WHERE department_id=? AND status='active'", (dept_id,)).fetchone()['id']
    conn.execute(
        "INSERT INTO timetable (day, semester, period, course_id, teacher_id, room_id, department_id, version_id, start_time, end_time) "
        "VALUES ('الأحد', 2, 'A', ?, ?, ?, ?, ?, '09:00', '12:00')",
        (cid, tid, rid, dept_id, v),
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(app_fx, db_fx):
    conn = sqlite3.connect(flask_db.DATABASE)
    dept_id = conn.execute("SELECT id FROM departments WHERE name='قسم الحاسوب'").fetchone()[0]
    conn.close()
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'head_of_department'
        sess['username'] = 'hod'
        sess['department_id'] = dept_id
        sess['hod_department_id'] = dept_id
        sess['_csrf_token'] = 't'
    return c


def _read_js(name):
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, '..', 'static', 'js', name), encoding='utf-8') as fh:
        return fh.read()


def test_list_page_wires_shared_pages_bundle(client):
    """الجدول العام (print/timetable) يستخدم الحزمة المشتركة بدل timetable_list.js."""
    body = client.get('/print/timetable').get_data(as_text=True)
    assert 'timetable_pages.js' in body, 'shared pages bundle wired'
    assert 'TIMETABLE_LIST_BOOT' in body, 'list boot config present'
    assert 'timetable_list.js' not in body, 'legacy list script gone'
    assert 'tt-mobile-grid' in body
    assert 'hidden lg:block' in body
    assert 'deleteEntry' in body, 'per-cell delete handler still rendered'


def test_teacher_schedule_wires_shared_pages_bundle(app_fx, db_fx):
    """جدولي الأسبوعي (/teacher/my-schedule) يربط حزمة الأكورديون المشتركة."""
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.execute("INSERT OR IGNORE INTO users (username, password, role, label) VALUES ('t1', 'x', 'teacher', 'معلم')")
    uid = conn.execute("SELECT id FROM users WHERE username='t1'").fetchone()[0]
    tid = conn.execute("SELECT id FROM teachers WHERE name='أ. سلمى'").fetchone()[0]
    conn.execute('UPDATE teachers SET user_id=? WHERE id=?', (uid, tid))
    conn.commit()
    conn.close()

    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = uid
        sess['role'] = 'teacher'
        sess['username'] = 't1'
        sess['_csrf_token'] = 't'

    body = c.get('/teacher/my-schedule').get_data(as_text=True)
    assert 'TIMETABLE_TEACHER_BOOT' in body, 'teacher boot config present'
    assert 'timetable_pages.js' in body, 'shared pages bundle wired'
    assert 'pages/timetable_teacher.js' not in body, 'legacy teacher script gone'
    assert 'tt-mcard' in body, 'seeded entry renders a mobile card'
    assert 'overflow-x-auto hidden lg:block' in body, 'desktop accordion table hidden on phones'


def test_teachers_schedule_admin_route_uses_shared_bundle(client):
    """قائمة جدول المدرسين (/timetable/teachers-schedule) تعرض نفس الحزمة."""
    body = client.get('/timetable/teachers-schedule').get_data(as_text=True)
    assert 'timetable_pages.js' in body
    assert 'TIMETABLE_TEACHER_BOOT' in body
    assert 'timetable_pages.js' in body


def test_shared_pages_bundle_uses_toast_and_csrf():
    """الحزمة المشتركة تحذف عبر CSRF وتعرض toast — بلا alert()."""
    js = _read_js('timetable_pages.js')
    assert 'deleteEntry' in js
    assert 'X-CSRFToken' in js
    assert 'csrf-token' in js
    assert 'toast' in js
    assert 'alert(' not in js, 'blocking alert replaced by toast'
    assert 'TIMETABLE_TEACHER_BOOT' in js
    assert 'TIMETABLE_LIST_BOOT' in js


def test_create_form_page_unified(client, db_fx):
    """نموذج الإضافة: رأس page-header + رجوع سياقي لقسم/فصل عبر محرر القسم."""
    conn = sqlite3.connect(flask_db.DATABASE)
    dept_id = conn.execute("SELECT id FROM departments WHERE name='قسم الحاسوب'").fetchone()[0]
    conn.close()
    body = client.get('/timetable/create?department_id={}&semester=2'.format(dept_id)).get_data(as_text=True)
    assert 'page-header' in body
    assert 'page-title' in body
    assert 'إضافة حصة' in body
    assert '/timetable/department?department_id={}&amp;semester=2'.format(dept_id) in body, 'back link preserves dept + semester'
    assert 'name="_csrf_token"' in body
    assert 'action="/timetable/create"' in body


def test_edit_form_page_unified(client, db_fx):
    """نموذج التعديل: رأس موحّد ورجوع سياقي يحمل القسم والفصل."""
    conn = sqlite3.connect(flask_db.DATABASE)
    entry = conn.execute("SELECT id, department_id, semester FROM timetable LIMIT 1").fetchone()
    conn.close()
    body = client.get('/timetable/{}/edit'.format(entry[0])).get_data(as_text=True)
    assert 'تعديل حصة' in body
    assert '/timetable/department?department_id={}&amp;semester={}'.format(entry[1], entry[2]) in body
    assert 'action="/timetable/{}/edit"'.format(entry[0]) in body


def test_lecture_hub_links_unified_views(client):
    """مركز الجداول يربط بطرق العرض الموحّدة الثلاث + طباعة."""
    body = client.get('/lecture-schedule').get_data(as_text=True)
    assert 'page-header' in body
    assert 'href="/timetable/"' in body or 'href="/timetable"' in body, 'unified combined view link'
    assert 'href="/timetable/department"' in body, 'unified department editor link'
    assert 'href="/timetable/teachers-schedule"' in body, 'teacher schedules link'
    assert 'href="/print/timetables/all"' in body, 'print link wired'
    assert 'تعديل' not in body, 'hub stays read-only'


def test_old_page_scripts_removed():
    """ملفّا السلوك القديمان حُذفا — التحقّق مما تبقّى من الحزمة الموحّدة."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.join(here, '..')
    assert not os.path.exists(os.path.join(root, 'static', 'js', 'timetable_list.js'))
    assert not os.path.exists(os.path.join(root, 'static', 'js', 'pages', 'timetable_teacher.js'))