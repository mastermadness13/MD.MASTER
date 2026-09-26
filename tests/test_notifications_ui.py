"""Notification bell: API + topbar UI.

The write side already existed (10 call sites across hod_pages, teacher_pages
and timetable create rows in the ``notifications`` table) and the read API
already existed in api_routes/notifications.py, but nothing ever rendered the
bell, so users generated notifications they could not see. These tests pin the
read path and the markup that surfaces it.
"""

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema
from tests.test_bottom_nav import _client_for, _user_id


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'notif.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) "
        "VALUES ('office_manager', 'x', 'faculty_affairs', 'مدير مكتب')"
    )
    conn.commit()
    conn.close()
    return str(db_path)


@pytest.fixture
def client(app_fx, db_fx):
    return _client_for(
        app_fx, _user_id(db_fx, 'office_manager'), 'faculty_affairs', 'office_manager'
    )


def _uid(db_path, username='office_manager'):
    conn = connect(db_path)
    row = conn.execute(
        'SELECT id FROM users WHERE username=?', (username,)
    ).fetchone()
    conn.close()
    return row['id']


def test_list_endpoint_requires_authentication(app_fx):
    anon = app_fx.test_client()
    assert anon.get('/api/notifications').status_code == 401


def test_list_endpoint_returns_notifications_and_unread_count(client, db_fx):
    from services import notification_service

    db = connect(db_fx)
    uid = _uid(db_fx)
    notification_service.create_notification(
        db, uid, 'تمت الموافقة', 'تمت الموافقة على طلبك', 'success'
    )
    notification_service.create_notification(
        db, uid, 'تنبيه', 'تذكير بموعد الامتحان', 'warning'
    )
    db.close()

    resp = client.get('/api/notifications')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['ok'] is True
    # Every api_routes response is wrapped in {ok, data}; unwrap it the same
    # way static/js/notifications.js does.
    payload = body['data']
    assert payload['unread_count'] == 2
    assert len(payload['notifications']) == 2
    titles = {n['title'] for n in payload['notifications']}
    assert 'تمت الموافقة' in titles


def test_mark_all_read_clears_the_unread_count(client, db_fx):
    from services import notification_service

    db = connect(db_fx)
    notification_service.create_notification(
        db, _uid(db_fx), 'عنوان', 'نص', 'info'
    )
    db.close()

    unread = client.get('/api/notifications').get_json()['data']['unread_count']
    assert unread == 1

    with client.session_transaction() as sess:
        sess['_csrf_token'] = 't'
    resp = client.post(
        '/api/notifications/read',
        headers={'X-CSRFToken': 't'},
    )
    assert resp.status_code == 200
    assert client.get('/api/notifications').get_json()['data']['unread_count'] == 0


def test_mark_all_read_requires_csrf(client):
    """The write path must not be reachable without a token, even with a
    valid session. The API answers 403 JSON when the caller asks for JSON and
    falls back to a redirect otherwise, so both paths are pinned here."""
    api_resp = client.post(
        '/api/notifications/read', headers={'Accept': 'application/json'}
    )
    assert api_resp.status_code == 403
    assert api_resp.get_json()['ok'] is False

    browser_resp = client.post('/api/notifications/read')
    assert browser_resp.status_code == 302


def test_mark_all_read_client_asks_for_json_before_clearing_the_ui(client):
    """Without an Accept of application/json the CSRF failure path answers
    with a 302 that fetch follows, so the client would report success and
    clear the badge even though nothing was written."""
    with open('static/js/notifications.js', encoding='utf-8') as fh:
        js = fh.read()
    mark_all = js[js.index('function markAllRead'): js.index('function escapeHtml')]
    assert "'Accept': 'application/json'" in mark_all, (
        'markAllRead must request JSON or it cannot detect a CSRF rejection'
    )
    assert 'if (!body || !body.ok) return;' in mark_all, (
        'the UI must not clear the badge before the server confirms'
    )


def test_notifications_are_scoped_to_the_signed_in_user(client, db_fx):
    """A user must never see another user's rows."""
    from services import notification_service

    db = connect(db_fx)
    db.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) "
        "VALUES ('someone_else', 'x', 'teacher', 'مدرس آخر')"
    )
    db.commit()
    other = db.execute(
        "SELECT id FROM users WHERE username='someone_else'"
    ).fetchone()['id']
    notification_service.create_notification(
        db, other, 'خاص بغيرك', 'يجب ألا يظهر', 'info'
    )
    db.close()

    payload = client.get('/api/notifications').get_json()['data']
    assert payload['notifications'] == []
    assert payload['unread_count'] == 0


def test_bell_renders_in_the_topbar_with_a_disclosure(client):
    body = client.get('/timetable/department').get_data(as_text=True)
    assert 'id="notifBellBtn"' in body, 'the bell is still missing'
    assert 'id="notifMenu"' in body
    assert 'id="notifList"' in body, (
        'notifications.js renders into #notifList; without it the fetch runs '
        'but nothing is displayed'
    )
    assert 'id="notifBadge"' in body
    assert 'id="markAllRead"' in body

    btn = body[body.index('id="notifBellBtn"') - 200: body.index('id="notifBellBtn"') + 200]
    assert 'aria-expanded="false"' in btn, 'the disclosure state is not announced'
    assert 'aria-controls="notifMenu"' in btn


def test_notifications_script_is_loaded(client):
    body = client.get('/timetable/department').get_data(as_text=True)
    assert 'js/notifications.js' in body, (
        'notifications.js exists and has CSS, but was never included'
    )


def test_bell_is_gated_on_the_permission_the_api_enforces():
    """The API is gated on dashboard.view. Rendering the button for a role
    without it would only produce a 403 on first poll."""
    with open('templates/shared/layouts/base.html', encoding='utf-8') as fh:
        src = fh.read()
    at = src.index('id="notifBellBtn"')
    window = src[max(0, at - 600):at]
    assert "has_permission('dashboard.view')" in window

    with open('api_routes/notifications.py', encoding='utf-8') as fh:
        api_src = fh.read()
    assert "api_permission_required('dashboard.view')" in api_src, (
        'the API permission changed; keep the template gate in sync'
    )


def test_menu_can_be_opened_by_click_not_hover_only():
    """Hover-only menus are unusable on touch and unreachable by keyboard."""
    with open('static/css/layout/topbar.css', encoding='utf-8') as fh:
        css = fh.read()
    assert '.notif-dropdown.open .notif-menu' in css

    with open('static/js/notifications.js', encoding='utf-8') as fh:
        js = fh.read()
    assert "addEventListener('click'" in js
    assert "aria-expanded" in js
    assert "'Escape'" in js, 'Escape should close the menu'


def test_badge_count_is_exposed_to_assistive_tech():
    """The badge is a bare number, so the count must reach screen readers
    through the button's accessible name."""
    with open('static/js/notifications.js', encoding='utf-8') as fh:
        js = fh.read()
    assert 'aria-hidden' in js
    assert 'aria-label' in js
    assert 'aria-expanded' in js


def test_client_unwraps_the_api_envelope():
    """api_routes wraps every payload as {ok, data}. Reading the top level
    silently yields an empty list, so the client must unwrap .data."""
    with open('static/js/notifications.js', encoding='utf-8') as fh:
        js = fh.read()
    assert 'body.ok' in js, 'the client never checks the ok flag'
    assert 'body.data' in js or 'data || {}' in js, (
        'the client reads the top level instead of the data envelope'
    )
