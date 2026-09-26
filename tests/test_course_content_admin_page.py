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
        "INSERT OR IGNORE INTO users (username, password, role, label) VALUES ('rnd', 'x', 'research_development', 'البحث والتطوير')"
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
        sess['role'] = 'research_development'
        sess['username'] = 'rnd'
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
    assert 'رفع محتوى المقرر' in body
    assert '<table' in body
    for header in ['المادة', 'القسم', 'الفصل', 'المدرّس', 'النموذج', 'الساعات', 'الإجراءات']:
        assert header in body
    assert 'ccCourseTableBody' in body, 'table body is filled by JS'
    courses = _courses_json(body)
    assert {c['code'] for c in courses} == {'CS101', 'CS102', 'CS103'}
    assert 'بحث' in body


def test_action_cells_reflect_status(client):
    """كل مقرر: 4 أزرار (تحميل المقرر/تحميل المنهج/طباعة المقرر/إنشاء-تعديل المقرر) ولا أزرار رفع/عرض منفصلة."""
    body = client.get('/teacher/super-admin/course-content').get_data(as_text=True)
    js = _read_js('static/js/teachers_super_admin_course_content.js')
    assert 'js/teachers_super_admin_course_content.js' in body, 'external page script is loaded'
    assert 'تحميل المقرر' in js
    assert 'تحميل المنهج' in js
    assert 'طباعة المقرر' in js
    assert 'إنشاء/تعديل المقرر' in js
    assert 'تحميل المقرر' in js
    assert 'تحميل المنهج' in js
    assert 'طباعة المقرر' in js
    assert 'إنشاء/تعديل المقرر' in js
    # هيكلياً: زر تحميل المنهج يُبنى عند وجود المنهاج؛ زرّا الطباعة والإنشاء/التعديل دائماً
    assert 'if (syl && syl.id) {' in js
    assert 'if (syl && syl.id) {\n      items +=' in js, 'download button only when syllabus exists'
    # زر تحميل المقرر يُبنى عند وجود ملف النموذج المعتمد (يستخدم /course-file/)
    assert 'if (form && form.id) {' in js
    assert "href=\"/course-file/' + form.id + '?download=1\"" in js, 'course form downloads via canonical course-file route'
    assert "onclick=\"ccPreparePrint(this)\"" in js
    assert 'items += \'<a href="\' + formEditUrl + \'">' in js, 'edit button built unconditionally'
    # الطباعة تتم عبر iframe مخفي (لا فتح صفحة ولا تنقّل)
    assert 'ccPreparePrint' in js
    assert 'window.ccPreparePrint = ccPreparePrint;' in js, 'should be global for inline onclick'
    assert "frame.src = '/teacher/super-admin/course-content/' + sid + '?print=1'" in js
    assert 'win.print()' in js
    # لا أزرار منفصلة قديمة (رفع/عرض/متابعة/إنشاء/تعديل نموذج)
    assert 'إنشاء النموذج' not in js
    assert 'متابعة النموذج' not in js
    assert 'تعديل النموذج' not in js
    # زر تحميل النموذج موجود داخل pdfCell (بجانب شارة الحالة في عمود النموذج)، لا في قائمة الإجراءات
    assert 'تحميل النموذج' in js, 'download for the form lives in the pdf cell next to the badge'
    assert 'عرض النموذج' not in js
    assert 'عرض المنهج' not in js
    # لا أزرار رفع منهاج أو نموذج في قائمة المقررات (المنهاج عرض فقط)
    assert "'+ c.id + '/syllabus/upload" not in js
    assert "'+ c.id + '/form/upload" not in js
    assert 'رفع محتوى المقرر' in body
    # docs تحت التدقيق في مُصيّر الإجراءات
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
    import page_routes.teacher_pages as tp
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
    import page_routes.teacher_pages as tp
    monkeypatch.setattr(tp, '_translate_course_content_en', lambda db, sid: None)
    cid = _course_id('CS103')
    data = {'_csrf_token': 't', 'action': 'save', 'course_id': str(cid)}
    r = client.post('/teacher/super-admin/course-content/send', data=data)
    assert r.status_code == 302
    sub = _q("SELECT status FROM course_content_submissions WHERE course_id=?", (cid,))[0]
    assert sub['status'] == 'draft'


