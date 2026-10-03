"""Tests for the server-rendered PDF downloads.

Printouts used to go through the browser, which made the result depend on the
user's printer settings (page size, margins, scale) and produced a second blank
page. These tests pin the replacement contract: a real PDF attachment, one page
for single-document sheets, all rows present, and no app chrome in the output.
"""

import io
import os
import re
import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema
from services import pdf_service


# Kept before any monkeypatching so tests that stub the renderer can still
# reach the real one.
REAL_RENDER_PDF = pdf_service.render_pdf


def _pdf_pages(data):
    """Page count without requiring a PDF library in requirements.txt."""
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - optional dev dependency
        return len(re.findall(rb'/Type\s*/Page[^s]', data))
    with pymupdf.open(stream=data, filetype='pdf') as doc:
        return doc.page_count


def _pdf_text(data):
    import pymupdf
    with pymupdf.open(stream=data, filetype='pdf') as doc:
        return '\n'.join(page.get_text() for page in doc)


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'pdf_download.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) "
        "VALUES ('hod', 'x', 'head_of_department', 'رئيس قسم')")
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) "
        "VALUES ('rnd', 'x', 'research_development', 'بحث وتطوير')")
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) "
        "VALUES ('dean', 'x', 'dean', 'العميد')")
    conn.execute(
        "INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, "
        "has_sections, type) VALUES ('قسم الحاسوب', 8, 8, 0, 1, 'academic')")
    dept_id = conn.execute(
        "SELECT id FROM departments WHERE name='قسم الحاسوب'").fetchone()['id']
    conn.execute(
        'INSERT INTO timetable_versions (department_id, semester, '
        "semester_code, status) VALUES (?, 2, 'fall_2026', 'active')", (dept_id,))
    conn.commit()
    conn.close()
    return db_path


def _dept_id(name='قسم الحاسوب'):
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        'SELECT id FROM departments WHERE name=?', (name,)).fetchone()
    conn.close()
    return row['id']


def _session(app_fx, db_fx, username, **extra):
    """Log a client in as *username*, exactly the way the login view does.

    The ids are resolved from the rows rather than hard-coded: ``ensure_schema``
    seeds the bootstrap ``office_manager`` account first, so assuming id 1 is
    this user authenticates as the wrong account.
    """
    from tests.harness import CSRF_TOKEN, session_for
    client = app_fx.test_client()
    session_for(client, str(db_fx), username, csrf_token=CSRF_TOKEN, extra=extra)
    return client


@pytest.fixture
def client(app_fx, db_fx):
    return _session(app_fx, db_fx, 'rnd',
                    department_id=_dept_id(), hod_department_id=_dept_id())


@pytest.fixture
def dean_client(app_fx, db_fx):
    return _session(app_fx, db_fx, 'dean', department_id=None)


# ── pdf_service unit tests ─────────────────────────────────────────

def test_browser_discovery_is_cached(app_fx):
    pdf_service.reset_browser_cache()
    try:
        first = pdf_service.browser_path()
        assert first == pdf_service.browser_path()
        assert first is None or os.path.isfile(first)
    finally:
        pdf_service.reset_browser_cache()


def test_render_pdf_reports_missing_browser(app_fx, monkeypatch):
    monkeypatch.setattr(pdf_service, 'browser_path', lambda: None)
    with pytest.raises(pdf_service.PdfUnavailableError):
        pdf_service.render_pdf('<html></html>')


def test_inline_static_images_ignores_remote_and_traversal(app_fx):
    root = os.path.join('static')
    html = ('<img src="/static/dist/app.css"><img src="/static/../../etc/passwd">'
            '<img src="https://example.com/x.png"><img src="data:image/png;base64,AA">')
    out = pdf_service.inline_static_images(html, root)
    assert 'src="https://example.com/x.png"' in out
    assert 'src="data:image/png;base64,AA"' in out
    # A path escaping the static root is left untouched, never inlined.
    assert 'src="/static/../../etc/passwd"' in out
    assert '/etc/passwd" data:' not in out


def test_content_disposition_is_rfc5987(app_fx):
    with app_fx.test_request_context('/'):
        header = pdf_service._content_disposition('نموذج معدل الأداء.pdf')
    assert header.startswith('attachment;')
    assert "filename*=UTF-8''" in header
    assert re.search(r'filename="[\x20-\x7e]*"', header)


