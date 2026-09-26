"""Output-escaping regressions for client-side HTML construction (§8, area 3).

The app builds large amounts of markup with ``innerHTML`` /
``insertAdjacentHTML`` and has no client framework, so every untrusted value
concatenated into that markup is an XSS sink. Most of these payloads reach the
browser *stored*: names, academic numbers, course codes, and administrative
task types are only ``.strip()``-ed on the way into SQLite, then echoed back
through JSON APIs into the page.

Two layers of coverage:

1. Behavioural — the escaping helper is extracted from each file and executed
   under Node against a hostile payload. Skipped automatically when Node is
   unavailable so the suite still runs on hosts without it.
2. Static — the sink itself is asserted to route the value through the
   escaper, matching the existing convention for JS assertions in this suite.
"""

import json
import os
import re
import shutil
import subprocess

import pytest


NODE = shutil.which('node')

# A payload that breaks out of text content, a double-quoted attribute, and a
# single-quoted attribute, and then tries to execute.
PAYLOAD = '\'"><img src=x onerror=alert(1)>&\\'


def _read_js(rel_path):
    with open(os.path.join('static', 'js', rel_path), encoding='utf-8') as fh:
        return fh.read()


def _extract_function(js, name):
    """Return the full source of ``function <name>(...) { ... }``.

    Brace-matched rather than regex-matched so nested bodies, template
    literals, and object literals inside the function are captured whole.
    """
    match = re.search(r'function\s+' + re.escape(name) + r'\s*\(', js)
    if not match:
        raise AssertionError('no `function {}` declaration found'.format(name))

    start = match.start()
    depth = 0
    body_start = js.index('{', match.end() - 1)
    for idx in range(body_start, len(js)):
        char = js[idx]
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return js[start:idx + 1]
    raise AssertionError('unbalanced braces in `function {}`'.format(name))


