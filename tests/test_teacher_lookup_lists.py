import json
import re
import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema


@pytest.fixture
def lookup_setup(tmp_path, monkeypatch, app_fx):
    db_path = tmp_path / 'lookup-lists.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as schema_file:
        conn.executescript(schema_file.read())
    ensure_schema(conn)
    conn.execute(
        "INSERT INTO users (username, password, role, label) "
        "VALUES ('wesam', 'x', 'dean', 'عميد الكلية')"
    )
    manager_id = conn.execute(
        "SELECT id FROM users WHERE username = 'wesam'"
    ).fetchone()['id']
    conn.execute(
        "INSERT INTO users (username, password, role, label) "
        "VALUES ('lookup_office', 'x', 'faculty_affairs', 'مدير المكتب')"
    )
    office_id = conn.execute(
        "SELECT id FROM users WHERE username = 'lookup_office'"
    ).fetchone()['id']
    conn.commit()
    conn.close()

    def client_for(user_id, role, username):
        client = app_fx.test_client()
        with client.session_transaction() as session:
            session['user_id'] = user_id
            session['role'] = role
            session['username'] = username
            session['_csrf_token'] = 'test-token'
        return client

    return db_path, client_for(manager_id, 'dean', 'wesam'), (
        client_for(office_id, 'faculty_affairs', 'lookup_office')
    )


def _post(client, category, action, **values):
    return client.post(
        '/teachers/lookup-lists',
        data={
            '_csrf_token': 'test-token',
            'category': category,
            'action': action,
            **values,
        },
        follow_redirects=True,
    )


def _ajax_post(client, category, action, **values):
    return client.post(
        '/teachers/lookup-lists',
        data={
            '_csrf_token': 'test-token',
            'category': category,
            'action': action,
            **values,
        },
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )


def _fetchone(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return dict(row) if row else None


def _flash_messages(response):
    body = response.get_data(as_text=True)
    match = re.search(
        r'window\.BASE_FLASH_BOOT = \{ messages: (\[.*?\]) \};', body
    )
    if not match:
        return []
    return [
        message for _category, message in json.loads(match.group(1))
    ]


def test_lookup_lists_belong_to_the_dean_alone(lookup_setup):
    """القوائم المرجعية للعميد وحده: المكتب يعدّل الأساتذة لا بنية التكليفات."""
    _, dean, office = lookup_setup

    assert dean.get('/teachers/lookup-lists').status_code == 200
    assert office.get('/teachers/lookup-lists').status_code == 302


def _assert_json_envelope(response, expected_status=None):
    """Assert *response* is JSON — never the HTML that breaks JSON.parse."""
    if expected_status is not None:
        assert response.status_code == expected_status
    content_type = (response.headers.get('Content-Type') or '').lower()
    body = response.get_data(as_text=True)
    assert 'application/json' in content_type, (
        f'expected JSON, got {content_type}: {body[:120]!r}'
    )
    assert not body.lstrip().lower().startswith(('<!doctype', '<html')), (
        f'HTML body served to a JSON caller: {body[:120]!r}'
    )
    return response.get_json()


def test_no_ajax_path_answers_with_html(lookup_setup):
    """Every AJAX answer must be JSON.

    ``abort(400)`` on toggle, a 400 on an unknown category and the
    delete-confirmation re-render each used to emit HTML, which the browser
    read as JSON and reported as ``Unexpected token '<'``.
    """
    db_path, manager, _ = lookup_setup
    conn = connect(str(db_path))
    rank_id = str(conn.execute(
        'SELECT id FROM academic_ranks ORDER BY id LIMIT 1'
    ).fetchone()['id'])
    linked_rank_id = str(conn.execute(
        'SELECT rank_id FROM rank_rules WHERE rank_id IS NOT NULL LIMIT 1'
    ).fetchone()['rank_id'])
    conn.close()

    _assert_json_envelope(
        _ajax_post(manager, 'academic_rank', 'toggle', id=rank_id), 400
    )
    # 400 لا 404: الصفحة موجودة، والقيمة وحدها غير معروفة — و404 يجعل
    # المستخدم يظن أن الصفحة حُذفت، لا أن رابطه المحفوظ قديم.
    bad_category = _assert_json_envelope(
        _ajax_post(manager, 'no_such_category', 'add', name='?'), 400
    )
    assert 'افتراضية' in bad_category['message']
    _assert_json_envelope(
        _ajax_post(manager, 'academic_rank', 'explode', id=rank_id), 400
    )
    # A value still linked to rank rules needs the confirmation step.
    _assert_json_envelope(
        _ajax_post(manager, 'academic_rank', 'delete', id=linked_rank_id), 409
    )


def test_app_level_404_answers_ajax_with_json(lookup_setup):
    """A genuine route miss must reach the AJAX caller as JSON, never as the
    HTML 404 page that readJsonResponse reports as "استجابة غير صالحة من
    الخادم (404)"."""
    _db_path, manager, _ = lookup_setup
    response = manager.get(
        '/no-such-route', headers={'X-Requested-With': 'XMLHttpRequest'}
    )
    envelope = _assert_json_envelope(response, 404)
    assert envelope['ok'] is False


def test_json_caller_is_told_when_the_session_is_gone(lookup_setup, app_fx):
    """An expired session must not feed the login page to JSON.parse."""
    db_path, _manager, _ = lookup_setup
    client = app_fx.test_client()
    response = client.post(
        '/teachers/lookup-lists',
        data={
            '_csrf_token': 'stale-token',
            'category': 'admin_assignment_type',
            'action': 'add',
            'name': 'بعد انتهاء الجلسة',
        },
        headers={'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'},
    )
    assert _assert_json_envelope(response, 403)['ok'] is False
    assert _fetchone(
        db_path,
        "SELECT id FROM admin_assignment_types WHERE name = 'بعد انتهاء الجلسة'",
    ) is None


def test_json_caller_without_the_permission_gets_json_not_html(lookup_setup):
    """دور بلا صلاحية القوائم يُرفض في JSON لا بإعادة توجيه HTML."""
    _db_path, _manager, office = lookup_setup
    with office.session_transaction() as session:
        session['_csrf_token'] = 'test-token'
    response = office.post(
        '/teachers/lookup-lists',
        data={
            '_csrf_token': 'test-token',
            'category': 'admin_assignment_type',
            'action': 'add',
            'name': 'محاولة مرفوضة',
        },
        headers={'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'},
    )
    assert _assert_json_envelope(response, 403)['ok'] is False


def test_stale_saved_link_opens_the_page_instead_of_a_404(lookup_setup):
    """رابط محفوظ يحمل category قديم يجب أن يفتح الصفحة، لا أن يرد 404.

    الصفحة موجودة والقيمة وحدها تفقد معناها مع الوقت (تصنيف أُلغي أو
    رابط من قبل إعادة التسمية). الردّ 404 كان يعرض على المستخدم صفحة
    "الصفحة التي تبحث عنها غير موجودة" فيظن أن الصفحة حُذفت.
    """
    _db_path, manager, _ = lookup_setup

    response = manager.get(
        '/teachers/lookup-lists?category=category_that_no_longer_exists',
        headers={'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8'},
    )
    assert response.status_code == 200
    assert 'الصفحة التي تبحث عنها غير موجودة' not in response.get_data(
        as_text=True
    )


def test_trailing_slash_does_not_break_the_page_scripts(lookup_setup):
    """«/teachers/lookup-lists/» بالشرطة يجب أن تُخدم مثل بلا شرطة.

    سكربت الصفحة يرسل إلى ``window.location.href`` و ``form.action``، فإذا
    كانت الصفحة على عنوان بشرطة فكل طلباتها ترجع 404 ويرى المستخدم
    «الرابط المطلوب غير موجود» بدل الصفحة. الشرطة تدخل من إكمال المتصفح
    أو من رابط مكتوب يدوياً، فيدخلها المستخدم بضغطة واحدة.
    """
    _db_path, manager, _ = lookup_setup

    slashed = manager.get('/teachers/lookup-lists/')
    plain = manager.get('/teachers/lookup-lists')
    assert plain.status_code == 200
    assert slashed.status_code == 200

    # المسار الذي فشل فعلاً: fetch() يرسل Accept: */* افتراضياً.
    def fetch(url):
        return manager.get(url, headers={'Accept': '*/*'})

    assert fetch('/teachers/lookup-lists').status_code == 200
    assert fetch('/teachers/lookup-lists/').status_code == 200
    assert fetch('/teachers/lookup-lists/?category=academic_rank').status_code == 200


def test_browser_form_post_still_gets_html_redirects(lookup_setup):
    """The JSON refusals must not leak into ordinary browser form posts.

    Chrome sends ``*/*;q=0.8`` with every form post, so ``*/*`` must never be
    read as "this caller wants JSON" — otherwise the delete button would answer
    with a raw JSON blob instead of the page.
    """
    db_path, manager, _ = lookup_setup
    response = manager.post(
        '/teachers/lookup-lists',
        data={
            '_csrf_token': 'test-token',
            'category': 'admin_assignment_type',
            'action': 'add',
            'name': 'من نموذج عادي',
        },
        headers={'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8'},
    )
    assert response.status_code == 302
    assert 'json' not in (response.headers.get('Content-Type') or '')
    assert _fetchone(
        db_path,
        "SELECT id FROM admin_assignment_types WHERE name = 'من نموذج عادي'",
    )


def test_lookup_list_add_rename_and_toggle_are_ajax_actions(lookup_setup):
    db_path, manager, _ = lookup_setup
    response = _ajax_post(
        manager, 'admin_assignment_type', 'add', name='منسق الاختبارات'
    )
    assert response.status_code == 200
    assert response.get_json() == {'ok': True, 'message': 'تم الحفظ بنجاح'}
    added = _fetchone(
        db_path,
        "SELECT id FROM admin_assignment_types WHERE name = 'منسق الاختبارات'",
    )
    assert added

    response = _ajax_post(
        manager, 'admin_assignment_type', 'rename',
        id=str(added['id']), name='منسق الامتحانات',
    )
    assert response.status_code == 200
    assert _fetchone(
        db_path, 'SELECT name FROM admin_assignment_types WHERE id = ?',
        (added['id'],),
    ) == {'name': 'منسق الامتحانات'}

    system_id = _fetchone(
        db_path,
        "SELECT id FROM admin_assignment_types WHERE internal_code = 'head_of_department'",
    )['id']
    response = _ajax_post(
        manager, 'admin_assignment_type', 'toggle', id=str(system_id)
    )
    assert response.status_code == 200
    assert _fetchone(
        db_path, 'SELECT is_active FROM admin_assignment_types WHERE id = ?',
        (system_id,),
    ) == {'is_active': 0}


def test_lookup_page_has_fast_search_and_ajax_management_controls(lookup_setup):
    _, manager, _ = lookup_setup
    body = manager.get(
        '/teachers/lookup-lists?category=admin_assignment_type'
    ).get_data(as_text=True)
    with open('static/js/pages/teachers_lookup_lists.js', encoding='utf-8') as js_file:
        script = js_file.read()

    assert 'id="lookupCategorySelect"' in body
    assert 'id="lookupSearch"' in body
    assert 'id="lookupStatusFilter"' in body
    assert 'data-lookup-ajax' in body
    assert 'id="lookupFeedback"' in body
    assert 'data-lookup-row' in body
    assert 'data-lookup-rename' in body
    assert 'data-lookup-name' in body
    assert 'divide-y divide-outline-variant' in body
    assert 'إضافة تكليف إداري' in body
    assert "event.key === 'Escape'" in script
    assert "target.closest('[data-lookup-edit]')" in script
    assert "window.location.assign(url.toString())" in script
    assert 'data-lookup-save aria-label="حفظ الاسم"' in body
    assert "'X-CSRFToken'" in script


def test_json_reader_is_not_nested_inside_the_refresh_helper(lookup_setup):
    """``readJsonResponse`` must live in the IIFE scope, not inside a sibling.

    Declared inside ``refreshValues`` it was hoisted only there, so every edit
    died with a ``ReferenceError`` *before* the response was ever read: the row
    was written but the page showed an error and never refreshed.  The old test
    only asserted the name existed somewhere in the file, which a nested
    definition satisfies — this one pins the scope.
    """
    _, manager, _ = lookup_setup
    with open('static/js/pages/teachers_lookup_lists.js', encoding='utf-8') as js_file:
        script = js_file.read()

    reader_at = script.index('async function readJsonResponse(')
    refresh_at = script.index('async function refreshValues(')
    submit_at = script.index("document.addEventListener('submit'")
    assert reader_at < refresh_at, 'readJsonResponse must be declared before its users'
    assert submit_at > reader_at

    # Not nested: the reader sits at the IIFE's own indent level (two spaces).
    # Compare the exact prefix — `indent.strip() == ''` is true for *any* indent
    # and would pass a nested definition, i.e. a guard that never fires.
    line_start = script.rfind('\n', 0, reader_at) + 1
    assert script[line_start:reader_at] == '  ', (
        'readJsonResponse is indented inside another function'
    )

    # And no response may reach JSON.parse without a content-type guard.
    assert "contentType.includes('application/json')" in script
    assert 'csrfTokenOf(form)' in script
    assert 'csrfTokenOf' in script
    assert "form.querySelector('[name=\"_csrf_token\"]').value" not in script


def test_ajax_lookup_uses_form_action_attribute_not_named_control(lookup_setup):
    """A hidden ``name=action`` control shadows the DOM ``form.action`` property."""
    _, manager, _ = lookup_setup
    body = manager.get(
        '/teachers/lookup-lists?category=admin_assignment_type'
    ).get_data(as_text=True)
    script_match = re.search(
        r'<script defer src="([^"]*pages-teachers_lookup_lists'
        r'\.[a-f0-9]{8}\.js)"', body
    )
    assert script_match, 'the page must load its built lookup-list script'
    response = manager.get(script_match.group(1))
    assert response.status_code == 200
    script = response.get_data(as_text=True)

    assert 'getAttribute("action")' in script or "getAttribute('action')" in script
    assert 'fetch(form.action' not in script


def test_page_script_is_served_with_a_cache_busting_version(lookup_setup):
    """The page script URL must carry a version query.

    ``/static/`` is served with a one-year ``max-age``, so a script URL
    without a version keeps the browser on the pre-fix copy for a year: the
    fix is deployed, the page still throws, and it looks like the fix did
    nothing.  The version query makes the URL change whenever the file does.
    """
    _, manager, _ = lookup_setup
    body = manager.get(
        '/teachers/lookup-lists?category=admin_assignment_type'
    ).get_data(as_text=True)

    match = re.search(
        r'src="([^"]*(?:js/pages/teachers_lookup_lists'
        r'(?:\.[a-f0-9]{8})?\.js|pages-teachers_lookup_lists'
        r'\.[a-f0-9]{8}\.js)(?:\?v=\d+)?)"',
        body,
    )
    assert match, 'the page must load its own script'
    script_url = match.group(1)
    assert (
        re.search(r'\.[a-f0-9]{8}\.js$', script_url)
        or re.search(r'\?v=\d+$', script_url)
    ), f'script URL has no content hash or cache-busting version: {script_url}'


def test_json_accept_header_is_treated_as_ajax(lookup_setup):
    db_path, manager, _ = lookup_setup
    response = manager.post(
        '/teachers/lookup-lists',
        data={
            '_csrf_token': 'test-token',
            'category': 'admin_assignment_type',
            'action': 'add',
            'name': 'خيار JSON',
        },
        headers={'Accept': 'application/json'},
    )
    assert response.status_code == 200
    assert response.get_json() == {'ok': True, 'message': 'تم الحفظ بنجاح'}
    assert _fetchone(
        db_path,
        "SELECT id FROM admin_assignment_types WHERE name = 'خيار JSON'",
    )


def test_ajax_lookup_validation_returns_inline_error_without_redirect(lookup_setup):
    _, manager, _ = lookup_setup
    response = _ajax_post(
        manager, 'admin_assignment_type', 'add', name='   '
    )

    assert response.status_code == 400
    assert response.get_json() == {
        'ok': False,
        'message': 'اكتب نص القيمة أولاً',
    }
    assert 'BASE_FLASH_BOOT' not in manager.get(
        '/teachers/lookup-lists'
    ).get_data(as_text=True)


def test_system_assignment_rename_keeps_its_internal_role(lookup_setup):
    db_path, manager, _ = lookup_setup
    conn = connect(str(db_path))
    row = _fetchone(
        db_path,
        "SELECT id FROM admin_assignment_types "
        "WHERE name = 'رئيس قسم' AND internal_code = 'head_of_department'",
    )
    assert row
    conn.execute("INSERT INTO teachers (name) VALUES ('عضو رئيس قسم')")
    teacher_id = conn.execute(
        "SELECT id FROM teachers WHERE name = 'عضو رئيس قسم'"
    ).fetchone()['id']
    conn.execute(
        "UPDATE teachers SET position = 'رئيس قسم', admin_assignment_type_id = ? "
        "WHERE id = ?", (row['id'], teacher_id),
    )
    conn.commit()
    conn.close()

    response = _ajax_post(
        manager, 'admin_assignment_type', 'rename',
        id=str(row['id']), name='رئيس القسم الأكاديمي',
    )

    assert response.status_code == 200
    assert response.get_json() == {'ok': True, 'message': 'تم الحفظ بنجاح'}
    renamed = _fetchone(
        db_path, 'SELECT name, internal_code, is_system_linked '
        'FROM admin_assignment_types WHERE id = ?', (row['id'],)
    )
    assert renamed == {
        'name': 'رئيس القسم الأكاديمي',
        'internal_code': 'head_of_department',
        'is_system_linked': 1,
    }
    assert _fetchone(
        db_path,
        'SELECT position, admin_assignment_type_id FROM teachers WHERE id = ?',
        (teacher_id,),
    ) == {
        'position': 'رئيس القسم الأكاديمي',
        'admin_assignment_type_id': row['id'],
    }
    # /     /     >---- الاسم الجديد يصل نموذج تعديل الأستاذ — وهو نموذج
    # /     /     >---- للمكتب (العميد لا يملك teachers.manage)، فنتأكد أن
    # /     /     >---- إعادة التسمية انتقلت لواجهة من يعدّل الأساتذة.
    _db_path, _dean, office = lookup_setup
    page = office.get(f'/teachers/edit/{teacher_id}')
    assert page.status_code == 200
    assert f'data-assignment-type-id="{row["id"]}"' in page.get_data(as_text=True)


def test_legacy_assignment_text_is_backfilled_to_stable_lookup_id(lookup_setup):
    db_path, _manager, _ = lookup_setup
    conn = connect(str(db_path))
    conn.execute(
        "DELETE FROM _migration_log "
        "WHERE migration_name = 'managed_admin_assignment_role_protection_v1'"
    )
    conn.execute(
        "INSERT INTO teachers (name, position) VALUES ('عضو تكليف قديم', 'رئيس قسم')"
    )
    teacher_id = conn.execute(
        "SELECT id FROM teachers WHERE name = 'عضو تكليف قديم'"
    ).fetchone()['id']
    ensure_schema(conn)

    teacher = conn.execute(
        'SELECT position, admin_assignment_type_id FROM teachers WHERE id = ?',
        (teacher_id,),
    ).fetchone()
    assert teacher['position'] == 'رئيس قسم'
    assert teacher['admin_assignment_type_id'] is not None
    from page_routes.teachers import _roles_from_assignment_type
    assert _roles_from_assignment_type(
        conn, teacher['admin_assignment_type_id']
    ) == {'head_of_department'}
    conn.close()


def test_general_assignment_never_maps_to_a_dashboard_role(lookup_setup):
    db_path, _manager, _ = lookup_setup
    conn = connect(str(db_path))
    conn.execute(
        "INSERT INTO admin_assignment_types "
        "(name, default_hours, is_active, sort_order, internal_code, is_system_linked) "
        "VALUES ('منسق الجودة', 0, 1, 1, 'head_of_department', 0)"
    )
    assignment_type_id = conn.execute(
        "SELECT id FROM admin_assignment_types WHERE name = 'منسق الجودة'"
    ).fetchone()['id']
    from page_routes.teachers import _roles_from_assignment_type
    assert _roles_from_assignment_type(conn, assignment_type_id) == set()
    conn.close()


def test_used_general_assignment_delete_requires_confirmation_first(lookup_setup):
    db_path, manager, _ = lookup_setup
    conn = connect(str(db_path))
    conn.execute(
        "INSERT INTO admin_assignment_types "
        "(name, default_hours, is_active, sort_order, is_system_linked) "
        "VALUES ('تكليف تجريبي', 0, 1, 99, 0)"
    )
    task_id = conn.execute(
        "SELECT id FROM admin_assignment_types WHERE name = 'تكليف تجريبي'"
    ).fetchone()['id']
    conn.execute(
        "INSERT INTO teachers (name, position) VALUES ('عضو تجريبي', 'تكليف تجريبي')"
    )
    teacher_id = conn.execute(
        "SELECT id FROM teachers WHERE name = 'عضو تجريبي'"
    ).fetchone()['id']
    conn.execute(
        '''INSERT INTO faculty_admin_assignments
           (teacher_id, task_name, start_date)
           VALUES (?, 'تكليف تجريبي', '2026-09-01')''',
        (teacher_id,),
    )
    conn.commit()
    conn.close()

    # /     /     >---- بدون نقل أو تفريغ: شاشة تأكيد ولا يُحذف شيء
    response = _post(
        manager, 'admin_assignment_type', 'delete', id=str(task_id)
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'اختر نقل الاستخدام إلى قيمة بديلة' in body
    assert 'تأكيد حذف «تكليف تجريبي»' in body
    assert _fetchone(
        db_path, 'SELECT position FROM teachers WHERE name = ?', ('عضو تجريبي',)
    )['position'] == 'تكليف تجريبي'
    assert _fetchone(
        db_path,
        'SELECT COUNT(*) AS count FROM faculty_admin_assignments WHERE task_name = ?',
        ('تكليف تجريبي',),
    ) == {'count': 1}
    assert _fetchone(
        db_path, 'SELECT id FROM admin_assignment_types WHERE id = ?', (task_id,)
    ) == {'id': task_id}

    # /     /     >---- بالتفريغ: يُحذف التكليف وتُفرَّغ الحقول المرتبطة
    response = _post(
        manager, 'admin_assignment_type', 'delete',
        id=str(task_id), clear_references='1',
    )
    assert response.status_code == 200
    assert _fetchone(
        db_path, 'SELECT id FROM admin_assignment_types WHERE id = ?', (task_id,)
    ) is None
    assert _fetchone(
        db_path, 'SELECT position FROM teachers WHERE name = ?', ('عضو تجريبي',)
    )['position'] == ''
    assert _fetchone(
        db_path,
        'SELECT COUNT(*) AS count FROM faculty_admin_assignments WHERE task_name = ?',
        ('تكليف تجريبي',),
    ) == {'count': 0}


def test_ajax_linked_general_assignment_delete_needs_confirmation(lookup_setup):
    """AJAX delete of a linked general task is refused (409) until the user
    picks a replacement or confirms clearing — never an HTML page."""
    db_path, manager, _ = lookup_setup
    conn = connect(str(db_path))
    conn.execute(
        "INSERT INTO admin_assignment_types "
        "(name, default_hours, is_active, sort_order, is_system_linked) "
        "VALUES ('تكليف مرتبط', 0, 1, 99, 0)"
    )
    task_id = conn.execute(
        "SELECT id FROM admin_assignment_types WHERE name = 'تكليف مرتبط'"
    ).fetchone()['id']
    conn.execute(
        "INSERT INTO teachers (name, position) VALUES ('عضو مرتبط', 'تكليف مرتبط')"
    )
    conn.commit()
    conn.close()

    response = _ajax_post(
        manager, 'admin_assignment_type', 'delete', id=str(task_id)
    )
    envelope = _assert_json_envelope(response, 409)
    assert envelope['ok'] is False
    assert 'اختر نقل الاستخدام إلى قيمة بديلة' in envelope['message']
    assert _fetchone(
        db_path, 'SELECT id FROM admin_assignment_types WHERE id = ?', (task_id,)
    ) == {'id': task_id}


def test_ajax_linked_general_assignment_delete_with_clear(lookup_setup):
    db_path, manager, _ = lookup_setup
    conn = connect(str(db_path))
    conn.execute(
        "INSERT INTO admin_assignment_types "
        "(name, default_hours, is_active, sort_order, is_system_linked) "
        "VALUES ('تكليف قابل للتفريغ', 0, 1, 99, 0)"
    )
    task_id = conn.execute(
        "SELECT id FROM admin_assignment_types WHERE name = 'تكليف قابل للتفريغ'"
    ).fetchone()['id']
    conn.execute(
        "INSERT INTO teachers (name, position) "
        "VALUES ('عضو قابل للتفريغ', 'تكليف قابل للتفريغ')"
    )
    conn.commit()
    conn.close()

    response = _ajax_post(
        manager, 'admin_assignment_type', 'delete',
        id=str(task_id), clear_references='1',
    )
    _assert_json_envelope(response, 200)
    assert response.get_json()['ok'] is True
    assert _fetchone(
        db_path, 'SELECT id FROM admin_assignment_types WHERE id = ?', (task_id,)
    ) is None
    assert _fetchone(
        db_path, 'SELECT position FROM teachers WHERE name = ?',
        ('عضو قابل للتفريغ',),
    )['position'] == ''


def test_ajax_linked_general_assignment_delete_moves_to_replacement(lookup_setup):
    db_path, manager, _ = lookup_setup
    conn = connect(str(db_path))
    conn.execute(
        "INSERT INTO admin_assignment_types "
        "(name, default_hours, is_active, sort_order, is_system_linked) "
        "VALUES ('تكليف يحوَّل', 0, 1, 98, 0), ('تكليف بديل', 0, 1, 97, 0)"
    )
    task_id = conn.execute(
        "SELECT id FROM admin_assignment_types WHERE name = 'تكليف يحوَّل'"
    ).fetchone()['id']
    replacement_id = conn.execute(
        "SELECT id FROM admin_assignment_types WHERE name = 'تكليف بديل'"
    ).fetchone()['id']
    conn.execute(
        "INSERT INTO teachers (name, position) VALUES ('عضو يحوَّل', 'تكليف يحوَّل')"
    )
    conn.execute(
        '''INSERT INTO faculty_admin_assignments
           (teacher_id, task_name, start_date)
           SELECT id, 'تكليف يحوَّل', '2026-09-01' FROM teachers
           WHERE name = 'عضو يحوَّل' '''
    )
    conn.commit()
    conn.close()

    response = _ajax_post(
        manager, 'admin_assignment_type', 'delete',
        id=str(task_id), replacement_id=str(replacement_id),
    )
    _assert_json_envelope(response, 200)
    assert response.get_json()['ok'] is True
    teacher = _fetchone(
        db_path,
        'SELECT position, admin_assignment_type_id FROM teachers WHERE name = ?',
        ('عضو يحوَّل',),
    )
    assert teacher['position'] == 'تكليف بديل'
    assert teacher['admin_assignment_type_id'] == replacement_id
    assert _fetchone(
        db_path,
        'SELECT COUNT(*) AS count FROM faculty_admin_assignments WHERE task_name = ?',
        ('تكليف بديل',),
    ) == {'count': 1}
    assert _fetchone(
        db_path, 'SELECT id FROM admin_assignment_types WHERE id = ?', (task_id,)
    ) is None


def test_unused_general_assignment_can_be_deleted(lookup_setup):
    db_path, manager, _ = lookup_setup
    conn = connect(str(db_path))
    conn.execute(
        "INSERT INTO admin_assignment_types "
        "(name, default_hours, is_active, sort_order, is_system_linked) "
        "VALUES ('تكليف غير مستخدم', 0, 1, 99, 0)"
    )
    task_id = conn.execute(
        "SELECT id FROM admin_assignment_types WHERE name = 'تكليف غير مستخدم'"
    ).fetchone()['id']
    conn.commit()
    conn.close()

    response = _post(
        manager, 'admin_assignment_type', 'delete', id=str(task_id)
    )

    assert response.status_code == 200
    assert _fetchone(
        db_path, 'SELECT id FROM admin_assignment_types WHERE id = ?', (task_id,)
    ) is None


def test_active_system_role_is_retired_by_disabling_not_by_refusal(lookup_setup):
    """الدور النظامي يُزال بلا رفض: تعطيل + تفريغ، مع بقاء صفه في القاعدة.

    الحذف الصلب كان يمحو ``internal_code`` فيفقد النظام ربط الصلاحية، والرسالة
    «لا يمكن حذف دور نظامي» كانت تمنع العميد من قراره.  الآن الإزالة تُخفي
    الدور من الاختيارات (كل القوائم تفلتر على is_active) وتُفرّغ ارتباطاته.
    """
    db_path, manager, _ = lookup_setup
    role = _fetchone(
        db_path,
        "SELECT id, name, internal_code, is_active, is_protected_role "
        "FROM admin_assignment_types "
        "WHERE internal_code = 'exam' AND name = 'رئيس قسم الدراسة والامتحانات'",
    )
    assert role is not None
    assert role['is_active'] == 1
    assert role['is_protected_role'] == 1

    response = _post(
        manager, 'admin_assignment_type', 'delete',
        id=str(role['id']), clear_references='1',
    )

    assert response.status_code == 200
    assert any('تم تعطيل الدور النظامي' in message for message in _flash_messages(response))
    after = _fetchone(
        db_path,
        "SELECT id, name, internal_code, is_active, is_protected_role "
        "FROM admin_assignment_types WHERE id = ?", (role['id'],)
    )
    # /     /     >---- الصف باقٍ (ربط الصلاحية سليم) لكنه خرج من الاختيارات
    assert after['id'] == role['id']
    assert after['name'] == role['name']
    assert after['internal_code'] == 'exam'
    assert after['is_active'] == 0
    assert after['is_protected_role'] == 0
    # /     /     >---- ولا يظهر بعد الآن في قائمة تكليف الأستاذ (الصفحة
    # /     /     >---- ما زالت تعرضه مع علامة «معطّل» ليمكن إعادة تفعيله)
    edit_page = manager.get('/teachers/edit/1')
    assert role['name'] not in edit_page.get_data(as_text=True)


def test_dean_may_retire_a_disabled_system_role_with_no_users(lookup_setup):
    db_path, manager, _ = lookup_setup
    conn = connect(str(db_path))
    conn.execute(
        '''UPDATE admin_assignment_types SET is_active = 0
           WHERE internal_code = 'dean' AND is_system_linked = 1'''
    )
    conn.commit()
    conn.close()

    role = _fetchone(
        db_path,
        "SELECT id FROM admin_assignment_types "
        "WHERE internal_code = 'dean' AND name = 'عميد الكلية'",
    )
    response = _post(
        manager, 'admin_assignment_type', 'delete',
        id=str(role['id']), clear_references='1',
    )

    assert any(
        'تم الحفظ بنجاح' in message for message in _flash_messages(response)
    )
    still_there = _fetchone(
        db_path,
        'SELECT id FROM admin_assignment_types WHERE id = ?', (role['id'],)
    )
    assert still_there == {'id': role['id']}


def test_retired_system_role_labels_are_inactive(lookup_setup):
    db_path, _manager, _ = lookup_setup
    retired_labels = (
        'رئيس قسم',
        'رئيس قسم البحث والتطوير',
        'رئيس قسم الامتحانات',
    )
    conn = connect(str(db_path))
    rows = conn.execute(
        'SELECT name, is_active FROM admin_assignment_types '
        'WHERE name IN (?, ?, ?)',
        retired_labels,
    ).fetchall()
    conn.close()

    assert {row['name']: row['is_active'] for row in rows} == {
        label: 0 for label in retired_labels
    }


def test_inactive_unreferenced_orphan_role_record_is_removable(lookup_setup):
    db_path, manager, _ = lookup_setup
    conn = connect(str(db_path))
    conn.execute(
        "INSERT INTO admin_assignment_types "
        "(name, default_hours, is_active, sort_order, internal_code, "
        "is_system_linked) VALUES ('رئيس القسم ذ', 0, 0, 99, "
        "'head_of_department', 1)"
    )
    orphan_id = conn.execute(
        "SELECT id FROM admin_assignment_types WHERE name = 'رئيس القسم ذ'"
    ).fetchone()['id']
    conn.execute(
        "DELETE FROM _migration_log "
        "WHERE migration_name = 'managed_admin_assignment_role_protection_v1'"
    )
    ensure_schema(conn)
    conn.close()

    orphan = _fetchone(
        db_path,
        'SELECT is_protected_role FROM admin_assignment_types WHERE id = ?',
        (orphan_id,),
    )
    assert orphan == {'is_protected_role': 0}
    from page_routes.teachers import _roles_from_assignment_type
    conn = connect(str(db_path))
    roles = _roles_from_assignment_type(conn, orphan_id)
    conn.close()
    assert roles == set()

    response = _post(
        manager, 'admin_assignment_type', 'delete', id=str(orphan_id)
    )

    assert response.status_code == 200
    assert any('تم حذف القيمة' in message for message in _flash_messages(response))
    assert _fetchone(
        db_path, 'SELECT id FROM admin_assignment_types WHERE id = ?', (orphan_id,)
    ) is None


def test_dean_may_retire_a_disabled_system_role_with_no_users(lookup_setup):
    """حتى الدور المعطّل والمستخدم صفراً يُزال بلا رفض."""
    db_path, manager, _ = lookup_setup
    conn = connect(str(db_path))
    conn.execute(
        '''UPDATE admin_assignment_types SET is_active = 0
           WHERE internal_code = 'dean' AND is_system_linked = 1'''
    )
    conn.execute(
        "DELETE FROM _migration_log "
        "WHERE migration_name = 'managed_admin_assignment_role_protection_v1'"
    )
    ensure_schema(conn)
    conn.close()

    role = _fetchone(
        db_path,
        "SELECT id FROM admin_assignment_types "
        "WHERE internal_code = 'dean' AND name = 'عميد الكلية'",
    )
    assert _fetchone(
        db_path,
        'SELECT COUNT(*) AS count FROM teachers '
        'WHERE admin_assignment_type_id = ?', (role['id'],)
    ) == {'count': 0}

    response = _post(
        manager, 'admin_assignment_type', 'delete',
        id=str(role['id']), clear_references='1',
    )

    assert any(
        'تم تعطيل الدور النظامي' in message
        for message in _flash_messages(response)
    )
    still_there = _fetchone(
        db_path,
        'SELECT id FROM admin_assignment_types WHERE id = ?', (role['id'],)
    )
    assert still_there == {'id': role['id']}


def test_rank_replacement_migrates_teacher_and_workload_rules(lookup_setup):
    db_path, manager, _ = lookup_setup
    conn = connect(str(db_path))
    conn.execute(
        "INSERT INTO academic_ranks (name_ar, name_en, sort_order) "
        "VALUES ('رتبة تجريبية', 'Test rank', 999)"
    )
    old_id = conn.execute(
        "SELECT id FROM academic_ranks WHERE name_ar = 'رتبة تجريبية'"
    ).fetchone()['id']
    replacement = conn.execute(
        'SELECT id FROM academic_ranks WHERE id != ? AND is_active = 1 LIMIT 1',
        (old_id,),
    ).fetchone()['id']
    qualification_id = conn.execute(
        'SELECT id FROM qualifications WHERE is_active = 1 LIMIT 1'
    ).fetchone()['id']
    conn.execute(
        "INSERT INTO teachers (name, rank_id, academic_rank) "
        "VALUES ('عضو رتبة تجريبية', ?, 'رتبة تجريبية')", (old_id,)
    )
    conn.execute(
        'INSERT INTO rank_rules (qualification_id, rank_id) VALUES (?, ?)',
        (qualification_id, old_id),
    )
    conn.execute(
        'INSERT INTO faculty_workload_rules '
        '(rank_id, category, min_hours, max_hours, academic_year) '
        "VALUES (?, 'lookup-test', 2, 8, '2099-2100')", (old_id,)
    )
    conn.commit()
    conn.close()

    response = _post(
        manager, 'academic_rank', 'delete',
        id=str(old_id), replacement_id=str(replacement),
    )

    assert response.status_code == 200
    assert _fetchone(
        db_path, 'SELECT rank_id, academic_rank FROM teachers WHERE name = ?',
        ('عضو رتبة تجريبية',),
    ) == {
        'rank_id': replacement,
        'academic_rank': _fetchone(
            db_path, 'SELECT name_ar FROM academic_ranks WHERE id = ?',
            (replacement,),
        )['name_ar'],
    }
    assert _fetchone(
        db_path, 'SELECT rank_id FROM faculty_workload_rules '
        "WHERE category = 'lookup-test' AND academic_year = '2099-2100'"
    ) == {'rank_id': replacement}
    assert _fetchone(
        db_path, 'SELECT rank_id FROM rank_rules WHERE qualification_id = ?',
        (qualification_id,),
    ) == {'rank_id': replacement}


def test_removed_default_assignment_does_not_reappear_on_schema_recheck(
    lookup_setup,
):
    db_path, _, _ = lookup_setup
    conn = connect(str(db_path))
    qualification = conn.execute(
        'SELECT name_ar FROM qualifications ORDER BY id LIMIT 1'
    ).fetchone()['name_ar']
    specialization = conn.execute(
        'SELECT id, name FROM specializations ORDER BY id LIMIT 1'
    ).fetchone()
    conn.execute(
        "DELETE FROM admin_assignment_types WHERE name = 'منسق القاعات'"
    )
    conn.execute('DELETE FROM qualifications WHERE name_ar = ?', (qualification,))
    if specialization:
        conn.execute('DELETE FROM specializations WHERE id = ?', (specialization['id'],))
    conn.commit()
    ensure_schema(conn)
    remaining = conn.execute(
        "SELECT COUNT(*) FROM admin_assignment_types WHERE name = 'منسق القاعات'"
    ).fetchone()[0]
    remaining_qualifications = conn.execute(
        'SELECT COUNT(*) FROM qualifications WHERE name_ar = ?', (qualification,)
    ).fetchone()[0]
    remaining_specializations = (
        conn.execute(
            'SELECT COUNT(*) FROM specializations WHERE id = ? AND name = ?',
            (specialization['id'], specialization['name']),
        ).fetchone()[0]
        if specialization else 0
    )
    conn.close()

    assert remaining == 0
    assert remaining_qualifications == 0
    assert remaining_specializations == 0