def test_content_disposition_strips_path_separators(app_fx):
    with app_fx.test_request_context('/'):
        header = pdf_service._content_disposition('../../etc/passwd\r\nX: y')
    assert '\r' not in header and '\n' not in header
    assert '/' not in header.split("filename*=UTF-8''")[0].split('filename="')[1]


# ── timetable / exam downloads ─────────────────────────────────────

def test_department_timetable_pdf_is_a_single_page(client):
    resp = client.get('/print/timetables/department.pdf',
                      query_string={'department_id': _dept_id(), 'semester': 2})
    assert resp.status_code == 200
    assert resp.mimetype == 'application/pdf'
    assert 'attachment' in resp.headers['Content-Disposition']
    assert resp.data.startswith(b'%PDF')
    assert _pdf_pages(resp.data) == 1


def test_department_timetable_pdf_matches_html_route_payload(client):
    params = {'department_id': _dept_id(), 'semester': 2}
    pdf = client.get('/print/timetables/department.pdf', query_string=params)
    html = client.get('/print/timetables/department', query_string=params)
    assert pdf.status_code == html.status_code == 200
    assert _pdf_pages(pdf.data) == 1


def test_department_timetable_pdf_redirects_like_html_route(client):
    resp = client.get('/print/timetables/department.pdf')
    assert resp.status_code in (302, 303)
    assert '/timetable/department' in resp.headers['Location']


def test_teacher_timetable_pdf_is_a_single_page(client):
    resp = client.get('/print/timetables/teacher.pdf',
                      query_string={'teacher_id': 1, 'semester': 2})
    assert resp.status_code == 200
    assert resp.data.startswith(b'%PDF')
    assert _pdf_pages(resp.data) == 1


def test_all_timetables_pdf_is_a_valid_pdf(client):
    resp = client.get('/print/timetables/all.pdf')
    assert resp.status_code == 200
    assert resp.data.startswith(b'%PDF')
    assert _pdf_pages(resp.data) >= 1


def test_exams_schedule_pdf_is_a_pdf(dean_client):
    resp = dean_client.get('/print/exams/schedule.pdf')
    assert resp.status_code == 200
    assert resp.data.startswith(b'%PDF')
    assert 'attachment' in resp.headers['Content-Disposition']


def test_exams_schedule_pdf_keeps_the_same_permission_gate(client):
    # research_development holds neither exams.view nor timetable access here,
    # so the PDF route must refuse exactly like the HTML route does.
    denied = client.get('/print/exams/schedule.pdf')
    html = client.get('/print/exams/schedule')
    assert denied.status_code == html.status_code


def test_pdf_downloads_require_login(app_fx, db_fx):
    anonymous = app_fx.test_client()
    for path in ('/print/exams/schedule.pdf',
                 '/print/timetables/department.pdf',
                 '/print/timetables/all.pdf'):
        resp = anonymous.get(path)
        assert resp.status_code in (302, 303), path
        assert '/login' in resp.headers['Location'], path


# ── the faculty performance form ───────────────────────────────────

def _affairs_client(app_fx, db_fx):
    from tests.harness import login_as
    return login_as(app_fx, db_fx, 'faculty_affairs')


def test_performance_form_downloads_one_pdf_page(app_fx, db_fx):
    """The URL the preview page links to is now a file, not a second page."""
    from tests.harness import _seed_all
    from tests.harness import build_schema

    conn = connect(str(db_fx))
    ids = _seed_all(conn, str(db_fx))
    conn.commit()
    conn.close()

    resp = _affairs_client(app_fx, db_fx).get(
        '/faculty-performance/print/%d?year=2026/2027&semester=1' % ids['teacher_id']
    )

    assert resp.status_code == 200
    assert resp.mimetype == 'application/pdf'
    assert resp.data.startswith(b'%PDF')
    assert 'attachment' in resp.headers['Content-Disposition']
    assert _pdf_pages(resp.data) == 1, 'the form spilled onto a second page'


