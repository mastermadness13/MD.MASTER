"""Guards for the compiled asset pipeline (`npm run build`).

These tests exist because the Tailwind Play CDN was removed from the app.
The CDN generated utilities at runtime by scanning the live DOM, so a class
that was built by Python, or assembled in JS, still got styled. A build-time
compile can only see its content globs, and nothing warns you when a class
falls outside them -- the page just renders unstyled, which reads as a layout
bug rather than a build bug.

Each test below pins one way that can silently go wrong.
"""

import json
import os
import re

import pytest

from tests.harness import get_app

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, 'static')
DIST = os.path.join(STATIC, 'dist')
MANIFEST = os.path.join(DIST, 'manifest.json')

pytestmark = pytest.mark.filterwarnings('ignore::DeprecationWarning')


def _manifest():
    if not os.path.exists(MANIFEST):
        pytest.fail(
            'static/dist/manifest.json is missing. The Play CDN was removed, so '
            'without a build there is no Tailwind and the UI renders unstyled. '
            'Run: npm install && npm run build'
        )
    with open(MANIFEST, encoding='utf-8') as handle:
        return json.load(handle)


def _built_path(url: str) -> str:
    rel = url.lstrip('/').replace('\\', '/')
    if rel.startswith('static/'):
        rel = rel[len('static/'):]
    return os.path.join(STATIC, rel.replace('/', os.sep))


# --------------------------------------------------------------------------
# The bundle must exist and be self-consistent
# --------------------------------------------------------------------------

def test_manifest_is_committed_not_ignored():
    """A fresh clone must contain the compiled CSS.

    The generic `dist/` ignore rule (a Python build-artifact rule) used to
    swallow static/dist/ as well. That shipped a UI with no Tailwind at all.
    """
    gitignore = os.path.join(ROOT, '.gitignore')
    if not os.path.exists(gitignore):
        pytest.skip('no .gitignore')
    with open(gitignore, encoding='utf-8') as handle:
        lines = [ln.strip() for ln in handle]
    assert '!static/dist/' in lines, (
        '.gitignore must re-include static/dist/; the compiled bundle is a '
        'deploy artefact, not a build artefact'
    )


@pytest.mark.parametrize('bucket', ['css', 'js'])
def test_every_manifest_entry_exists_on_disk(bucket):
    data = _manifest()
    assert data.get(bucket), f'manifest has no {bucket} entries'
    for name, url in data[bucket].items():
        path = _built_path(url)
        assert os.path.exists(path), f'{bucket}/{name} -> {url} does not exist'


def test_manifest_entries_are_content_hashed_and_unique():
    """Hashed names are what make the immutable cache header safe."""
    data = _manifest()
    for bucket in ('css', 'js'):
        for name, url in data[bucket].items():
            assert re.search(r'\.[0-9a-f]{6,}\.(css|js)$', url), (
                f'{bucket}/{name} -> {url} is not content-hashed'
            )
        assert len(set(data[bucket].values())) == len(data[bucket]), (
            f'duplicate output paths in {bucket}: two sources hashed the same'
        )


def test_built_css_has_no_relative_url_references():
    """After flattening 36 files into one, any relative url() would 404."""
    data = _manifest()
    for name, url in data['css'].items():
        with open(_built_path(url), encoding='utf-8') as handle:
            css = handle.read()
        bad = re.findall(r'url\(\s*["\']?(?!data:|https?:|//|/)([^)"\']+)', css)
        assert not bad, f'{name} has relative url() that breaks when bundled: {bad[:5]}'


def test_remote_font_imports_survive_at_the_top_of_the_bundle():
    """@import must precede all rules or the whole sheet is dropped."""
    data = _manifest()
    url = data['css']['app.css']
    with open(_built_path(url), encoding='utf-8') as handle:
        css = handle.read()
    assert '@import' in css, 'the Google Fonts @import was lost during bundling'
    first_rule = re.search(r'@import', css)
    assert first_rule and first_rule.start() < 2000, (
        '@import is no longer near the top of the bundle'
    )


# --------------------------------------------------------------------------
# The Play CDN must not creep back in
# --------------------------------------------------------------------------

def test_no_template_loads_the_tailwind_play_cdn():
    offenders = []
    for base, _dirs, files in os.walk(os.path.join(ROOT, 'templates')):
        for name in files:
            if not name.endswith('.html'):
                continue
            path = os.path.join(base, name)
            with open(path, encoding='utf-8', errors='replace') as handle:
                if 'cdn.tailwindcss.com' in handle.read():
                    offenders.append(os.path.relpath(path, ROOT))
    assert not offenders, (
        f'Tailwind Play CDN reintroduced in {offenders}; it defeats the whole '
        f'build and the inline config no longer applies'
    )


def test_tailwind_config_tokens_match_the_ported_jinja_config():
    """The JS config replaced an inline <script> config; they must agree.

    Three tokens (on-tertiary-container, on-surface-variant, inverse-primary)
    were silently lost during the port, which would have dropped the colour
    from every utility that references them.
    """
    js_path = os.path.join(ROOT, 'tailwind.config.js')
    legacy = os.path.join(ROOT, 'templates', 'shared', 'components', 'tailwind_config.html')
    if not (os.path.exists(js_path) and os.path.exists(legacy)):
        pytest.skip('config source missing')

    pair = re.compile(r'["\']([a-z0-9-]+)["\']\s*:\s*["\'](#[0-9a-fA-F]{3,8})["\']')

    with open(js_path, encoding='utf-8') as handle:
        js = dict(pair.findall(handle.read()))
    with open(legacy, encoding='utf-8', errors='replace') as handle:
        old = dict(pair.findall(handle.read()))

    missing = {k: v for k, v in old.items() if js.get(k) != v}
    assert not missing, (
        f'colour tokens present in tailwind_config.html but wrong or absent in '
        f'tailwind.config.js: {missing}'
    )