def test_send_requires_department(client, app_fx, tmp_path, monkeypatch):
    import page_routes.teacher_pages as tp
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
    import page_routes.teacher_pages as tp
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
    import page_routes.teacher_pages as tp
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


def test_codes_tab_prefills_stored_submission(client):
    cid = _course_id('CS101')
    sid = _q("SELECT id FROM course_content_submissions WHERE course_id=?", (cid,))[0]['id']
    body = client.get(f'/courses/codes?tab=content&course_id={cid}&submission_id={sid}').get_data(as_text=True)
    assert 'name="course_name"' in body


def test_codes_tab_for_course_without_submission(client):
    cid = _course_id('CS103')
    body = client.get(f'/courses/codes?tab=content&course_id={cid}').get_data(as_text=True)
    assert 'name="course_name"' in body
    assert 'name="submission_id"' not in body, 'new form has no submission id yet'
    assert re.search(r'<tbody id="ccTheoreticalCurriculumBody">\s*</tbody>', body)
    assert re.search(r'<tbody id="ccPracticalCurriculumBody">\s*</tbody>', body)
    assert 'name="theoretical_curriculum_present" value="1"' in body
    assert 'name="practical_curriculum_present" value="1"' in body


def test_curriculum_rows_are_manual_and_both_sections_stop_at_12_weeks():
    script = _read_js('static/js/pages/teachers__course_content_doc.js')
    template = _read_js('templates/teachers/_course_content_doc.html')

    assert 'ensureTrailingCurriculumRow' not in script
    assert 'maybeAddCurriculumRow' not in script
    assert script.count('limit: WEEKS_LIMIT') == 2
    assert "if (recalcSection(section) >= section.limit) return;" in script
    assert 'practicalWeeksTotal > WEEKS_LIMIT' in script
    assert 'total > section.limit' in script
    assert 'name="theoretical_curriculum_weeks[]" value="{{ row.weeks or 1 }}"' in template
    assert template.count('max="12"') == 2


def test_codes_tab_is_sheet_only(client):
    cid = _course_id('CS103')
    body = client.get(f'/courses/codes?tab=content&course_id={cid}').get_data(as_text=True)
    # Floating action bar retains the essential controls
    assert 'name="academic_period_id"' in body
    assert 'id="formFileInput"' not in body, 'end-of-form PDF file picker removed'
    # Single combined button: save + publish (data-action="send") with default send
    assert 'data-action="send"' in body
    assert 'data-action="save"' not in body, 'draft-only button removed'
    assert 'حفظ مفردات المقرر' in body
    assert 'value="send" id="formAction"' in body
    # Old heavy cards/header are gone
    assert 'id="ccCourseSelect"' not in body
    assert 'ارفق ملف PDF للنموذج ليصبح قابلاً للتحميل' not in body
    assert 'تعبئة بيانات النموذج والمنهاج' not in body
    # Dual curriculum tables + download wiring
    assert 'id="ccTheoreticalCurriculumBody"' in body
    assert 'name="practical_content"' in body
    assert 'name="practical_content_en"' in body
    assert 'onclick="downloadCourseSheet()"' in body
    assert 'data-course-code="CS103"' in body
    assert 'id="ccSheetStyle"' in body
    # Legacy content columns removed
    assert 'curriculum_content[]' not in body
    # Prerequisites is a plain single-line text input
    assert 'name="prerequisites"' in body
    assert 'textarea name="prerequisites"' not in body
    assert '<input type="text" name="prerequisites"' in body
    # Tutorial hours present in the weekly-hours row
    assert 'name="tutorial_hours"' in body
    # Hours row keeps an EN label so both sides are symmetric
    assert 'No. Of hours' in body


