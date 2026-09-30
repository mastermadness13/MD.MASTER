"""A read-only administrative assignment must not be writable through any door.

The dean can attach a page to an assignment and mark it ``view`` = read-only.
``TASK_PAGES`` lists, per page, the write permissions that make up the
"control" side of that page, and ``has_permission`` must refuse them for the
holder -- on the HTML page *and* on the JSON API that backs the same page,
because the SPA writes through ``/api/*``.

Two defects are pinned here:

1. ``_is_demoted_write`` compared ``request.blueprint`` against the page's
   single HTML blueprint, so every ``api_rooms`` / ``api_courses`` /
   ``api_teachers`` / ``api_departments`` / ``api_timetable`` / ``api_exams``
   write endpoint sailed straight through.  Verified end to end before the
   fix: the HTML door answered 403 while ``POST /api/rooms`` answered ``201``
   and the row existed afterwards.
2. ``exams.department_schedule`` gates five exam-schedule writes but was not
   declared a write of the exams page, so that door was open on *every*
   surface.

The write URLs are derived from the live URL map rather than hand-written, so
these tests describe "every write door of this page" instead of a list that
can fall behind the routes.
"""

import re

import pytest

import flask_db
from core.constants.permissions import ROLE_PERMISSIONS
from core.constants.task_pages import TASK_PAGES
from database.connection import connect
from database.schema import ensure_schema

XHR = {'X-Requested-With': 'XMLHttpRequest'}
WRITE_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})

# /     /     >---- (صفحة، دور): الدور يملك صلاحية الكتابة أصلاً، وإلا صار
# /     /     >---- الرفض بلا معنى (نرفض لأن الدور لا يملكها، لا لأن التكليف
# /     /     >---- للقراءة). مبنية على بيانات ROLE_PERMISSIONS لا على تخمين.
WRITE_ROLE_CASES = [
    (page_key, role)
    for page_key, page in TASK_PAGES.items()
    for role, perms in ROLE_PERMISSIONS.items()
    if page['write_permissions']
    and set(page['write_permissions']) <= set(perms)
]


def _write_routes(app, page):
    """(methods, url rule, permission) for every write door of *page*."""
    declared = set(page['write_permissions'])
    routes = []
    with app.app_context():
        from security.authorization import _write_blueprints

        blueprints = set()
        for perm in declared:
            blueprints |= _write_blueprints(perm)

    for rule in app.url_map.iter_rules():
        if rule.endpoint.rsplit('.', 1)[0] not in blueprints:
            continue
        view_func = app.view_functions.get(rule.endpoint)
        if view_func is None:
            continue
        if getattr(view_func, '_required_permission', None) not in declared:
            continue
        methods = (rule.methods or set()) & WRITE_METHODS
        if methods:
            routes.append((methods, rule, view_func._required_permission))
    return routes


_CONVERTER_VALUES = {
    'int': '1',
    'float': '1.0',
    'path': 'x',
    'string': 'x',
    'any': 'x',
    'uuid': '00000000-0000-0000-0000-000000000001',
    'default': 'x',
}
_CAST_RE = re.compile(r'<([^:>]+)(?::([^>]*))?>')


def _concrete(rule):
    """Fill *rule*'s placeholders so the request actually resolves.

    Derived from the rule's own converters rather than a hand-kept list, so a
    route that gains a new ``<int:foo>`` keeps resolving here.
    """
    def fill(match):
        kind, _type = match.group(1), match.group(2)
        if kind in ('int', 'float'):
            return _CONVERTER_VALUES[kind]
        return _CONVERTER_VALUES.get(kind, 'x')

    return _CAST_RE.sub(fill, rule.rule)


def _build_db(tmp_path, monkeypatch, name):
    db_path = tmp_path / name
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as schema_file:
        conn.executescript(schema_file.read())
    ensure_schema(conn)
    return conn


def _attach_page(conn, role, page_key, mode):
    """Point the catalogue row for *role* at *page_key* in *mode*."""
    conn.execute(
        'UPDATE admin_assignment_types '
        'SET internal_code = ?, is_protected_role = 1, page_key = ?, '
        '    page_access_mode = ? '
        'WHERE id = (SELECT MIN(id) FROM admin_assignment_types)',
        (role, page_key, mode),
    )


def _make_user(conn, role, username):
    conn.execute(
        'INSERT INTO users (username, password, role, label) VALUES (?, ?, ?, ?)',
        (username, 'x', role, role),
    )
    return conn.execute(
        'SELECT id FROM users WHERE username = ?', (username,)
    ).fetchone()['id']


