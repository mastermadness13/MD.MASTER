"""Tests for the R&D course-content flow (create-publish forms; view syllabi only)."""

import io
import json
import re
import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'cc_admin.db'
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
    for code, name, year, sem in [
        ('CS101', 'مقدمة برمجة', 1, 1),
        ('CS102', 'تراكيب بيانات', 2, 3),
        ('CS103', 'شبكات', 3, 5),
    ]:
        conn.execute(
            '''INSERT INTO courses (code, name, department_id, year, semester,
                                    theoretical_hours, practical_hours, total_hours)
               VALUES (?, ?, ?, ?, ?, 3, 1, 4)''',
            (code, name, dept_id, year, sem),
        )
    c1 = conn.execute("SELECT id FROM courses WHERE code='CS101'").fetchone()['id']
    c2 = conn.execute("SELECT id FROM courses WHERE code='CS102'").fetchone()['id']
    # CS101: published form; CS102: draft; CS103: none
    conn.execute(
        '''INSERT INTO course_content_submissions
           (user_id, department_id, course_id, course_name, course_code, status)
           VALUES (1, ?, ?, ?, ?, 'published')''',
        (dept_id, c1, 'مقدمة برمجة', 'CS101'),
    )
    conn.execute(
        '''INSERT INTO course_content_submissions
           (user_id, department_id, course_id, course_name, course_code, status)
           VALUES (1, ?, ?, ?, ?, 'draft')''',
        (dept_id, c2, 'تراكيب بيانات', 'CS102'),
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


def _read_js(relpath):
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, '..', relpath), encoding='utf-8') as fh:
        return fh.read()


def _js_value(body, key):
    """Extract a JS value (`[...]`) exposed by the server BOOT block on the page."""
    m = re.search(re.escape(key) + r'\s*:\s*(\[)', body)
    assert m, key + ' JSON payload must be embedded for the JS-rendered table'
    s = m.start(1)
    depth = 0
    in_str = False
    esc = False
    i = s
    while i < len(body):
        ch = body[i]
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    break
        i += 1
    return json.loads(body[s:i + 1])


def _courses_json(body):
    return _js_value(body, 'courses')


def _course_id(code):
    return _q("SELECT id FROM courses WHERE code=?", (code,))[0]['id']


# ── قائمة المقررات (تحميل المقررات) ──────────────────────────────────────


def test_page_renders_courses_table(client):
    r = client.get('/teacher/super-admin/course-content')
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'رفع المقرر' in body
    assert '<table' in body
    for header in ['رمز المادة', 'اسم المادة', 'القسم', 'حالة النموذج', 'إجراءات']:
        assert header in body
    assert 'ccCourseTableBody' in body, 'table body is filled by JS'
    courses = _courses_json(body)
    assert {c['code'] for c in courses} == {'CS101', 'CS102', 'CS103'}
    assert 'بحث' in body


def test_action_cells_reflect_status(client):
    """كل مقرر: 3 أزرار فقط (تحميل المنهج/طباعة المقرر/تعديل المقرر) ولا أزرار رفع/عرض/تحميل منفصلة."""
    body = client.get('/teacher/super-admin/course-content').get_data(as_text=True)
    js = _read_js('static/js/teachers_super_admin_course_content.js')
    assert 'js/teachers_super_admin_course_content.js' in body, 'external page script is loaded'
    assert 'تحميل المنهج' in js
    assert 'طباعة المقرر' in js
    assert 'تعديل المقرر' in js
    # هيكلياً: دالة الإجراءات تُنتج 3 أزرار بالضبط دائماً (لا شرط لإنشاء زر إضافي)
    assert 'actBtn(sylHref, \'download\', \'تحميل المنهج\')' in js
    assert 'printBtn(\'طباعة المقرر\')' in js
    assert 'actBtn(formEditUrl, \'edit\', \'تعديل المقرر\')' in js
    # الطباعة تتم عبر iframe مخفي (لا فتح صفحة ولا تنقّل)
    assert 'ccPreparePrint' in js
    assert 'window.ccPreparePrint = ccPreparePrint;' in js, 'should be global for inline onclick'
    assert "frame.src = '/teacher/super-admin/course-content/' + sid + '?print=1'" in js
    assert 'win.print()' in js
    assert 'if (syl && syl.id) {' not in js, 'no conditional button creation allowed'
    # لا أزرار منفصلة قديمة (رفع/عرض/متابعة/إنشاء/تعديل/تحميل نموذج)
    assert 'إنشاء النموذج' not in js
    assert 'متابعة النموذج' not in js
    assert 'تعديل النموذج' not in js
    assert 'تحميل النموذج' not in js
    assert 'description' not in js, 'زر تحميل المقرر (أيقونة description) يجب أن يختفي نهائياً'
    assert 'عرض النموذج' not in js
    assert 'عرض المنهج' not in js
    # لا أزرار رفع منهاج أو نموذج في قائمة المقررات (المنهاج عرض فقط)
    assert "'+ c.id + '/syllabus/upload" not in js
    assert "'+ c.id + '/form/upload" not in js
    assert 'رفع المقرر' in body
    # docs \u062a\u062d\u062a \u0627\u0644\u062a\u062f\u0642\u064a\u0642 في مُصيّر الإجراءات
    assert "'+ c.id + '\" class=\"w-7 h-7 flex items-center justify-center rounded-lg hover:bg-blue-50" not in js


