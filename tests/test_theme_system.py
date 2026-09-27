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
    assert "value=\"16\"" in panel
    assert 'min="12" max="22" step="0.5"' in panel
    assert 'fontFamily' in init and 'fontSize' in init
    assert '--user-font-family' in init
    assert '--user-font-size' in init
    assert 'Cairo:wght@' in typography
    assert 'IBM+Plex+Sans+Arabic:wght@' in typography
    assert 'Noto+Kufi+Arabic:wght@' in typography


def test_font_size_preference_scales_fixed_ui_and_official_report_text():
    with open('static/js/theme.js', encoding='utf-8') as fh:
        manager = fh.read()
    with open('templates/shared/components/theme_init.html', encoding='utf-8') as fh:
        init = fh.read()
    with open('static/css/utilities/theme-overrides.css', encoding='utf-8') as fh:
        overrides = fh.read()
    with open('templates/faculty_performance/_print_document.html', encoding='utf-8') as fh:
        print_layout = fh.read()
    with open('templates/faculty_performance/_official_document_styles.html', encoding='utf-8') as fh:
        official_styles = fh.read()

    assert "doc.style.fontSize = prefs.fontSize + 'px'" in manager
    assert "doc.style.fontSize = fontSize + 'px'" in init
    assert "body [class~=\"text-[11px]\"]" in overrides
    assert "body [class~=\"text-[40px]\"]" in overrides
    assert 'body [class~="file:text-[11px]"]::file-selector-button' in overrides
    assert "{% include 'shared/components/theme_init.html' %}" in print_layout
    assert "var(--user-font-family" in official_styles
    assert not re.search(r'font-size\s*:\s*\d+(?:\.\d+)?pt', official_styles)


def test_official_document_previews_keep_readable_paper_surface_in_dark_mode():
    with open('templates/faculty_performance/preview.html', encoding='utf-8') as fh:
        teacher_preview = fh.read()
    with open('templates/faculty_performance/report_course.html', encoding='utf-8') as fh:
        course_preview = fh.read()
    with open('templates/faculty_performance/_official_document_styles.html', encoding='utf-8') as fh:
        official_styles = fh.read()
    with open('templates/teachers/_course_content_doc.html', encoding='utf-8') as fh:
        course_content = fh.read()

    assert 'official-doc-paper bg-white text-black' in teacher_preview
    assert 'official-doc-paper bg-white text-black' in course_preview
    assert 'body .official-doc-paper {' in official_styles
    assert 'background: #fff;' in official_styles
    assert 'color-scheme: light;' in official_styles
    assert 'body .cc-sheet {' in course_content
    assert 'color: #111827;' in course_content


def test_theme_panel_range_labels_match_normalized_and_selected_values():
    with open('static/js/theme.js', encoding='utf-8') as fh:
        manager = fh.read()
    with open('static/js/theme_panel.js', encoding='utf-8') as fh:
        panel_script = fh.read()
    with open('templates/shared/components/theme_panel.html', encoding='utf-8') as fh:
        panel = fh.read()

    assert re.search(
        r'var hue = typeof prefs\.hue === \'number\' && isFinite\(prefs\.hue\)'
        r'\s*\?\s*Math\.max\(0, Math\.min\(359, Math\.round\(prefs\.hue\)\)\)'
        r'\s*:\s*280;\s*prefs\.hue = hue;',
        manager,
    )
    assert "each('[data-theme-hue-value]').forEach" in panel_script
    assert "output.textContent = prefs.hue + '°'" in panel_script
    assert "output.textContent = (prefs.fontSize || 16) + ' px'" in panel_script
    assert re.search(
        r'<input[^>]*type="range"[^>]*value="280"[^>]*data-theme-hue[^>]*>.*?'
        r'<output[^>]*data-theme-hue-value[^>]*>280°</output>',
        panel,
        re.S,
    )
    assert re.search(r'id="themeFontSize"[^>]*value="16"', panel)
    assert re.search(
        r'<output[^>]*data-theme-font-size-value[^>]*>16 px</output>',
        panel,
    )


def test_theme_panel_reference_controls_apply_and_persist_every_palette_group():
    with open('static/js/theme.js', encoding='utf-8') as fh:
        manager = fh.read()
    with open('static/js/theme_panel.js', encoding='utf-8') as fh:
        controller = fh.read()
    with open('templates/shared/components/theme_panel.html', encoding='utf-8') as fh:
        panel = fh.read()
    with open('static/css/utilities/theme-custom.css', encoding='utf-8') as fh:
        css = fh.read()
    with open('templates/shared/components/theme_init.html', encoding='utf-8') as fh:
        init = fh.read()

    for key, setter in (
        ('pageColor', 'setPageColor'),
        ('cardColor', 'setCardColor'),
        ('modalColor', 'setModalColor'),
        ('borderColor', 'setBorderColor'),
        ('textColor', 'setTextColor'),
        ('mutedColor', 'setMutedColor'),
        ('inverseTextColor', 'setInverseTextColor'),
        ('buttonColor', 'setButtonColor'),
        ('buttonStyle', 'setButtonStyle'),
    ):
        assert key in manager
        assert setter in manager
    for group in ('accent', 'cards', 'modal', 'buttons', 'background', 'borders', 'text', 'layout'):
        assert f'data-theme-accordion="{group}"' in panel
    for setting in (
        'pageColor', 'cardColor', 'modalColor', 'borderColor', 'textColor',
        'inverseTextColor', 'buttonColor',
    ):
        assert f'data-theme-color-input="{setting}"' in panel
        if setting != 'inverseTextColor':
            assert f'data-theme-color-preset="{setting}"' in panel
    assert 'data-theme-color-input="mutedColor"' in panel
    assert 'data-theme-contrast' in panel
    assert 'data-theme-live-preview' in panel
    assert 'data-theme-apply' in panel
    assert 'manager[config.setter]' in controller
    assert 'localStorage' in manager
    assert '--user-page-color' in init
    assert '--user-card-color' in init
    assert '--user-modal-color' in init
    assert '--user-border-color' in init
    assert '--user-modal-text-color' in init
    assert '--user-modal-muted-color' in init
    assert '--user-inverse-text-color' in init
    assert '--user-text-color' in init
    assert '--user-button-color' in init
    assert ':root[data-theme-mode="custom"][data-button-style="outline"]' in css
    assert '--text-primary: var(--user-modal-text-color' in css
    assert '--text-secondary: var(--user-modal-muted-color' in css
    assert 'readableColor' in manager and 'contrastRatio' in manager


def test_theme_light_and_dark_mode_selection_is_not_stuck_to_old_base():
    with open('static/js/theme.js', encoding='utf-8') as fh:
        manager = fh.read()

    assert "if (mode === 'light') return false;" in manager
    assert "if (next === 'light' || next === 'dark') prefs.base = next;" in manager


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