@pytest.fixture
def assignment(tmp_path, monkeypatch, app_fx):
    """Factory: a holder of *role* whose assignment opens *page_key*.

    ``mode`` is 'view' (read-only) or 'edit' (full control).
    """
    conn = _build_db(tmp_path, monkeypatch, 'task-page-readonly.db')

    def factory(page_key, role, username, mode='view'):
        user_id = _make_user(conn, role, username)
        _attach_page(conn, role, page_key, mode)
        conn.commit()
        client = app_fx.test_client()
        with client.session_transaction() as session:
            session['user_id'] = user_id
            session['role'] = role
            session['roles'] = [role]
            session['username'] = username
            session['_csrf_token'] = 'test-token'
        return client

    yield factory
    conn.close()


# ── the catalogue ───────────────────────────────────────────────────

def test_no_write_permission_is_shared_by_two_pages():
    """The demotion keys on (page write permission, gating blueprint). If two
    pages claimed the same write, attaching either read-only would also
    silence the other's controls. Fail here rather than ship that."""
    owners = {}
    for page_key, page in TASK_PAGES.items():
        for perm in page['write_permissions']:
            owners.setdefault(perm, []).append(page_key)
    shared = {p: pages for p, pages in owners.items() if len(pages) > 1}
    assert not shared, 'write permissions claimed by more than one page: %s' % shared


def test_no_write_permission_is_unreachable():
    """A write permission no role holds could never be bypassed, and would
    make a 'read-only' assignment meaningless for that control."""
    unreachable = [
        (page_key, perm)
        for page_key, page in TASK_PAGES.items()
        for perm in page['write_permissions']
        if not any(perm in perms for perms in ROLE_PERMISSIONS.values())
    ]
    assert not unreachable, 'write permissions no role holds: %s' % unreachable


# /     /     >---- صلاحيات مشروعة لمشاهِد لا تكتب بيانات: إبلاغ خطأ في
# /     /     >---- الجدول، ومعاينة طباعة. مسموحة لأصحاب «عرض فقط» عمداً،
# /     /     >---- فهي لا تغيّر سجلاً. أي إذن آخر غير مُعلن = باب مفتوح.
VIEWER_POST_EXEMPTIONS = {
    # The report-a-error form is how a viewer tells the office the published
    # timetable is wrong; it creates no record.
    'timetable.view',
    # Print preview renders a document and persists nothing.
    'faculty_performance.view',
    # rooms_list answers GET and POST behind one route, so the decorator has to
    # name rooms.view; the handler re-checks rooms.manage on the POST branch
    # (page_routes/classrooms.py computes can_manage from has_permission), so
    # the write is closed at the same place the demotion closes it.
    'rooms.view',
}


@pytest.mark.parametrize('page_key', sorted(TASK_PAGES))
def test_every_write_door_of_a_page_is_declared_a_write(app_fx, page_key):
    """Completeness: no un-declared write door may exist inside the page's
    permission family (namespaced by the page key or its endpoint blueprint).

    This is the guard that would have caught ``exams.department_schedule``
    being left out of the exams page.
    """
    page = TASK_PAGES[page_key]
    prefixes = {page_key, page['endpoint'].split('.')[0]}
    declared = set(page['write_permissions']) | VIEWER_POST_EXEMPTIONS

    leaked = set()
    for rule in app_fx.url_map.iter_rules():
        view_func = app_fx.view_functions.get(rule.endpoint)
        if view_func is None:
            continue
        perm = getattr(view_func, '_required_permission', None)
        if not perm or perm in declared:
            continue
        if not any(perm.startswith(p + '.') for p in prefixes):
            continue
        if (rule.methods or set()) & WRITE_METHODS:
            leaked.add((perm, rule.endpoint))

    assert not leaked, (
        'write doors inside the %s family that read-only mode would not '
        'close: %s' % (page_key, sorted(leaked))
    )


# ── the demotion map ────────────────────────────────────────────────

