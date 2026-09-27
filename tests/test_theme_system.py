"""Smoke tests for the appearance (theme) layer.

Covers the contract that static/js/theme.js and
templates/shared/components/theme_init.html must both honour:

  * theme_init.html runs before paint and sets data-theme plus the Tailwind
    `dark` class, so a dark-mode user never sees a white flash.
  * the appearance panel is reachable from the app shell and its controls are
    wired to window.themeManager.
  * theme-custom.css is imported after dark.css so a custom accent wins.
"""

import re

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema
from tests.test_bottom_nav import _client_for, _user_id


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    """Minimal DB with the office_manager user the client helper expects."""
    db_path = tmp_path / 'theme.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) "
        "VALUES ('office_manager', 'x', 'faculty_affairs', 'مدير مكتب')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, "
        "has_sections, type) VALUES ('قسم الحاسوب', 8, 8, 0, 1, 'academic')"
    )
    dept_id = conn.execute(
        "SELECT id FROM departments WHERE name='قسم الحاسوب'"
    ).fetchone()['id']
    conn.execute(
        "INSERT OR IGNORE INTO timetable_versions (department_id, semester, "
        "semester_code, status) VALUES (?, 2, 'fall_2026', 'active')",
        (dept_id,),
    )
    conn.commit()
    conn.close()
    return str(db_path)


@pytest.fixture
def client(app_fx, db_fx):
    return _client_for(
        app_fx, _user_id(db_fx, 'office_manager'), 'faculty_affairs', 'office_manager'
    )


def _css():
    with open('static/css/app.css', encoding='utf-8') as fh:
        return fh.read()


def test_theme_init_runs_before_first_paint():
    """The no-flash script must sit in <head> ahead of the Tailwind CDN."""
    with open('templates/shared/components/head_preamble.html', encoding='utf-8') as fh:
        head = fh.read()
    init_at = head.find('theme_init.html')
    tailwind_at = head.find('cdn.tailwindcss.com')
    assert init_at != -1, 'theme_init.html is not included in head_preamble'
    assert tailwind_at != -1, 'Tailwind CDN include disappeared'
    assert init_at < tailwind_at, (
        'theme_init must be included before the Tailwind CDN script so the '
        'dark class is present when Tailwind generates its utilities'
    )


def test_theme_init_mirrors_data_theme_onto_dark_class():
    """Tailwind is configured with darkMode:'class'; without the mirrored
    class every dark: utility in the templates stays inert."""
    with open(
        'templates/shared/components/theme_init.html', encoding='utf-8'
    ) as fh:
        src = fh.read()
    assert "data-theme" in src
    assert "classList.toggle('dark'" in src
    assert re.search(r"setAttribute\('data-theme-mode'", src)
    assert re.search(r"setAttribute\('data-density'", src)
    assert re.search(r"setAttribute\('data-corner'", src)


def test_theme_manager_owns_all_four_modes():
    with open('static/js/theme.js', encoding='utf-8') as fh:
        src = fh.read()
    for mode in ('light', 'dark', 'system', 'custom'):
        assert "'%s'" % mode in src, 'mode %s is missing from theme.js' % mode
    # The quick toggle must stay a two-state flip for the topbar button.
    assert 'window.toggleTheme' in src
    # Reading the OS preference has to be live, not a one-shot at load.
    assert "prefers-color-scheme: dark" in src
    assert 'addEventListener' in src


def test_custom_theme_font_controls_use_valid_persisted_manager_settings():
    with open('static/js/theme.js', encoding='utf-8') as fh:
        manager = fh.read()
    with open('static/js/theme_panel.js', encoding='utf-8') as fh:
        panel_script = fh.read()
    with open('templates/shared/components/theme_panel.html', encoding='utf-8') as fh:
        panel = fh.read()
    with open('templates/shared/components/theme_init.html', encoding='utf-8') as fh:
        init = fh.read()
    with open('static/css/base/typography.css', encoding='utf-8') as fh:
        typography = fh.read()

    for family in ('Cairo', 'Tajawal', 'Almarai', 'IBM Plex Sans Arabic', 'Noto Kufi Arabic'):
        assert f'<option value="{family}">' in panel
        assert family in manager
    assert 'setFontFamily' in manager
    assert 'setFontSize' in manager
    assert 'fontFamily' in manager and 'fontSize' in manager
    assert 'data-theme-font-family' in panel_script
    assert 'data-theme-font-size' in panel_script
    assert "manager.setFontFamily('Cairo')" in panel_script
    assert 'fontFamily' in init and 'fontSize' in init
    assert '--user-font-family' in init
    assert '--user-font-size' in init
    assert 'Cairo:wght@' in typography
    assert 'IBM+Plex+Sans+Arabic:wght@' in typography
    assert 'Noto+Kufi+Arabic:wght@' in typography