def test_send_persists_curriculum_sections(client, app_fx, tmp_path, monkeypatch):
    import page_routes.teacher_pages as tp
    monkeypatch.setattr(tp, '_translate_course_content_en', lambda db, sid: None)
    cid = _course_id('CS103')
    data = {
        '_csrf_token': 't', 'action': 'send', 'course_id': str(cid),
        'theoretical_curriculum_topic[]': ['نظري 1', 'نظري 2'],
        'theoretical_curriculum_weeks[]': ['2', '3'],
        'theoretical_curriculum_topic_en[]': ['Theory 1', 'Theory 2'],
        'practical_content': 'تطبيقات عملية على المقرر',
        'practical_content_en': 'Practical applications',
    }
    r = client.post('/teacher/super-admin/course-content/send', data=data)
    assert r.status_code == 302
    rows = _q("SELECT topic, weeks, topic_en, section FROM course_content_curriculum "
              "WHERE submission_id = (SELECT id FROM course_content_submissions "
              "WHERE course_id=? ORDER BY id DESC LIMIT 1) ORDER BY sort_order", (cid,))
    assert [x['topic'] for x in rows] == ['نظري 1', 'نظري 2']
    assert [x['section'] for x in rows] == ['theoretical', 'theoretical']
    assert rows[0]['weeks'] == 2
    sub = _q("SELECT practical_content, practical_content_en "
             "FROM course_content_submissions WHERE course_id=?"
             " ORDER BY id DESC LIMIT 1", (cid,))[0]
    assert sub['practical_content'] == 'تطبيقات عملية على المقرر'
    assert sub['practical_content_en'] == 'Practical applications'


def test_send_edit_preserves_omitted_legacy_curriculum_fields(client, monkeypatch):
    import page_routes.teacher_pages as tp
    monkeypatch.setattr(tp, '_translate_course_content_en', lambda db, sid: None)
    cid = _course_id('CS102')
    sid = _q("SELECT id FROM course_content_submissions WHERE course_id=?", (cid,))[0]['id']
    _q(
        '''INSERT INTO course_content_curriculum
           (submission_id, topic, weeks, content, sort_order, topic_en, content_en, section)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (sid, 'موضوع قديم', 2, 'محتوى تفصيلي', 0, 'Old topic', 'Detailed content', 'theoretical'),
    )
    _q(
        '''INSERT INTO course_content_curriculum
           (submission_id, topic, weeks, content, sort_order, topic_en, content_en, section)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (sid, 'تطبيق قديم', 1, 'محتوى تطبيقي محفوظ', 1, 'Old practical', 'Saved practical content', 'practical'),
    )
    response = client.post('/teacher/super-admin/course-content/send', data={
        '_csrf_token': 't',
        'action': 'save',
        'course_id': str(cid),
        'submission_id': str(sid),
        'theoretical_curriculum_topic[]': ['موضوع محدّث'],
        'theoretical_curriculum_weeks[]': ['3'],
        'theoretical_curriculum_topic_en[]': ['Updated topic'],
    })
    assert response.status_code == 302
    rows = _q(
        '''SELECT topic, content, topic_en, content_en, section
           FROM course_content_curriculum WHERE submission_id=? ORDER BY sort_order''',
        (sid,),
    )
    assert rows == [
        {
            'topic': 'موضوع محدّث',
            'content': 'محتوى تفصيلي',
            'topic_en': 'Updated topic',
            'content_en': 'Detailed content',
            'section': 'theoretical',
        },
        {
            'topic': 'تطبيق قديم',
            'content': 'محتوى تطبيقي محفوظ',
            'topic_en': 'Old practical',
            'content_en': 'Saved practical content',
            'section': 'practical',
        },
    ]


