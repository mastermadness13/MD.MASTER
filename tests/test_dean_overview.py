"""Dean (العميد) comprehensive read-only overview — the /dashboard/dean.html page.

Regression coverage for the oversight dashboard and for the write-guards that
keep it read-only. The dean holds view-only permissions across every domain
(departments.view, timetable.view, rooms.view, exams.view, history.view ...),
so any template that renders a write control for that role is a leak: the
server would reject the POST with a permission error after showing the button.
"""

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema

# Section headings rendered by templates/dashboard/dean.html.
OVERVIEW_SECTIONS = (
    'الهوية والصلاحيات',
    'الأقسام',
    'الجدولة',
    'هيئة التدريس',
    'الامتحانات',
    'التواصل',
    'أعباء التدريس',
    'سجل العمليات',
    'دليل صفحات المنصة',
)

# Endpoints the dean is expected to be able to read. All are permission-gated
# with a permission the dean role actually holds.
DEAN_DIRECTORY_PATHS = (
    '/departments',
    '/teachers',
    '/teachers/teaching-record',
    '/courses',
    '/rooms',
    '/timetable/',
    '/timetable/department',
    '/timetable/teachers-schedule',
    '/exams',
    '/history',
    '/faculty-performance/reports',
    '/faculty-performance/performance-rate-list',
)


@pytest.fixture
def overview_db(tmp_path, monkeypatch):
    """Small dataset that touches every section of the overview."""
    db_path = tmp_path / 'dean_overview.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))

    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)

    conn.execute(
        "INSERT INTO departments (name, semesters, majors, hidden, has_sections, type) "
        "VALUES ('قسم الحاسوب', 7, 8, 0, 1, 'academic')"
    )
    dept_id = conn.execute(
        "SELECT id FROM departments WHERE name='قسم الحاسوب'"
    ).fetchone()['id']

    conn.execute(
        "INSERT INTO courses (code, name, department_id) VALUES ('CS1', 'مقرر', ?)",
        (dept_id,),
    )
    conn.execute(
        "INSERT INTO teachers (name, department_id) VALUES ('أستاذ', ?)", (dept_id,),
    )
    conn.execute(
        "INSERT INTO department_majors (department_id, name) VALUES (?, 'شعبة 1')",
        (dept_id,),
    )
    conn.commit()
    conn.close()
    return db_path


def _client_with_role(app_fx, role):
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = role
        sess['username'] = role
        sess['department_id'] = None
        sess['_csrf_token'] = 't'
    return c


# ── the dashboard itself ──────────────────────────────────────────

def test_dean_overview_renders_all_sections(app_fx, overview_db):
    """اللوحة الشاملة تعرض كل نطاقات المنصة ولا تفشل على قاعدة بيانات فارغة."""
    r = _client_with_role(app_fx, 'dean').get('/')
    body = r.get_data(as_text=True)

    assert r.status_code == 200
    for section in OVERVIEW_SECTIONS:
        assert section in body, f'قسم مفقود في اللوحة: {section}'


def test_dean_overview_declares_read_only(app_fx, overview_db):
    """اللوحة تُعلن صراحةً أنها للقراءة فقط، فلا يُوهم المستخدم بوجود كتابة."""
    body = _client_with_role(app_fx, 'dean').get('/').get_data(as_text=True)
    assert 'قراءة فقط' in body


def test_dean_overview_has_no_write_forms(app_fx, overview_db):
    """لا يوجد أي نموذج كتابة في اللوحة الشاملة (الروابط كلها GET)."""
    import re
    body = _client_with_role(app_fx, 'dean').get('/').get_data(as_text=True)
    actions = {
        m for m in re.findall(r'<form[^>]*\baction="([^"]+)"', body)
        if m not in ('/logout',)
    }
    assert actions == set(), f'نماذج كتابة في اللوحة: {actions}'


def test_dean_overview_directory_links_resolve(app_fx, overview_db):
    """كل رابط في دليل صفحات المنصة موجود فعلاً ويطابق endpoint مسجّلاً."""
    body = _client_with_role(app_fx, 'dean').get('/').get_data(as_text=True)

    import re
    hrefs = set(re.findall(r'href="(/[^"#?]*)"', body))
    for path in DEAN_DIRECTORY_PATHS:
        assert path in hrefs, f'رابط مفقود من الدليل: {path}'

    # كل رابط الدليل يجب أن يقابل قاعدة في url_map (لا رابط ميّت)
    rules = {r.rule for r in app_fx.url_map.iter_rules()}
    for path in DEAN_DIRECTORY_PATHS:
        assert any(path == rule or path.startswith(rule) for rule in rules), \
            f'رابط لا يقابل أي endpoint: {path}'


def test_dean_overview_service_returns_every_domain(app_fx, overview_db):
    """خدمة اللوحة تُعيد نطاقاتها السبعة كلها على قاعدة بيانات شبه فارغة."""
    from services.dashboard_service import get_dean_overview_data
    conn = connect(str(overview_db))
    try:
        data = get_dean_overview_data(conn, show=8)
    finally:
        conn.close()

    assert set(data) == {
        'identity', 'academic', 'scheduling', 'examinations',
        'communication', 'teaching_load', 'auditing',
    }
    assert isinstance(data['teaching_load'], list)


# ── read-only enforcement on the pages the dean can reach ────────