def test_custom_accent_is_applied_to_filled_actions_only_with_computed_contrast():
    with open('static/js/theme.js', encoding='utf-8') as fh:
        manager = fh.read()
    with open('static/css/utilities/theme-custom.css', encoding='utf-8') as fh:
        css = fh.read()

    assert 'customButtonForeground' in manager
    assert 'relativeLuminance' in manager
    assert '--custom-button-fg' in manager
    assert '--custom-button-bg' in manager
    assert '[data-theme-mode="custom"] button.bg-primary' in css
    assert '[data-theme-mode="custom"] a.bg-primary' in css
    assert '[data-theme-mode="custom"] .theme-button' in css
    assert '[data-theme-mode="custom"] .bg-primary,' not in css
    assert '--primary: var(--user-accent)' not in css
    assert '--primary-faint: color-mix' not in css
    assert '--sidebar-active-bg: color-mix' not in css
    assert '--auth-brand-mid: var(--user-accent)' not in css


def test_all_role_dashboards_use_theme_aware_neutral_surfaces():
    dashboard_templates = (
        'dean.html',
        'exam_dept.html',
        'faculty_affairs.html',
        'hod.html',
        'rnd.html',
        'teacher.html',
        'visitor.html',
    )
    for filename in dashboard_templates:
        with open(f'templates/dashboard/{filename}', encoding='utf-8') as fh:
            source = fh.read()
        assert 'bg-white' not in source, f'{filename} has a fixed white dashboard surface'


def test_theme_js_loaded_before_base_sidebar():
    """base_sidebar.js no longer defines the toggles, so it must load after
    theme.js or the first paint would use a stale handler."""
    with open('templates/shared/layouts/base.html', encoding='utf-8') as fh:
        src = fh.read()
    theme_at = src.find('js/theme.js')
    sidebar_at = src.find('js/base_sidebar.js')
    assert theme_at != -1, 'theme.js is not included in base.html'
    assert sidebar_at != -1
    assert theme_at < sidebar_at

    with open('static/js/base_sidebar.js', encoding='utf-8') as fh:
        sidebar_src = fh.read()
    assert not re.search(r'window\.applyTheme\s*=', sidebar_src), (
        'base_sidebar.js still defines applyTheme and would shadow theme.js'
    )
    assert not re.search(r'window\.toggleTheme\s*=', sidebar_src), (
        'base_sidebar.js still defines toggleTheme and would shadow theme.js'
    )


def test_custom_css_imports_after_both_palettes():
    """theme-custom.css must win over light.css and dark.css by source order."""
    css = _css()
    custom_at = css.find('utilities/theme-custom.css')
    assert custom_at != -1, 'theme-custom.css is not imported by app.css'
    assert css.find('themes/light.css') < custom_at
    assert css.find('themes/dark.css') < custom_at
    # Still ahead of the mobile override layer, which has to stay last.
    assert custom_at < css.find('layout/mobile.css')


def test_appearance_panel_is_reachable_and_wired(client):
    body = client.get('/timetable/department').get_data(as_text=True)
    assert 'popovertarget="themePanel"' in body, 'no trigger for the panel'
    assert 'id="themePanel"' in body, 'panel markup is missing'
    assert 'js/theme_panel.js' in body
    # Native radios keep arrow-key group navigation for free.
    for name in ('theme-mode', 'theme-density', 'theme-corner'):
        assert 'name="%s"' % name in body
    # All four modes must be offered, including the two that did not exist.
    for value in ('light', 'dark', 'system', 'custom'):
        assert 'value="%s"' % value in body