def test_send_edit_uses_curriculum_row_ids_when_rows_are_omitted(client, monkeypatch):
    import page_routes.teacher_pages as tp
    monkeypatch.setattr(tp, '_translate_course_content_en', lambda db, sid: None)
    cid = _course_id('CS102')
    sid = _q("SELECT id FROM course_content_submissions WHERE course_id=?", (cid,))[0]['id']
    _q(
        '''INSERT INTO course_content_curriculum
           (submission_id, topic, weeks, content, sort_order, topic_en, content_en, section)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (sid, 'الموضوع الأول', 2, 'محتوى أول', 0, 'First topic', 'First content', 'theoretical'),
    )
    _q(
        '''INSERT INTO course_content_curriculum
           (submission_id, topic, weeks, content, sort_order, topic_en, content_en, section)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (sid, 'الموضوع الثاني', 3, 'محتوى ثان', 1, 'Second topic', 'Second content', 'theoretical'),
    )
    old_rows = _q(
        'SELECT id FROM course_content_curriculum WHERE submission_id=? ORDER BY sort_order',
        (sid,),
    )
    second_id = old_rows[1]['id']
    response = client.post('/teacher/super-admin/course-content/send', data={
        '_csrf_token': 't',
        'action': 'save',
        'course_id': str(cid),
        'submission_id': str(sid),
        'theoretical_curriculum_id[]': [str(second_id)],
        'theoretical_curriculum_topic[]': ['الموضوع الثاني المحدث'],
        'theoretical_curriculum_weeks[]': ['4'],
        'theoretical_curriculum_topic_en[]': ['Second topic updated'],
    })
    assert response.status_code == 302
    saved = _q(
        'SELECT topic, weeks, content, topic_en, content_en FROM course_content_curriculum '
        'WHERE submission_id=?',
        (sid,),
    )
    assert saved == [{
        'topic': 'الموضوع الثاني المحدث',
        'weeks': 4,
        'content': 'محتوى ثان',
        'topic_en': 'Second topic updated',
        'content_en': 'Second content',
    }]


def test_codes_tab_shows_period_picker(client):
    cid = _course_id('CS103')
    body = client.get(f'/courses/codes?tab=content&course_id={cid}').get_data(as_text=True)
    assert 'name="academic_period_id"' in body


def test_send_rejects_theoretical_weeks_over_12(client, app_fx, tmp_path, monkeypatch):
    import page_routes.teacher_pages as tp
    monkeypatch.setattr(tp, '_translate_course_content_en', lambda db, sid: None)
    cid = _course_id('CS103')
    before = _q("SELECT COUNT(*) AS n FROM course_content_submissions WHERE course_id=?", (cid,))[0]['n']
    data = {
        '_csrf_token': 't', 'action': 'send', 'course_id': str(cid),
        'theoretical_curriculum_topic[]': ['مقرر طويل'],
        'theoretical_curriculum_weeks[]': ['13'],
        'theoretical_curriculum_topic_en[]': ['Long course'],
    }
    r = client.post('/teacher/super-admin/course-content/send', data=data)
    assert r.status_code == 302
    after = _q("SELECT COUNT(*) AS n FROM course_content_submissions WHERE course_id=?", (cid,))[0]['n']
    assert after == before, 'submission with >12 theoretical weeks must not be saved'
    rows = _q("SELECT COUNT(*) AS n FROM course_content_curriculum "
              "WHERE submission_id = (SELECT id FROM course_content_submissions "
              "WHERE course_id=? ORDER BY id DESC LIMIT 1)", (cid,))[0]['n']
    assert rows == 0, 'no curriculum rows may be persisted for a rejected submission'


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


def test_detail_view_has_download_and_dual_curriculum(client):
    sid = _q("SELECT id FROM course_content_submissions WHERE status='published'")[0]['id']
    body = client.get(f'/teacher/super-admin/course-content/{sid}').get_data(as_text=True)
    assert 'مفردات الجانب النظري' in body
    assert 'مفردات الجانب العملي' in body
    assert 'onclick="downloadCourseSheet()"' in body
    assert 'data-course-code=' in body


def test_detail_print_boot_and_script(client):
    sid = _q("SELECT id FROM course_content_submissions WHERE status='published'")[0]['id']
    body = client.get(f'/teacher/super-admin/course-content/{sid}').get_data(as_text=True)
    assert 'js/teachers_course_content_page.js' in body, 'external detail script is loaded'
    assert 'auto_print: false' in body
    assert 'window.print()' in body, 'print button present'
    # ?print=1 يُفعّل الطباعة التلقائية
    body2 = client.get(f'/teacher/super-admin/course-content/{sid}?print=1').get_data(as_text=True)
    assert 'auto_print: true' in body2