def test_dean_departments_page_hides_create_and_delete(app_fx, overview_db):
    """صفحة الأقسام للقراءة فقط: بلا نموذج إنشاء وبلا أزرار حذف."""
    body = _client_with_role(app_fx, 'dean').get('/departments').get_data(as_text=True)

    assert 'name="majors"' not in body          # create form
    assert '/departments/create' not in body
    assert '/delete' not in body


def test_dean_departments_ajax_table_hides_delete(app_fx, overview_db):
    """جدول الأقسام عبر AJAX لا يسرّب زر حذف الشعبة (كان BuildError سابقاً)."""
    r = _client_with_role(app_fx, 'dean').get(
        '/departments', headers={'X-Requested-With': 'XMLHttpRequest'}
    )
    body = r.get_data(as_text=True)

    assert r.status_code == 200
    assert 'شعبة 1' in body                     # data still visible
    assert 'delete-major-btn' not in body       # but no write control
    assert 'department_delete_major' not in body  # and no bad url_for


def test_exam_still_gets_department_write_controls(app_fx, overview_db):
    """من يملك departments.manage ما زال يرى الإنشاء والحذف (لا انحدار)."""
    body = _client_with_role(app_fx, 'exam').get('/departments').get_data(as_text=True)

    assert 'name="majors"' in body
    assert '/departments/create' in body
    assert '/departments/delete/' in body


def test_exam_department_create_form_survives_validation_error(app_fx, overview_db):
    """عند خطأ التحقق تُعاد الصفحة ومعها النموذج (can_manage لا يُفقد)."""
    c = _client_with_role(app_fx, 'exam')
    r = c.post('/departments/create', data={
        '_csrf_token': 't', 'name': 'قسم الحاسوب', 'semesters': 7, 'majors': 8,
    })
    body = r.get_data(as_text=True)

    assert r.status_code == 200
    assert 'name="majors"' in body


def test_dean_timetable_popup_has_no_edit_actions(app_fx, overview_db):
    """نافذة تفاصيل المحاضرة لا تعرض تعديل/تكرار/حذف أمام العميد."""
    body = _client_with_role(app_fx, 'dean').get('/timetable').get_data(as_text=True)

    assert 'popupActions' in body               # the bar is still there
    assert 'openEdit(window.__ttPopupId())' not in body
    assert 'duplicateEntry(window.__ttPopupId())' not in body
    assert 'deleteEntry(window.__ttPopupId())' not in body
    assert 'addLecBtn' not in body


def test_hod_timetable_keeps_edit_actions(app_fx, overview_db):
    """من يملك timetable.edit ما زال يرى أدوات الجدولة (لا انحدار)."""
    body = _client_with_role(app_fx, 'head_of_department').get(
        '/timetable'
    ).get_data(as_text=True)

    assert 'openEdit(window.__ttPopupId())' in body
    assert 'addLecBtn' in body


def test_dean_teacher_schedule_hides_upload_form(app_fx, overview_db):
    """صفحة جدول الأستاذ بلا نموذج رفع (uploads.view) مع بقاء قائمة الملفات."""
    body = _client_with_role(app_fx, 'dean').get(
        '/timetable/teachers-schedule'
    ).get_data(as_text=True)

    assert 'data-upload-limit' not in body
    assert 'uploadSection' in body


def test_teacher_teacher_schedule_keeps_upload_form(app_fx, overview_db):
    """المدرس يملك uploads.view فيبقى نموذج الرفع (لا انحدار)."""
    body = _client_with_role(app_fx, 'teacher').get(
        '/timetable/teachers-schedule'
    ).get_data(as_text=True)

    assert 'data-upload-limit' in body


def test_dean_cannot_post_department_writes(app_fx, overview_db):
    """الحماية على مستوى الخادم: الإنشاء والحذف مرفوضان للعميد."""
    c = _client_with_role(app_fx, 'dean')

    assert c.post('/departments/create', data={
        '_csrf_token': 't', 'name': 'قسم جديد', 'semesters': 7, 'majors': 8,
    }).status_code == 302
    assert c.post('/departments/delete/1', data={'_csrf_token': 't'}).status_code == 302


def test_dean_cannot_create_room(app_fx, overview_db):
    """rooms_list يقبل POST تحت rooms.view، لكن يجب أن يرفض rooms.manage مفقوداً."""
    c = _client_with_role(app_fx, 'dean')
    r = c.post('/rooms', data={
        '_csrf_token': 't', 'name': 'قاعة جديدة', 'quantity': 1, 'capacity': 20,
    })
    assert r.status_code == 302  # رُفضت المحاولة وأُعيد التوجيه بدل الإنشاء

    conn = connect(str(overview_db))
    try:
        created = conn.execute(
            "SELECT COUNT(*) AS c FROM rooms WHERE name='قاعة جديدة'"
        ).fetchone()['c']
    finally:
        conn.close()
    assert created == 0


# ── navigation ───────────────────────────────────────────────────

def test_dean_nav_exposes_departments_and_rooms(app_fx, overview_db):
    """العميد يرى الأقسام والقاعات في الشريط الجانبي (قراءة فقط)."""
    body = _client_with_role(app_fx, 'dean').get('/courses').get_data(as_text=True)

    assert 'الأقسام' in body
    assert 'القاعات' in body


def test_teacher_nav_still_excludes_departments_and_rooms(app_fx, overview_db):
    """المدرس لا يملك departments.view/rooms.view فلا يظهر له الرابطان."""
    body = _client_with_role(app_fx, 'teacher').get('/timetable').get_data(as_text=True)

    assert '/departments' not in body
    assert '/rooms' not in body