def test_theme_panel_is_reachable_from_user_menu_not_sidebar(client):
    body = client.get('/timetable/department').get_data(as_text=True)
    user_menu_start = body.index('id="userMenu"')
    user_menu_end = body.index('</form>', user_menu_start) + len('</form>')
    user_menu = body[user_menu_start:user_menu_end]

    assert 'popovertarget="themePanel"' in user_menu
    assert 'id="sidebarMoreGroup"' not in body
    assert 'خيارات إضافية' not in body


def test_additional_navigation_items_are_in_user_menu(client):
    body = client.get('/timetable/department').get_data(as_text=True)
    user_menu_start = body.index('id="userMenu"')
    user_menu_end = body.index('</form>', user_menu_start) + len('</form>')
    user_menu = body[user_menu_start:user_menu_end]

    for label in ('سجل التغييرات', 'الأقسام', 'القاعات'):
        assert label in user_menu


def test_user_settings_dropdown_contains_profile_theme_and_single_logout(client):
    body = client.get('/timetable/department').get_data(as_text=True)

    assert 'id="userMenuDropdown"' in body
    assert 'id="userMenuBtn"' in body
    assert 'href="/profile"' in body
    assert 'popovertarget="themePanel"' in body
    assert body.count('action="/logout"') == 1
    assert 'aria-controls="userMenu"' in body
    assert 'onclick="toggleRoleMenu()"' in body

    with open('templates/shared/layouts/base.html', encoding='utf-8') as fh:
        layout = fh.read()
    assert layout.count("url_for('auth.logout')") == 1

    with open('static/js/base_role_menu.js', encoding='utf-8') as fh:
        script = fh.read()
    assert 'window.toggleUserMenu' in script
    assert 'window.closeUserMenu' in script
    assert "e.key !== 'Escape'" in script


def test_topbar_quick_toggle_keeps_the_two_state_flip():
    """The topbar icon is only rendered on chrome-less pages (hide_sidebar),
    so assert it in the layout source rather than on a specific route."""
    with open('templates/shared/layouts/base.html', encoding='utf-8') as fh:
        src = fh.read()
    topbar_btn = re.search(r'<button[^>]*id="themeToggleTopbar"[^>]*>', src, re.S)
    assert topbar_btn, 'topbar quick toggle is missing from the layout'
    assert 'onclick="toggleTheme()"' in topbar_btn.group(0)
    assert 'data-theme-toggle' in topbar_btn.group(0), (
        'the quick toggle needs data-theme-toggle so theme.js can keep its '
        'aria-pressed state in sync'
    )


def test_print_never_inherits_the_dark_palette():
    """A dark-mode user printing a timetable used to get near-white text on
    white paper. The remap must live inside @media print and must beat
    dark.css even though app.css imports print/common.css earlier."""
    with open('static/css/print/common.css', encoding='utf-8') as fh:
        src = fh.read()
    block_at = src.find('@media print')
    assert block_at != -1, 'no @media print block in the print layer'
    remap = src[block_at:src.find('}', block_at)]
    assert 'color-scheme: light' in remap
    assert '--text-primary' in remap, 'text tokens are not remapped for print'
    assert '--surface' in remap

    with open('static/css/app.css', encoding='utf-8') as fh:
        css = fh.read()
    assert css.find('print/common.css') < css.find('themes/dark.css'), (
        'print/common.css is imported after dark.css; the !important remap is '
        'still correct but the ordering note in the file is now stale'
    )


def test_custom_accent_derives_from_theme_tokens():
    """The custom accent is built with color-mix against --surface / --text,
    so one definition stays legible in both palettes. If someone hardcodes a
    light-theme shade the dark variant silently loses contrast."""
    with open('static/css/utilities/theme-custom.css', encoding='utf-8') as fh:
        src = fh.read()
    custom_at = src.find('[data-theme-mode="custom"]')
    assert custom_at != -1, 'custom mode has no rules'
    assert 'color-mix(in oklab' in src, (
        'custom tokens should be mixed against the active theme tokens'
    )
    assert '--user-hue' in src, 'the hue slider has no variable to drive'


def test_reduced_motion_is_respected_globally():
    with open('static/css/utilities/theme-custom.css', encoding='utf-8') as fh:
        src = fh.read()
    assert 'prefers-reduced-motion: reduce' in src
    assert 'animation-duration' in src