def test_course_sheet_print_flows_across_pages_without_clipping(client):
    """The printed sheet must flow over several A4 pages and never clip text."""
    sid = _q("SELECT id FROM course_content_submissions WHERE status='published'")[0]['id']
    body = client.get(f'/teacher/super-admin/course-content/{sid}').get_data(as_text=True)
    script = _read_js('static/js/pages/teachers__course_content_doc.js')

    # A4 page box, owned by the sheet stylesheet
    assert '@page { size: A4 portrait; margin: 10mm; }' in body
    assert '--cc-print-zoom' in body

    # No absolute positioning and no forced single page: content must paginate
    assert 'position: static !important' in body
    assert 'position: absolute' not in body
    assert 'break-inside: avoid; page-break-inside: avoid' in body

    # Table headers repeat on continuation pages, footers do not
    assert 'display: table-header-group' in body
    assert 'display: table-row-group' in body

    # Running footer repeated at the bottom of every page
    assert 'cc-print-footer' in body
    assert 'position: fixed' in body

    # Textareas print at the height JS measured — never `height: auto`
    assert 'height: var(--cc-auto-height, auto) !important' in body
    sheet_css = re.sub(r'/\*.*?\*/', '', body, flags=re.S)  # ignore comments
    textarea_print_rules = re.findall(r'body \.cc-sheet textarea \{(.*?)\}', sheet_css, re.S)
    assert textarea_print_rules, 'print rules for textareas are missing'
    assert not any('height: auto' in rule for rule in textarea_print_rules), \
        'textarea height must come from the measured --cc-auto-height, never auto'
    assert any('var(--cc-auto-height' in rule for rule in textarea_print_rules)
    assert 'scrollHeight' in script
    assert 'font-size: max' not in body
    assert 'Promise.resolve(flushTranslations())' in script


def test_course_sheet_exposes_both_curriculum_sections(client):
    """Theoretical + practical curricula are both editable, translated and printed."""
    cid = _course_id('CS103')
    body = client.get(f'/courses/codes?tab=content&course_id={cid}').get_data(as_text=True)
    assert 'id="ccTheoreticalCurriculumBody"' in body
    assert 'id="ccPracticalCurriculumBody"' in body
    assert 'id="ccAddTheoreticalRow"' in body
    assert 'id="ccAddPracticalRow"' in body
    assert 'id="ccPracticalWeeksTotal"' in body
    script = _read_js('static/js/pages/teachers__course_content_doc.js')
    assert "_curriculum_topic[]\"" in script
    assert "_curriculum_topic_en[]\"" in script
    assert "_curriculum_weeks[]\"" in script
    # The official header is part of the printed sheet
    assert 'كلية التقنية الهندسية زوارة' in body
    assert 'cc-sheet-meta' in body
    assert 'صفحة 1 من 1' not in body, 'hardcoded page counter removed'


