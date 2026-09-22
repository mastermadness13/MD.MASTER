"""Tests for the teacher course-content upload page (المقررات المكلف بها)."""

import io
import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'teacher_cc.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))

    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) VALUES ('office_manager', 'x', 'faculty_affairs', 'مدير مكتب أعضاء هيئة التدريس')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) VALUES ('t1', 'x', 'teacher', 'أ. أحمد')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) VALUES ('t2', 'x', 'teacher', 'أ. سارة')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, has_sections, type) VALUES ('قسم الحاسوب', 8, 8, 0, 1, 'academic')"
    )
    super_id = conn.execute("SELECT id FROM users WHERE username='office_manager'").fetchone()['id']
    t1_uid = conn.execute("SELECT id FROM users WHERE username='t1'").fetchone()['id']
    t2_uid = conn.execute("SELECT id FROM users WHERE username='t2'").fetchone()['id']
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
    conn.execute(
        'INSERT INTO teachers (user_id, name, department_id) VALUES (?, ?, ?)',
        (t1_uid, 'أ. أحمد', dept_id),
    )
    conn.execute(
        'INSERT INTO teachers (user_id, name, department_id) VALUES (?, ?, ?)',
        (t2_uid, 'أ. سارة', dept_id),
    )
    t1 = conn.execute("SELECT id FROM teachers WHERE user_id=?", (t1_uid,)).fetchone()['id']
    t2 = conn.execute("SELECT id FROM teachers WHERE user_id=?", (t2_uid,)).fetchone()['id']

    c1 = conn.execute("SELECT id FROM courses WHERE code='CS101'").fetchone()['id']
    c2 = conn.execute("SELECT id FROM courses WHERE code='CS102'").fetchone()['id']

    # t1 is assigned CS101 (فصل 1 + شعبة أ) and CS102 (فصل 3 + شعبة ب). t2 owns nothing.
    conn.execute(
        '''INSERT INTO timetable (day, semester, course_id, teacher_id, department_id, student_section)
           VALUES ('الأحد', 1, ?, ?, ?, 'أ')''',
        (c1, t1, dept_id),
    )
    conn.execute(
        '''INSERT INTO timetable (day, semester, course_id, teacher_id, department_id, student_section)
           VALUES ('الثلاثاء', 4, ?, ?, ?, 'ب')''',
        (c1, t1, dept_id),
    )
    conn.execute(
        '''INSERT INTO timetable (day, semester, course_id, teacher_id, department_id, student_section)
           VALUES ('الاثنين', 3, ?, ?, ?, 'ب')''',
        (c2, t1, dept_id),
    )

    # CS101: R&D-created form (course_id set, no PDF yet). CS102: no submission.
    conn.execute(
        '''INSERT INTO course_content_submissions
           (user_id, department_id, teacher_id, course_id, course_name, course_code, status)
           VALUES (?, ?, ?, ?, 'مقدمة برمجة', 'CS101', 'pending_teacher')''',
        (super_id, dept_id, t1, c1),
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(app_fx, db_fx):
    t1_uid = _q("SELECT id FROM users WHERE username='t1'")[0]['id']
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = t1_uid
        sess['role'] = 'teacher'
        sess['username'] = 't1'
        sess['_csrf_token'] = 't'
    return c


@pytest.fixture
def other_teacher_client(app_fx, db_fx):
    t2_uid = _q("SELECT id FROM users WHERE username='t2'")[0]['id']
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = t2_uid
        sess['role'] = 'teacher'
        sess['username'] = 't2'
        sess['_csrf_token'] = 't'
    return c


def _q(sql, params=()):
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.commit()
    conn.close()
    return rows


def _course_id(code):
    return _q("SELECT id FROM courses WHERE code=?", (code,))[0]['id']


def _pdf(data=b'%PDF-1.4 unit'):
    return io.BytesIO(data)


# ── صفحة المقررات المكلف بها ──────────────────────────────────────────────


def test_teacher_page_shows_assigned_courses(client):
    r = client.get('/teacher/course-content')
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'المقررات المكلف بها' in body
    for header in ['الكود', 'اسم المقرر', 'نظري', 'عملي', 'الساعات', 'المنهاج', 'المقرر (R']:
        assert header in body
    assert 'CS101' in body
    assert 'CS102' in body
    assert 'CS103' not in body, 'courses not assigned to teacher must be hidden'


def test_teacher_page_binary_upload_badge(client):
    body = client.get('/teacher/course-content').get_data(as_text=True)
    assert 'لم يُرفع المنهج' in body, 'binary state: not uploaded yet'
    assert 'رفع المنهج' in body
    assert 'لا يوجد نموذج مقرر' in body, 'R&D form not present for CS102 (no submission)'


def test_teacher_page_marks_uploaded_when_syllabus_exists(client):
    cid = _course_id('CS102')
    tid = _q("SELECT id FROM teachers WHERE name='أ. أحمد'")[0]['id']
    _q('''INSERT INTO course_files (course_id, file_type, filename, original_filename, file_size, teacher_id, status)
          VALUES (?, 'syllabus', 'syllabus.pdf', 'syllabus-original.pdf', 9, ?, 'approved')''', (cid, tid))
    body = client.get('/teacher/course-content').get_data(as_text=True)
    assert 'تم رفع المنهج' in body
    assert 'تحميل المنهج' in body
    assert 'استبدال' in body


def test_teacher_page_rnd_form_link_only_when_course_form_exists(client):
    body = client.get('/teacher/course-content').get_data(as_text=True)
    assert 'عرض نموذج R' in body, 'CS101 has an R&D-created form → link shown'
    assert 'نموذج المقرر موجود' in body, 'CS101 has a form → green badge shown'
    # CS102 gets a personal (teacher-created) submission WITHOUT course_id —
    # the R&D form link must still not appear for it.
    super_id = _q("SELECT id FROM users WHERE username='office_manager'")[0]['id']
    tid = _q("SELECT id FROM teachers WHERE name='أ. أحمد'")[0]['id']
    dept_id = _q("SELECT id FROM departments WHERE name='قسم الحاسوب'")[0]['id']
    _q('''INSERT INTO course_content_submissions
          (user_id, department_id, teacher_id, course_name, course_code, status)
          VALUES (?, ?, ?, 'تراكيب بيانات', 'CS102', 'draft')''', (super_id, dept_id, tid))
    body = client.get('/teacher/course-content').get_data(as_text=True)
    assert body.count('عرض نموذج R') == 1, 'only the R&D-created (course_id) submission gets the link'
    assert body.count('نموذج المقرر موجود') == 1, 'only CS101 gets the green badge'


def test_teacher_page_has_no_admin_controls(client):
    body = client.get('/teacher/course-content').get_data(as_text=True)
    for legacy in ['رمز المادة', 'اسم المادة', 'إجراءات', 'ccCourseTableBody', 'إنشاء النموذج',
                   'تعديل المقرر', 'بحث']:
        assert legacy not in body, f'admin/legacy control visible on teacher page: {legacy}'


def test_teacher_page_empty_state(app_fx, db_fx):
    t2_uid = _q("SELECT id FROM users WHERE username='t2'")[0]['id']
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = t2_uid  # t2 has no assignments
        sess['role'] = 'teacher'
        sess['username'] = 't2'
        sess['_csrf_token'] = 't'
    body = c.get('/teacher/course-content').get_data(as_text=True)
    assert 'لا توجد مقررات مكلف بها' in body


# ── رفع المنهج (syllabus) ──────────────────────────────────────────────────


def test_syllabus_upload_writes_course_file(client, app_fx, tmp_path, monkeypatch):
    monkeypatch.setitem(app_fx.config, 'UPLOAD_FOLDER', str(tmp_path))
    cid = _course_id('CS102')
    r = client.post('/teacher/course-content/syllabus/upload', data={
        '_csrf_token': 't',
        'course_id': str(cid),
        'file': (_pdf(), 'syllabus.pdf'),
    }, content_type='multipart/form-data')
    assert r.status_code == 302
    row = _q("SELECT * FROM course_files WHERE course_id=? AND file_type='syllabus'", (cid,))[0]
    assert row['filename'].endswith('.pdf')
    assert row['status'] == 'approved'


def test_syllabus_upload_rejects_unassigned_course(client, app_fx, tmp_path, monkeypatch):
    monkeypatch.setitem(app_fx.config, 'UPLOAD_FOLDER', str(tmp_path))
    cid = _course_id('CS103')  # not assigned to t1
    r = client.post('/teacher/course-content/syllabus/upload', data={
        '_csrf_token': 't',
        'course_id': str(cid),
        'file': (_pdf(), 'x.pdf'),
    }, content_type='multipart/form-data')
    assert r.status_code == 302
    assert _q("SELECT COUNT(*) AS n FROM course_files WHERE course_id=?", (cid,))[0]['n'] == 0


# ── إرفاق ملف PDF بالنموذج وإرساله للمراجعة ───────────────────────────────


def test_form_upload_sends_rnd(client, app_fx, tmp_path, monkeypatch):
    import routes.teacher_pages as tp
    monkeypatch.setattr(tp, '_translate_course_content_en', lambda db, sid: None)
    monkeypatch.setitem(app_fx.config, 'UPLOAD_FOLDER', str(tmp_path))
    cid = _course_id('CS101')
    sid = _q("SELECT id FROM course_content_submissions WHERE course_id=?", (cid,))[0]['id']
    r = client.post('/teacher/course-content', data={
        '_csrf_token': 't',
        'action': 'send_rnd',
        'course_id': str(cid),
        'submission_id': str(sid),
        'file': (_pdf(), 'form.pdf'),
    }, content_type='multipart/form-data')
    assert r.status_code == 302
    sub = _q("SELECT status, filename FROM course_content_submissions WHERE id=?", (sid,))[0]
    assert sub['status'] == 'pending_rnd'
    assert sub['filename'].endswith('.pdf')


def test_form_upload_requires_existing_submission(client, app_fx, tmp_path, monkeypatch):
    import routes.teacher_pages as tp
    monkeypatch.setattr(tp, '_translate_course_content_en', lambda db, sid: None)
    monkeypatch.setitem(app_fx.config, 'UPLOAD_FOLDER', str(tmp_path))
    cid = _course_id('CS101')
    r = client.post('/teacher/course-content', data={
        '_csrf_token': 't',
        'action': 'send_rnd',
        'course_id': str(cid),
        'submission_id': '999999',
        'file': (_pdf(), 'form.pdf'),
    }, content_type='multipart/form-data')
    assert r.status_code == 302


def test_form_upload_rejects_disallowed_extension(client, app_fx, tmp_path, monkeypatch):
    """H2: arbitrary extensions (e.g. .html → same-origin stored XSS) must be
    rejected before any file is written or the submission status advanced."""
    import routes.teacher_pages as tp
    monkeypatch.setattr(tp, '_translate_course_content_en', lambda db, sid: None)
    monkeypatch.setitem(app_fx.config, 'UPLOAD_FOLDER', str(tmp_path))
    cid = _course_id('CS101')
    sid = _q("SELECT id FROM course_content_submissions WHERE course_id=?", (cid,))[0]['id']
    r = client.post('/teacher/course-content', data={
        '_csrf_token': 't',
        'action': 'send_rnd',
        'course_id': str(cid),
        'submission_id': str(sid),
        'file': (_pdf(b'<script>alert(1)</script>'), 'payload.html'),
    }, content_type='multipart/form-data')
    assert r.status_code == 302
    sub = _q("SELECT status, filename FROM course_content_submissions WHERE id=?", (sid,))[0]
    assert sub['filename'] == '', 'disallowed extension must not be persisted'
    assert sub['status'] == 'pending_teacher', 'rejected upload must not advance the workflow'
    assert not [p for p in tmp_path.iterdir() if p.name != 'teacher_cc.db'], (
        'nothing may be written to the upload folder')


# ── عرض نموذج R&D (وضع القراءة) ───────────────────────────────────────────


def test_form_view_readonly_for_owner(client):
    cid = _course_id('CS101')
    sid = _q("SELECT id FROM course_content_submissions WHERE course_id=?", (cid,))[0]['id']
    body = client.get(f'/teacher/course-content/{sid}/form').get_data(as_text=True)
    assert 'عرض نموذج المقرر من إعداد البحث والتطوير' in body
    assert 'مقدمة برمجة' in body
    assert 'name="theoretical_curriculum_topic[]"' in body, 'readonly form renders the official theoretical fields'
    assert 'name="practical_content"' in body, 'readonly form renders the practical free-text field'
    assert 'onclick="downloadCourseSheet()"' in body, 'readonly view exposes the sheet download'
    assert 'data-course-code=' in body


def test_form_view_404_for_other_teacher(other_teacher_client):
    cid = _course_id('CS101')
    sid = _q("SELECT id FROM course_content_submissions WHERE course_id=?", (cid,))[0]['id']
    r = other_teacher_client.get(f'/teacher/course-content/{sid}/form')
    assert r.status_code == 404


def test_form_view_requires_course_id(client):
    cid = _course_id('CS101')
    sid = _q("SELECT id FROM course_content_submissions WHERE course_id=?", (cid,))[0]['id']
    _q("UPDATE course_content_submissions SET course_id = NULL WHERE id=?", (sid,))
    r = client.get(f'/teacher/course-content/{sid}/form')
    assert r.status_code == 404