@pytest.mark.parametrize('page_key,role', WRITE_ROLE_CASES)
def test_demotion_reaches_both_doors_not_just_the_html_page(app_fx, page_key, role):
    """Derived from the URL map, so a route added later is covered without a
    list being maintained by hand."""
    from security.authorization import _write_blueprints

    with app_fx.app_context():
        blueprints = set()
        for perm in TASK_PAGES[page_key]['write_permissions']:
            blueprints |= _write_blueprints(perm)

    assert blueprints, 'no guarded endpoint found for %s' % page_key

    api_twins = {
        rule.endpoint.split('.')[0]
        for rule in app_fx.url_map.iter_rules()
        if rule.endpoint.startswith('api_')
    }
    expected_twin = 'api_%s' % page_key
    if expected_twin in api_twins:
        assert expected_twin in blueprints, (
            'the /api twin of the %s page is not covered by the demotion'
            % page_key
        )


def test_demotion_map_is_keyed_by_permission_not_by_page(app_fx):
    """The map must describe what a permission guards, so it cannot name one
    blueprint and miss its twin."""
    with app_fx.app_context():
        from security.authorization import _write_blueprints

        rooms_writes = _write_blueprints('rooms.manage')
        rooms_reads = _write_blueprints('rooms.view')
        # `classrooms.rooms_list` is gated by rooms.view and accepts POST,
        # so the read map naming it is correct -- what must not happen is a
        # write permission silently mapping to nothing.
    assert 'api_rooms' in rooms_writes and 'classrooms' in rooms_writes
    assert rooms_reads


# ── behaviour over real HTTP, every door ────────────────────────────

@pytest.mark.parametrize('page_key,role', WRITE_ROLE_CASES)
def test_no_write_door_of_a_read_only_assignment_opens(assignment, app_fx, page_key, role):
    """The bypass itself, exhaustively: every write route the page declares
    must answer a refusal, not perform the write."""
    client = assignment(page_key, role, 'ro_' + page_key)
    routes = _write_routes(app_fx, TASK_PAGES[page_key])
    assert routes, 'no write route discovered for %s -- test is vacuous' % page_key

    for methods, rule, perm in routes:
        for method in methods:
            response = client.open(
                _concrete(rule),
                method=method,
                json={},
                headers={**XHR, 'X-CSRFToken': 'test-token'},
            )
            assert response.status_code == 403, (
                'read-only holder reached %s %s (%s) -> %s %s'
                % (method, rule.rule, perm, response.status_code,
                   response.get_data(as_text=True)[:160])
            )
            assert response.get_json()['ok'] is False


def test_a_refused_write_leaves_nothing_behind(assignment):
    """The strongest form: the row is absent afterwards, not just a 403."""
    client = assignment('rooms', 'faculty_affairs', 'ro_no_row')
    response = client.post(
        '/api/rooms',
        json={'name': 'قاعة الاختراق', 'code': 'X1', 'capacity': 5},
        headers={**XHR, 'X-CSRFToken': 'test-token'},
    )
    assert response.status_code == 403

    listing = client.get('/api/rooms', headers=XHR)
    assert 'قاعة الاختراق' not in listing.get_data(as_text=True)
    page = client.get('/rooms')
    assert 'قاعة الاختراق' not in page.get_data(as_text=True)


def test_read_only_holder_keeps_reading_the_attached_page(assignment):
    """Refusing writes must not cost the holder the page they were given."""
    client = assignment('rooms', 'faculty_affairs', 'ro_reads')
    assert client.get('/rooms').status_code == 200
    listing = client.get('/api/rooms', headers=XHR)
    assert listing.status_code == 200
    assert listing.get_json()['ok'] is True


def test_the_demotion_reaches_one_page_only(assignment):
    """The contract is a single page, not the whole account: permissions the
    holder was not assigned stay intact, so the rest of their account works."""
    from security.authorization import has_permission

    client = assignment('rooms', 'faculty_affairs', 'ro_scope')
    with client.application.test_request_context('/rooms'):
        from flask import session as flask_session

        flask_session['role'] = 'faculty_affairs'
        assert has_permission(['faculty_affairs'], 'rooms.manage') is False
        assert has_permission(
            ['faculty_affairs'], 'faculty_performance.edit_research'
        ) is True


def test_edit_mode_is_not_demoted_and_can_write(assignment):
    """'edit' means full control -- the demotion must not fire."""
    client = assignment('rooms', 'faculty_affairs', 'edit_rooms', mode='edit')
    response = client.post(
        '/api/rooms',
        json={'name': 'قاعة سليمة', 'code': 'OK1', 'capacity': 5},
        headers={**XHR, 'X-CSRFToken': 'test-token'},
    )
    assert response.status_code in (200, 201), response.get_data(as_text=True)[:200]