def test_translate_endpoint_maps_practical_curriculum_topic(client, monkeypatch):
    import api_routes.course_content as api

    api.translation_limiter.reset_all()
    monkeypatch.setattr(api, 'safe_translate_ar_to_en', lambda text: 'Practical topic')
    response = client.post(
        '/api/course-content/translate',
        json={
            '_csrf_token': 't',
            'field': 'practical_curriculum_topic',
            'text': 'موضوع عملي',
            'row_index': 2,
        },
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['data']['target'] == 'practical_curriculum_topic_en'
    assert payload['data']['text'] == 'Practical topic'


# ── pdfState — عمود «الملف» المباشر (المرحلة 2) ──────────────────────────


def test_boot_keys_are_camelcase(client):
    """BOOT must use the exact keys the JS reads: formByCourse / departmentNames."""
    body = client.get('/teacher/super-admin/course-content').get_data(as_text=True)
    assert 'formByCourse:' in body
    assert 'departmentNames:' in body
    assert 'formbycourse:' not in body
    assert 'departmentnames:' not in body


def test_pdf_state_exposed_for_every_row(client):
    """كل صف يحمل pdf_state مشتقاً من آخر تسليم مع مراعاة ورقة المقرر القابلة للتنزيل."""
    body = client.get('/teacher/super-admin/course-content').get_data(as_text=True)
    courses = {c['code']: c for c in _courses_json(body)}
    assert courses['CS101']['pdf_state'] == 'available', 'published submission → downloadable sheet'
    assert courses['CS102']['pdf_state'] == 'draft'
    assert courses['CS103']['pdf_state'] == 'none'
    assert all('pdf_state' in c for c in _courses_json(body))


def test_pdf_state_available_wins_over_submission(client):
    """وجود ملف نموذج في course_files يجعل الحالة available (تحميل بنقرة واحدة)."""
    cid = _course_id('CS101')
    sid = _q("SELECT id FROM course_content_submissions WHERE course_id=?", (cid,))[0]['id']
    _q('''INSERT INTO course_files (course_id, submission_id, file_type, filename,
                                    original_filename, file_size, status)
          VALUES (?, ?, 'form', 'form.pdf', 'form-original.pdf', 9, 'published')''',
       (cid, sid))
    body = client.get('/teacher/super-admin/course-content').get_data(as_text=True)
    courses = {c['code']: c for c in _courses_json(body)}
    assert courses['CS101']['pdf_state'] == 'available'


def test_pdf_state_mapping_unit():
    from services.course_content_service import pdf_state_for
    assert pdf_state_for('published') == 'approved'
    assert pdf_state_for('approved') == 'approved'
    assert pdf_state_for('pending_rnd') == 'pending_review'
    assert pdf_state_for('pending_hod') == 'pending_review'
    assert pdf_state_for('draft') == 'draft'
    assert pdf_state_for('rejected') == 'rejected'
    assert pdf_state_for('') == 'none'
    assert pdf_state_for('unknown') == 'none'
    assert pdf_state_for('rejected', True) == 'available'
    assert pdf_state_for('', True) == 'available'


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


def test_public_course_content_is_readonly_without_login(app_fx, db_fx):
    sid = _q("SELECT id FROM course_content_submissions WHERE status='published'")[0]['id']
    response = app_fx.test_client().get(f'/course-content/{sid}')
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'data-translation-editable="false"' in body
    assert 'data-course-content-manager="teachers__course_content_doc"' in body
    assert 'id="courseContentForm"' not in body
    assert 'id="ccAddTheoreticalRow"' not in body
    assert 'data-action="send"' not in body
    assert re.search(r'<input[^>]+name="course_name"[^>]+disabled', body)
    assert re.search(r'<textarea[^>]+name="course_objective"[^>]+disabled', body)
    assert re.search(r'<textarea[^>]+name="practical_content"[^>]+disabled', body)


def test_course_content_document_keeps_english_left_and_arabic_right(client):
    sid = _q("SELECT id FROM course_content_submissions WHERE status='published'")[0]['id']
    body = client.get(f'/teacher/super-admin/course-content/{sid}').get_data(
        as_text=True
    )

    assert '.cc-sheet .document-table {' in body
    assert 'direction: ltr;' in body
    assert '.cc-sheet .cc-value-cell.cc-ar {' in body
    assert '.cc-sheet .cc-block-cell.cc-ar { direction: rtl; }' in body
    assert body.index('Course Title') < body.index('اسم المادة')


def test_public_course_content_keeps_legacy_submission_without_course(app_fx, db_fx):
    department_id = _q("SELECT id FROM departments LIMIT 1")[0]['id']
    _q(
        '''INSERT INTO course_content_submissions
           (user_id, department_id, course_id, course_name, course_code, status)
           VALUES (1, ?, NULL, ?, ?, 'published')''',
        (department_id, 'مقرر قديم', 'OLD101'),
    )
    sid = _q(
        "SELECT id FROM course_content_submissions WHERE course_code='OLD101'"
    )[0]['id']
    response = app_fx.test_client().get(f'/course-content/{sid}')
    assert response.status_code == 200
    assert 'مقرر قديم' in response.get_data(as_text=True)


def test_translation_endpoint_rejects_anonymous_client(app_fx, db_fx):
    import api_routes.course_content as api
    api.translation_limiter.reset_all()
    response = app_fx.test_client().post(
        '/api/course-content/translate',
        json={'field': 'notes', 'text': 'ملاحظات'},
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    assert response.status_code == 403


# ── قيم None / فارغة في حقول العدد (credits و hours) ──────────────────────


def test_codes_tab_never_renders_none_or_undefined_for_null_credits(client):
    """courses.accreditation = NULL → credits input renders value="0", never
    "None" nor "undefined" (float and JS both stay clean)."""
    cid = _course_id('CS103')
    _q('UPDATE courses SET accreditation = NULL WHERE id = ?', (cid,))
    body = client.get(f'/courses/codes?tab=content&course_id={cid}').get_data(as_text=True)
    assert 'value="None"' not in body
    assert 'undefined' not in body
    assert 'name="credits" min="0" value="0"' in body
    # الساعات تبقى كما هي من بيانات المقرر (ليست None)
    assert 'name="theory_hours" min="0" value="3"' in body
    assert 'name="practical_hours" min="0" value="1"' in body


def test_submission_view_never_renders_none_for_null_credits(client):
    """course_content_submissions.credits = NULL → view mode renders value="0"."""
    cid = _course_id('CS101')
    sid = _q("SELECT id FROM course_content_submissions WHERE course_id=?", (cid,))[0]['id']
    _q('UPDATE course_content_submissions SET credits = NULL WHERE id = ?', (sid,))
    body = client.get(f'/teacher/super-admin/course-content/{sid}').get_data(as_text=True)
    assert 'value="None"' not in body
    assert 'undefined' not in body
    assert 'name="credits" min="0" value="0"' in body


def test_send_with_empty_credits_stores_zero(client, app_fx, tmp_path, monkeypatch):
    """POST credits='' يخزّن 0 وليس '' ولا 'None' (مسار إنشاء جديد)."""
    import page_routes.teacher_pages as tp
    monkeypatch.setattr(tp, '_translate_course_content_en', lambda db, sid: None)
    cid = _course_id('CS103')
    data = {'_csrf_token': 't', 'action': 'save', 'course_id': str(cid), 'credits': ''}
    r = client.post('/teacher/super-admin/course-content/send', data=data)
    assert r.status_code == 302
    sub = _q("SELECT credits FROM course_content_submissions "
             "WHERE course_id=? ORDER BY id DESC LIMIT 1", (cid,))[0]
    assert sub['credits'] == 0
    assert sub['credits'] != ''
    assert sub['credits'] != 'None'


def test_send_empty_credits_on_edit_updates_row_to_zero(client, app_fx, tmp_path, monkeypatch):
    """تعديل نفس السجل مع credits='' يحوّل القيمة إلى 0 في نفس الصف."""
    import page_routes.teacher_pages as tp
    monkeypatch.setattr(tp, '_translate_course_content_en', lambda db, sid: None)
    cid = _course_id('CS101')
    sid = _q("SELECT id FROM course_content_submissions WHERE course_id=?", (cid,))[0]['id']
    data = {'_csrf_token': 't', 'action': 'save', 'course_id': str(cid),
            'submission_id': str(sid), 'credits': ''}
    r = client.post('/teacher/super-admin/course-content/send', data=data)
    assert r.status_code == 302
    subs = _q("SELECT id, credits FROM course_content_submissions WHERE course_id=?", (cid,))
    assert len(subs) == 1, 'edit must UPDATE the same row, not insert'
    assert subs[0]['id'] == sid
    assert subs[0]['credits'] == 0
    assert subs[0]['credits'] != ''
    assert subs[0]['credits'] != 'None'


def test_translation_endpoint_returns_english_for_allowed_field(client, monkeypatch):
    import api_routes.course_content as api

    api.translation_limiter.reset_all()
    monkeypatch.setattr(api, 'safe_translate_ar_to_en', lambda text: 'English objective')
    response = client.post(
        '/api/course-content/translate',
        json={
            '_csrf_token': 't',
            'field': 'course_objective',
            'text': 'هدف المقرر',
        },
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    assert response.status_code == 200
    assert response.get_json()['data']['target'] == 'course_objective_en'
    assert response.get_json()['data']['text'] == 'English objective'


def test_translation_endpoint_rejects_empty_arabic(client, monkeypatch):
    import api_routes.course_content as api

    api.translation_limiter.reset_all()
    called = []
    monkeypatch.setattr(api, 'safe_translate_ar_to_en', lambda text: called.append(text) or 'unexpected')
    response = client.post(
        '/api/course-content/translate',
        json={
            '_csrf_token': 't',
            'field': 'course_objective',
            'text': '   ',
        },
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    assert response.status_code == 422
    assert not called
