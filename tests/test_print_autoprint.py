"""Opt-in auto-print on the dedicated /print/* routes.

Those routes keep their manual print buttons. static/js/print_auto.js opens the
dialog on arrival only when a URL explicitly includes ``?autoprint=1``.
"""

import re

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema
from tests.test_bottom_nav import _client_for, _user_id


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'printauto.db'
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


def _js():
    with open('static/js/print_auto.js', encoding='utf-8') as fh:
        return fh.read()


def test_auto_print_script_is_loaded_by_the_app_shell(client):
    body = client.get('/timetable/department').get_data(as_text=True)
    assert 'js/print_auto.js' in body


def test_gate_is_scoped_to_the_print_prefix():
    assert "var PREFIX = '/print/'" in _js()
    assert 'window.location.pathname' in _js()


def test_only_the_print_blueprint_owns_that_prefix():
    """The gate is a hardcoded string, so prove it matches exactly one
    blueprint and that the faculty-performance print route sits elsewhere."""
    prefixes = {}
    import glob
    import os
    for path in glob.glob('page_routes/*.py'):
        with open(path, encoding='utf-8') as fh:
            for match in re.finditer(
                r"Blueprint\(\s*'[^']+'\s*,\s*__name__\s*,\s*url_prefix='([^']+)'",
                fh.read(),
            ):
                prefixes[os.path.basename(path)] = match.group(1)

    owners = [name for name, prefix in prefixes.items() if prefix == '/print']
    assert owners == ['print_routes.py'], (
        'more than one blueprint now owns /print, so the auto-print gate would '
        'catch pages it was never reviewed against: %r' % owners
    )
    # The two-step preview -> print flow must stay outside the gate.
    assert prefixes['faculty_performance.py'] == '/faculty-performance'


def test_faculty_performance_print_is_not_auto_printed():
    """preview -> print is a deliberate two-step; collapsing it would print a
    form the user has not reviewed. The gate is purely positional, so the only
    thing to verify is that the route is not under /print/."""
    import glob
    import os
    for path in glob.glob('page_routes/*.py'):
        with open(path, encoding='utf-8') as fh:
            if "url_prefix='/faculty-performance'" in fh.read():
                break
    else:
        pytest.fail('the faculty_performance prefix changed; re-check the gate')
    assert not '/faculty-performance'.startswith('/print/')


def test_auto_print_requires_explicit_opt_in():
    js = _js()
    assert "'autoprift'" not in js
    assert "get('autoprint')" in js
    assert "flag !== '1'" in js
    assert 'data-no-autoprint' in js
    assert 'if (!shouldAutoPrint() || recentlyPrinted()) return;' in js


def test_refresh_does_not_reopen_the_dialog_in_the_users_face():
    """Without a cooldown, cancelling the dialog and hitting refresh would
    re-open it immediately, which reads as the page fighting the user."""
    js = _js()
    assert 'COOLDOWN_MS' in js
    assert 'sessionStorage' in js
    assert 'recentlyPrinted' in js


def test_waits_for_load_and_fonts_before_printing():
    """Printing before webfonts settle changes pagination and silently drops
    rows onto extra pages."""
    js = _js()
    assert "window.addEventListener('load', run)" in js
    assert 'document.fonts' in js


def test_printed_output_has_no_app_chrome():
    """Auto-print is only safe because the shared print layer already strips
    the shell. If that regresses, every /print page starts printing the
    sidebar."""
    with open('static/css/print/common.css', encoding='utf-8') as fh:
        css = fh.read()
    at = css.index('@media print')
    assert at != -1
    block = css[at:]
    for selector in ('aside.sidebar', 'header.app-header', '.no-print'):
        assert selector in block, (
            '%s is no longer hidden when printing; auto-print would emit the '
            'app shell' % selector
        )
    assert 'button[onclick="window.print()"]' in block, (
        'the print button itself is not suppressed in print output'
    )


def test_print_routes_still_offer_a_manual_print_button(client):
    """Auto-print must not remove the manual escape hatch, which is the only
    way to reprint without changing the URL. At least one /print page has to
    keep an explicit button."""
    resp = client.get('/print/timetable')
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'window.print()' in body, (
        'no manual print button on /print/timetable; auto-print alone leaves '
        'no way to reprint without re-navigating'
    )