def test_statuses_shown_in_filters_and_badges(client):
    body = client.get('/teacher/super-admin/course-content').get_data(as_text=True)
    js = _read_js('static/js/shared/course_helpers.js')
    assert 'value="published"' in body, 'published option present in filter'
    assert 'منشور' in body
    assert "'published': 'منشور'" in js, 'status label map lives in the shared helpers bundle'
    assert 'قيد مراجعة البحث والتطوير' not in js, 'legacy pending statuses removed'


def test_list_search_serverside(client):
    body = client.get('/teacher/super-admin/course-content?search=شبكات').get_data(as_text=True)
    courses = _courses_json(body)
    assert {c['code'] for c in courses} == {'CS103'}


# ── إنشاء / نشر النموذج ──────────────────────────────────────────────────


def test_send_new_form_publishes(client, app_fx, tmp_path, monkeypatch):
    import routes.teacher_pages as tp
    monkeypatch.setattr(tp, '_translate_course_content_en', lambda db, sid: None)
    cid = _course_id('CS103')
    data = {'_csrf_token': 't', 'action': 'send', 'course_id': str(cid),
            'credits': '3', 'course_objective': 'هدف'}
    r = client.post('/teacher/super-admin/course-content/send', data=data)
    assert r.status_code == 302
    sub = _q("SELECT status, course_objective FROM course_content_submissions "
             "WHERE course_id=? ORDER BY id DESC LIMIT 1", (cid,))[0]
    assert sub['status'] == 'published'
    assert sub['course_objective'] == 'هدف'


def test_send_saves_draft(client, app_fx, tmp_path, monkeypatch):
    import routes.teacher_pages as tp
    monkeypatch.setattr(tp, '_translate_course_content_en', lambda db, sid: None)
    cid = _course_id('CS103')
    data = {'_csrf_token': 't', 'action': 'save', 'course_id': str(cid)}
    r = client.post('/teacher/super-admin/course-content/send', data=data)
    assert r.status_code == 302
    sub = _q("SELECT status FROM course_content_submissions WHERE course_id=?", (cid,))[0]
    assert sub['status'] == 'draft'


def test_send_requires_department(client, app_fx, tmp_path, monkeypatch):
    import routes.teacher_pages as tp
    monkeypatch.setattr(tp, '_translate_course_content_en', lambda db, sid: None)
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.execute("UPDATE courses SET department_id = NULL WHERE code='CS103'")
    conn.commit()
    conn.close()
    cid = _course_id('CS103')
    data = {'_csrf_token': 't', 'action': 'send', 'course_id': str(cid)}
    r = client.post('/teacher/super-admin/course-content/send', data=data)
    assert r.status_code == 302


def test_send_with_submission_id_updates_same_row(client, app_fx, tmp_path, monkeypatch):
    """إعادة الإرسال (تعديل) تحدّث نفس السجل ولا تُنشئ سجلاً جديداً."""
    import routes.teacher_pages as tp
    monkeypatch.setattr(tp, '_translate_course_content_en', lambda db, sid: None)
    cid = _course_id('CS101')
    sid = _q("SELECT id FROM course_content_submissions WHERE course_id=?", (cid,))[0]['id']
    data = {'_csrf_token': 't', 'action': 'send', 'course_id': str(cid),
            'submission_id': str(sid), 'credits': '4', 'course_objective': 'هدف محدَّث'}
    r = client.post('/teacher/super-admin/course-content/send', data=data)
    assert r.status_code == 302
    subs = _q("SELECT id, status, credits, course_objective "
              "FROM course_content_submissions WHERE course_id=?", (cid,))
    assert len(subs) == 1, 'edit must UPDATE the same row, not insert'
    assert subs[0]['id'] == sid
    assert subs[0]['status'] == 'published'
    assert subs[0]['credits'] == 4
    assert subs[0]['course_objective'] == 'هدف محدَّث'