def _run_in_node(source, expression, local_name):
    """Bind ``source`` as ``local_name`` and return ``expression``'s value.

    The extracted function keeps its real name, so it is re-bound to a
    caller-chosen identifier. That lets one harness serve both `esc` (declared
    inside an IIFE in the browser) and `escapeHtml` (declared at IIFE top
    level) without the browser's scoping rules getting in the way.
    """
    script = 'const {} = {};\nconsole.log(JSON.stringify({}));'.format(
        local_name, source, expression,
    )
    result = subprocess.run(
        [NODE, '-e', script],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _assert_payload_neutralised(escaper_source, name, expression, local_name):
    escaped = _run_in_node(escaper_source, expression, local_name)
    # `&` is deliberately excluded: it is the *start* of every entity this
    # escaper emits. What must not survive is anything that can open a tag,
    # close an attribute, or start a new one.
    for char in '<>"\'':
        assert char not in escaped, (
            '{} left a raw {!r} in the output: {!r}'.format(name, char, escaped)
        )
    assert '&lt;' in escaped and '&amp;' in escaped, escaped


def _call(local_name, value):
    """Build a JS call expression with ``value`` embedded as a JSON literal.

    Going through JSON avoids hand-escaping backticks and quotes into a JS
    template literal, which is where quoting bugs hide.
    """
    return '{}({})'.format(local_name, json.dumps(value))


# --------------------------------------------------------------------------
# 1. Behavioural: every escaper neutralises a breakout payload.
# --------------------------------------------------------------------------

ESCAPERS = [
    ('toast.js', 'esc', '_esc'),
    ('courses_list.js', 'esc', '_esc'),
    ('teachers_assign.js', 'esc', '_esc'),
    ('teachers_teaching_record_standalone_dept.js', 'esc', '_esc'),
    ('faculty_performance_select_report.js', 'esc', '_esc'),
    ('faculty_performance_edit_assignments.js', 'esc', '_esc'),
    ('courses_create.js', 'esc', '_esc'),
    ('exams/workspace.js', 'escapeHtml', '_escapeHtml'),
    ('shared/timetable_helpers.js', 'esc', '_esc'),
]


@pytest.mark.skipif(NODE is None, reason='node is not installed')
@pytest.mark.parametrize('rel_path,func_name,local_name', ESCAPERS,
                         ids=[p[0] for p in ESCAPERS])
def test_escaper_neutralises_attribute_and_tag_breakout(rel_path, func_name, local_name):
    source = _extract_function(_read_js(rel_path), func_name)
    _assert_payload_neutralised(
        source,
        '{}:{}'.format(rel_path, func_name),
        _call(local_name, PAYLOAD),
        local_name,
    )


@pytest.mark.skipif(NODE is None, reason='node is not installed')
@pytest.mark.parametrize('rel_path,func_name,local_name', ESCAPERS,
                         ids=[p[0] for p in ESCAPERS])
def test_escaper_escapes_all_five_markup_characters(rel_path, func_name, local_name):
    """`& < > " '` must all be encoded, so the value is safe in any attribute."""
    source = _extract_function(_read_js(rel_path), func_name)
    escaped = _run_in_node(source, _call(local_name, '&<>"\''), local_name)

    for encoded in ('&amp;', '&lt;', '&gt;', '&quot;', '&#39;'):
        assert encoded in escaped, '{} missing {}: {!r}'.format(rel_path, encoded, escaped)


@pytest.mark.skipif(NODE is None, reason='node is not installed')
def test_spa_escape_html_escapes_apostrophe():
    """spa/app.js only encoded `& < > "`, so single-quoted attrs stayed open."""
    source = _extract_function(_read_js('spa/app.js'), 'escapeHtml')
    escaped = _run_in_node(source, _call('_escapeHtml', "a'b"), '_escapeHtml')

    assert escaped == 'a&#39;b', escaped


@pytest.mark.skipif(NODE is None, reason='node is not installed')
@pytest.mark.parametrize('value,expected', [
    (None, ''),
    ('', ''),
    (0, '0'),
    (False, 'false'),
    ('<b>', '&lt;b&gt;'),
])
def test_escaper_preserves_falsy_and_primitive_values(value, expected):
    """Escaping must not swallow 0/false, which are meaningful IDs and flags."""
    source = _extract_function(_read_js('toast.js'), 'esc')
    assert _run_in_node(source, _call('_esc', value), '_esc') == expected


# --------------------------------------------------------------------------
# 2. Static: the sinks route untrusted values through the escaper.
# --------------------------------------------------------------------------

def test_toast_escapes_the_server_supplied_message():
    """The app-wide toast is the widest sink: Flask flash reaches it verbatim.

    base.html serialises flash with `tojson`, which re-emits literal `<`, and
    several flash messages interpolate stored names (teacher, course, period)
    that the server only strips. Escaping here closes the whole chain at once.
    """
    js = _read_js('toast.js')

    assert "esc(message)" in js
    assert "'>' + message + '</p>'" not in js


def test_base_flash_routes_flash_messages_into_the_toast_sink():
    """Documents the chain end that makes the toast sink reachable.

    base_flash.js iterates `BASE_FLASH_BOOT.messages` and hands each message
    to `window.showNotification`, which toast.js defines — so every Flask
    `flash()` in the app flows into the escaped sink guarded above.
    """
    js = _read_js('base_flash.js')

    assert 'window.showNotification(' in js
    assert 'BOOT.messages' in js


def test_toast_is_the_shared_notification_sink():
    assert 'window.showNotification = function (message, type, duration)' in _read_js('toast.js')


def test_courses_list_escapes_department_name_and_prerequisite():
    js = _read_js('courses_list.js')

    assert "esc(d.name)" in js
    assert "esc(c.requires || '—')" in js


def test_teacher_assign_search_escapes_pool_results():
    js = _read_js('teachers_assign.js')

    assert "esc(t.name)" in js
    assert "esc(t.academic_number || '')" in js
    # The avatar initial is a bare first character of the same untrusted name.
    assert "esc(t.name ? t.name.charAt(0) : '?')" in js


def test_teaching_record_department_dropdown_escapes_teacher_identity():
    js = _read_js('teachers_teaching_record_standalone_dept.js')

    assert "esc(t.name)" in js
    assert "esc(t.academic_number)" in js


def test_faculty_report_dropdowns_escape_course_and_teacher_identity():
    js = _read_js('faculty_performance_select_report.js')

    assert 'esc(c.name)' in js
    assert 'esc(c.code)' in js
    assert 'esc(t.name)' in js


def test_admin_task_type_escapes_into_option_value_attribute():
    """The worst case: the value lands inside a `value="..."` attribute.

    Task-type names come from the teacher form's free-text custom-position
    field, which `_ensure_admin_task` only strips, so a name containing a
    double quote would otherwise inject a new attribute.
    """
    js = _read_js('faculty_performance_edit_assignments.js')

    assert "'<option value=\"' + esc(t.name) + '\">'" in js
    assert "'<option value=\"' + t.name + '\">'" not in js


def test_courses_create_prerequisite_picker_escapes_code_and_name():
    js = _read_js('courses_create.js')

    assert "esc(c.code || '')" in js
    assert "esc(c.name || '')" in js


def test_timetable_live_escapes_current_year_in_both_popup_branches():
    """The locked and unlocked branches each had one bare `currentYear`."""
    js = _read_js('timetable_live.js')

    assert js.count("esc(currentYear) + ' / الفصل '") == 2
    assert "' — ' + currentYear + ' / الفصل '" not in js


def test_timetable_live_borrows_the_shared_escaper():
    """It declares no escaper of its own, so the shared one is the only guard.

    This is why the `'` fix in shared/timetable_helpers.js also hardens every
    timetable view: `esc` is re-bound from `H.esc` on both boot and refresh.
    """
    js = _read_js('timetable_live.js')

    assert 'var esc = H.esc' in js
    assert 'esc = H.esc;' in js


def test_exam_print_sheets_escape_dates_and_exam_period():
    js = _read_js('exams/workspace.js')

    assert 'escapeHtml(ar)' in js
    assert 'escapeHtml(semStart)' in js
    assert 'escapeHtml(semEnd || \'\')' in js
    assert 'escapeHtml(week)' in js


@pytest.mark.skipif(NODE is None, reason='node is not installed')
def test_shared_timetable_escaper_escapes_apostrophe():
    """timetable_helpers.js used split('"'), leaving `'` raw."""
    source = _extract_function(_read_js('shared/timetable_helpers.js'), 'esc')
    assert _run_in_node(source, _call('_esc', "'"), '_esc') == '&#39;'


# --------------------------------------------------------------------------
# 3. Regressions guarding the audit itself.
# --------------------------------------------------------------------------

def test_no_new_unescaped_innerhtml_of_raw_fields_in_fixed_files():
    """Belt-and-braces sweep over the files this audit touched.

    Fails if a raw `+ someVar +` is concatenated straight into a markup string
    for the field names that were reachable from stored data.
    """
    watched = {
        'toast.js': ['message'],
        'courses_list.js': ['d.name', 'c.requires'],
        'teachers_assign.js': ['t.name', 't.academic_number'],
        'teachers_teaching_record_standalone_dept.js': ['t.name'],
        'faculty_performance_select_report.js': ['c.name', 'c.code', 't.name'],
        'faculty_performance_edit_assignments.js': ['t.name'],
        'courses_create.js': ['c.name', 'c.code'],
    }

    for rel_path, fields in watched.items():
        js = _read_js(rel_path)
        for field in fields:
            for line in js.splitlines():
                stripped = line.strip()
                if not stripped.startswith(("'", '"')):
                    continue
                for bare in ('+ {} +'.format(field), '+ {} +'.format(field.replace('.', ''))):
                    assert bare not in stripped or 'esc({})'.format(field) in stripped, (
                        '{}: raw interpolation of {} -> {}'.format(rel_path, field, stripped)
                    )