# --------------------------------------------------------------------------
# Classes Tailwind cannot discover on its own
# --------------------------------------------------------------------------

def test_python_emitted_classes_are_safelisted():
    """utils/format.py builds class strings in Python.

    No content glob can see them, so they have to be safelisted. This fails
    when a new status colour is added without updating the safelist.
    """
    config = os.path.join(ROOT, 'tailwind.config.js')
    with open(config, encoding='utf-8') as handle:
        js = handle.read()

    format_py = os.path.join(ROOT, 'utils', 'format.py')
    with open(format_py, encoding='utf-8', errors='replace') as handle:
        source = handle.read()

    # Scan for the tokens directly rather than pairing up quotes: a naive
    # "quoted literal" regex mis-pairs whenever an odd quote appears earlier in
    # the file and silently swallows the literals you are looking for.
    emitted = set(re.findall(
        r'(?<![\w-])(?:bg|text|border)-(?:surface-dim|on-surface-variant|'
        r'(?:green|yellow|blue|red)-(?:50|100|700))(?![\w-])',
        source,
    ))
    assert emitted, 'expected to find the class literals in utils/format.py'

    missing = []
    for cls in sorted(emitted):
        if cls in js:
            continue
        covered_by_pattern = (
            re.search(r'\^\(bg\|text\|border\)-\(green\|yellow\|blue\|red\)', js)
            and re.match(r'^(bg|text)-(green|yellow|blue|red)-(50|100|700)$', cls)
        )
        if not covered_by_pattern:
            missing.append(cls)
    assert not missing, (
        f'utils/format.py emits {missing} but tailwind.config.js does not safelist '
        f'them; those badges will render unstyled'
    )


# --------------------------------------------------------------------------
# Cascade order and responsive behaviour
# --------------------------------------------------------------------------

def test_responsive_breakpoints_are_present_in_the_bundle():
    """Desktop layout depends on these; a content-glob miss removes them
    silently and collapses the page to its phone layout."""
    data = _manifest()
    with open(_built_path(data['css']['app.css']), encoding='utf-8') as handle:
        css = handle.read()
    for variant in ('sm\\:', 'md\\:', 'lg\\:', 'xl\\:'):
        assert f'.{variant}' in css, f'no .{variant} variants were generated'


def test_mobile_overrides_stay_last_in_the_source_graph():
    """static/css/responsive/mobile.css must remain the final import.

    It wins specificity ties against the desktop rules on purpose. Moving it
    earlier in the graph would let desktop rules override the phone layout.
    """
    entry = os.path.join(STATIC, 'css', 'app.css')
    with open(entry, encoding='utf-8') as handle:
        imports = re.findall(r'@import\s+url\(["\']?([^"\')]+)', handle.read())
    assert imports, 'static/css/app.css no longer has an @import graph'
    assert 'mobile.css' in imports[-1], (
        f'mobile.css must be the last import, but the graph ends with {imports[-1]}'
    )


# --------------------------------------------------------------------------
# Cache headers
# --------------------------------------------------------------------------

def test_dist_is_immutable_and_source_assets_revalidate():
    """Hashed bundles cache forever; unhashed sources must revalidate.

    Checked against real responses, because the rule is applied by
    security_headers._harden_response and not exposed as a lookup helper.
    """
    data = _manifest()
    hashed = next(iter(data['css'].values()))
    client = get_app().test_client()

    dist = client.get(hashed)
    assert dist.status_code == 200, f'{hashed} -> {dist.status_code}'
    dist_cache = dist.headers.get('Cache-Control', '')
    assert 'immutable' in dist_cache, f'dist asset not immutable: {dist_cache!r}'
    assert 'max-age=31536000' in dist_cache, dist_cache

    source = client.get('/static/css/app.css')
    assert source.status_code == 200
    src_cache = source.headers.get('Cache-Control', '')
    assert 'immutable' not in src_cache, (
        f'source assets are not content-hashed, so they must not be immutable: {src_cache!r}'
    )
    assert 'must-revalidate' in src_cache, src_cache


def test_static_asset_helper_returns_hashed_urls():
    app = get_app()
    with app.test_request_context():
        from flask import render_template_string
        out = render_template_string("{{ static_asset('css/app.css') }}")
    assert '/static/dist/' in out and '.css' in out, out


def test_manifest_appearing_after_startup_is_picked_up(monkeypatch):
    """A dev server started *before* ``npm run build`` must recover on its own.

    ``create_app()`` reads the manifest once and captures it in a closure, so a
    long-running process that started while ``static/dist/`` was absent used to
    pin the empty result and keep serving unstyled source paths until someone
    noticed and restarted it. That is what made every timetable render blank on
    an already-running server.
"""
    import flask

    import app as app_module

    real = _manifest()
    empty = {'css': {}, 'js': {}, 'builtAt': None}
    state = {'built': False}

    def fake_loader(static_root):
        return dict(real) if state['built'] else dict(empty)

    monkeypatch.setattr(app_module, '_load_asset_manifest', fake_loader)

    # A bare app: create_app() can only be called once per process.
    bare = flask.Flask('asset_probe', root_path=ROOT)
    static_asset = app_module._make_static_asset_url(bare)

    with bare.test_request_context():
        first = static_asset('css/app.css')
        state['built'] = True  # `npm run build` finishes, server not restarted
        after = static_asset('css/app.css')

    assert first.startswith('/static/css/app.css'), first
    assert '/static/dist/' not in first, first
    assert '/static/dist/' in after, after