def test_send_edit_rewrites_curriculum(client, app_fx, tmp_path, monkeypatch):
    import routes.teacher_pages as tp
    monkeypatch.setattr(tp, '_translate_course_content_en', lambda db, sid: None)
    cid = _course_id('CS101')
    sid = _q("SELECT id FROM course_content_submissions WHERE course_id=?", (cid,))[0]['id']
    data = {
        '_csrf_token': 't', 'action': 'send', 'course_id': str(cid),
        'submission_id': str(sid),
        'curriculum_topic[]': ['أساسيات', 'الحلقات'],
        'curriculum_weeks[]': ['2', '3'],
        'curriculum_content[]': ['تعريف', 'تمارين'],
    }
    r = client.post('/teacher/super-admin/course-content/send', data=data)
    assert r.status_code == 302
    rows = _q("SELECT topic FROM course_content_curriculum WHERE submission_id=? "
              "ORDER BY sort_order", (sid,))
    assert [x['topic'] for x in rows] == ['أساسيات', 'الحلقات']


def test_create_page_prefills_stored_submission(client):
    cid = _course_id('CS101')
    sid = _q("SELECT id FROM course_content_submissions WHERE course_id=?", (cid,))[0]['id']
    body = client.get(f'/teacher/super-admin/course-content/create?course_id={cid}&submission_id={sid}').get_data(as_text=True)
    assert r"value=\"مقدمة برمجة\"" in body or 'مقدمة برمجة' in body
    assert 'name="submission_id"' in body, 'edit mode embeds the submission id'


def test_create_page_for_course_without_submission(client):
    cid = _course_id('CS103')
    body = client.get(f'/teacher/super-admin/course-content/create?course_id={cid}').get_data(as_text=True)
    assert 'شبكات' in body
    assert 'name="submission_id"' not in body, 'new form has no submission id yet'


def test_create_page_shows_period_picker(client):
    cid = _course_id('CS103')
    body = client.get(f'/teacher/super-admin/course-content/create?course_id={cid}').get_data(as_text=True)
    assert 'name="academic_period_id"' in body


# ── صفحة تفاصيل النموذج ──────────────────────────────────────────────────


def test_detail_page_has_edit_button(client):
    sid = _q("SELECT id FROM course_content_submissions WHERE status='published'")[0]['id']
    body = client.get(f'/teacher/super-admin/course-content/{sid}').get_data(as_text=True)
    assert body.count('تعديل النموذج') >= 1
    assert 'بدون بيانات نموذج' not in body


def test_detail_edit_link_points_to_create(client):
    sid = _q("SELECT id FROM course_content_submissions WHERE status='published'")[0]['id']
    body = client.get(f'/teacher/super-admin/course-content/{sid}').get_data(as_text=True)
    assert f'submission_id={sid}' in body


def test_detail_print_boot_and_script(client):
    sid = _q("SELECT id FROM course_content_submissions WHERE status='published'")[0]['id']
    body = client.get(f'/teacher/super-admin/course-content/{sid}').get_data(as_text=True)
    assert 'js/teachers_course_content_page.js' in body, 'external detail script is loaded'
    assert 'auto_print: false' in body
    assert 'window.print()' in body, 'print button present'
    # ?print=1 يُفعّل الطباعة التلقائية
    body2 = client.get(f'/teacher/super-admin/course-content/{sid}?print=1').get_data(as_text=True)
    assert 'auto_print: true' in body2


# ── سلسلة الظهور العام ───────────────────────────────────────────────────


def test_public_library_serves_published_forms(client, app_fx, tmp_path, monkeypatch):
    monkeypatch.setitem(app_fx.config, 'UPLOAD_FOLDER', str(tmp_path))
    pdf = tmp_path / 'form.pdf'
    pdf.write_bytes(b'%PDF-1.4 form')
    cid = _course_id('CS101')
    sid = _q("SELECT id FROM course_content_submissions WHERE course_id=?", (cid,))[0]['id']
    _q("UPDATE course_content_submissions SET filename='form.pdf', "
       "original_filename='form-original.pdf', file_size=9 WHERE id=?", (sid,))
    _q('''INSERT INTO course_files (course_id, submission_id, file_type, filename,
                                    original_filename, file_size, status)
          VALUES (?, ?, 'form', 'form.pdf', 'form-original.pdf', 9, 'published')''',
       (cid, sid))
    fid = _q("SELECT id FROM course_files WHERE submission_id=?", (sid,))[0]['id']

    r = client.get(f'/course-file/{fid}')
    assert r.status_code == 200
    assert b'%PDF' in r.data

    # قائمة المقررات العامة تُشمل النماذج المنشورة
    body = client.get('/public/api/courses').get_data(as_text=True)
    payload = json.loads(body)
    courses = {c['id']: c for c in payload['courses']}
    assert courses[cid].get('formFile') is not None, 'published form visible publicly'