def test_dean_can_preview_and_print_performance_form_without_edit_access(
        app_fx, db_fx, monkeypatch):
    from page_routes import faculty_performance as performance_routes
    from services import faculty_performance_service as fps
    from tests.harness import _seed_all, login_as

    conn = connect(str(db_fx))
    ids = _seed_all(conn, str(db_fx))
    conn.close()

    monkeypatch.setattr(
        fps,
        'get_performance_form_data',
        lambda *_args, **_kwargs: {'header': {'teacher_name': 'أستاذ الاختبار'},
                                   'leaves': []},
    )
    monkeypatch.setattr(
        fps,
        'get_select_data',
        lambda _db: {
            'research_types': [], 'admin_task_types': [],
            'admin_task_hours': [], 'leave_types': [],
        },
    )
    monkeypatch.setattr(
        performance_routes, '_leaves_out_of_semester_warning',
        lambda *_args: None,
    )
    monkeypatch.setattr(
        performance_routes, 'render_template',
        lambda *_args, **_kwargs: 'preview rendered',
    )
    monkeypatch.setattr(
        pdf_service, 'template_pdf_response',
        lambda *_args, **_kwargs: ('pdf rendered', 200),
    )

    dean = login_as(app_fx, str(db_fx), 'dean')
    preview = dean.get(
        f"/faculty-performance/preview/{ids['teacher_id']}?year=fall_2026&semester=1"
    )
    printed = dean.get(
        f"/faculty-performance/print/{ids['teacher_id']}?year=fall_2026&semester=1"
    )
    edit = dean.get(
        f"/faculty-performance/edit-research/{ids['teacher_id']}?year=fall_2026&semester=1"
    )

    assert preview.status_code == 200
    assert printed.status_code == 200
    assert edit.status_code in (302, 403)


def test_performance_form_pdf_is_landscape_a4(app_fx, db_fx):
    from tests.harness import _seed_all

    conn = connect(str(db_fx))
    ids = _seed_all(conn, str(db_fx))
    conn.commit()
    conn.close()

    resp = _affairs_client(app_fx, db_fx).get(
        '/faculty-performance/print/%d?year=2026/2027&semester=1' % ids['teacher_id']
    )
    boxes = {m.decode() for m in re.findall(rb'/MediaBox\s*\[([^\]]*)\]', resp.data)}
    assert boxes, 'no MediaBox: the paper size is undefined'
    width, height = (float(v) for v in boxes.pop().split()[2:])
    assert width > height, 'the performance form must stay landscape'


def test_the_fit_prevents_overflow_instead_of_clipping(app_fx, db_fx):
    """`overflow: hidden` pins the page count to one even when the fit fails,
    which would quietly delete the bottom of the form. Prove the fit really
    makes the content fit by turning clipping off: a single page then can only
    happen if the scaling worked.
    """
    from tests.harness import _seed_all

    conn = connect(str(db_fx))
    ids = _seed_all(conn, str(db_fx))
    conn.commit()
    conn.close()

    rendered = []
    real_render = pdf_service.render_pdf
    try:
        pdf_service.render_pdf = lambda html, **kw: rendered.append(html) or b'%PDF-1.4\n%%EOF'
        _affairs_client(app_fx, db_fx).get(
            '/faculty-performance/print/%d?year=2026/2027&semester=1'
            % ids['teacher_id']
        )
    finally:
        pdf_service.render_pdf = real_render

    unclipped = rendered[-1].replace('overflow: hidden;', 'overflow: visible;')
    assert unclipped != rendered[-1], 'could not disable clipping for this check'

    with app_fx.test_request_context('/'):
        body = REAL_RENDER_PDF(
            pdf_service.inline_static_images(unclipped, pdf_service._static_root())
        )

    assert _pdf_pages(body) == 1, (
        'the form only stayed on one page because it was being clipped; rows '
        'are being lost'
    )


def test_pdf_templates_do_not_pull_in_the_app_shell():
    """PDFs render from a bare shell, so sidebar, bottom nav, flash messages and
    print buttons cannot reach the page at all."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ('performance', 'timetable_department', 'timetable_teacher',
                 'timetable_all', 'exams_schedule'):
        with open(os.path.join(root, 'templates', 'print', 'pdf',
                               name + '.html'), encoding='utf-8') as fh:
            text = fh.read()
        assert "extends 'print/pdf/_base.html'" in text, name
        for banned in ("extends 'base.html'", 'bottom_nav', 'sidebar',
                       'window.print', '<button'):
            assert banned not in text, '%s.html pulls in %s' % (name, banned)