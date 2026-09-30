"""Audit compiled CSS coverage against the classes the UI actually uses.

The Play CDN scanned the live DOM, so any class that reached the browser got
generated. The CLI can only see classes in its content globs, so a class that
is built at runtime (or lives outside the globs) silently loses its styling.
That failure is invisible in code review and looks like "the layout broke".

Reports:
  * classes used in templates/JS with no matching rule in the built CSS
  * how many Tailwind responsive variants (md:/lg:/xl:) survived the build
  * which source CSS files are missing from the bundle

Usage: python scripts/audit_css_coverage.py
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / 'templates'
STATIC_JS = ROOT / 'static' / 'js'
DIST = ROOT / 'static' / 'dist'

# Prefixes that indicate a Tailwind utility rather than a project class.
TAILWINDISH = re.compile(
    r'^(?:[a-z-]+:)*(?:'
    r'(?:bg|text|border|ring|fill|stroke|from|via|to|shadow|outline|decoration|accent|caret|divide|placeholder)-'
    r'|(?:p|px|py|pt|pb|pl|pr|m|mx|my|mt|mb|ml|mr|space|gap|w|h|min|max|inset|top|right|bottom|left|'
    r'z|order|col|row|grid|flex|order|leading|tracking|font|rounded|opacity|z|transition|duration|'
    r'ease|delay|animate|cursor|select|resize|appearance|overflow|object|aspect|translate|rotate|'
    r'scale|skew|filter|backdrop|pointer|visible|isolate|truncate|uppercase|lowercase|capitalize|'
    r'italic|underline|line-through|no-underline|block|inline|hidden|table|contents|list|'
    r'items|justify|self|place|content|divide|truncate|sr-only|container|prose)'
    r')[\w./\[\]%-]*$'
)

CLASS_ATTR = re.compile(r'class\s*=\s*["\']([^"\']*)["\']')
# Jinja conditionals inside class="" produce fragments like {{ 'bg-x' if y }}
JINJA_STRING = re.compile(r"""['"]([^'"]+)['"]""")

RESPONSIVE = ('sm:', 'md:', 'lg:', 'xl:', '2xl:')


def tokens_from_text(text: str) -> set[str]:
    found: set[str] = set()
    for raw in CLASS_ATTR.findall(text):
        # Drop Jinja control flow, keep literal class words.
        cleaned = re.sub(r'\{\{.*?\}\}|\{%.*?%\}', ' ', raw, flags=re.S)
        for word in cleaned.split():
            if re.fullmatch(r'[\w:/.\[\]%()-]+', word):
                found.add(word)
        for lit in JINJA_STRING.findall(raw):
            for word in lit.split():
                if re.fullmatch(r'[\w:/.\[\]%()-]+', word):
                    found.add(word)
    return found


def selectors_in(css: str) -> set[str]:
    """Every class token that appears as a selector component.

    Minified CSS escapes characters that are special inside a selector, so
    `bg-primary/10` ships as `.bg-primary\\/10` and `md:flex` as `.md\\:flex`.
    A naive `[\\w-]*` match silently truncates at the first escape and reports
    the class as missing when it is present, so escapes are consumed and then
    stripped.
    """
    found: set[str] = set()
    # `\\.` must be tried FIRST: a bare backslash is itself a legal member of
    # the negated class, so putting it second lets the class swallow the
    # backslash and leaves the escape to be cut off at the `:`.
    for raw in re.findall(r'\.((?:\\.|[^\s.,:>+~()[\]{}\\])+)', css):
        found.add(re.sub(r'\\(.)', r'\1', raw))
    return found


def main() -> int:
    manifest_path = DIST / 'manifest.json'
    if not manifest_path.exists():
        print('FATAL: static/dist/manifest.json is missing.')
        print('       The Play CDN was removed, so without a build there is no')
        print('       Tailwind CSS at all and the UI renders unstyled.')
        print('       Fix: npm install && npm run build')
        return 2
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))

    bundles = {}
    for key, value in manifest.get('css', {}).items():
        path = ROOT / 'static' / value.lstrip('/').replace('static/', '', 1)
        if not path.exists():
            path = DIST / value.rsplit('/', 1)[-1]
        bundles[key] = path.read_text(encoding='utf-8') if path.exists() else ''
        if not bundles[key]:
            print(f'FATAL: manifest points at a missing file: {value}')
            return 2

    app_css = bundles.get('app.css', '')

    used: set[str] = set()
    for path in list(TEMPLATES.rglob('*.html')) + list(STATIC_JS.rglob('*.js')):
        used |= tokens_from_text(path.read_text(encoding='utf-8', errors='replace'))

    # 1. responsive variants. Verify via the escaped selector, which is the
    # thing that actually has to be present for a desktop layout to apply.
    # Media-query syntax is re-written by the minifier, so counting @media
    # blocks is unreliable; count the selectors instead.
    print('=== desktop breakpoint coverage (markup usage vs built selectors) ===')
    available_all = (
        selectors_in(app_css)
        | selectors_in(bundles.get('spa.css', ''))
        | selectors_in(bundles.get('public.css', ''))
    )
    widths = {'sm': 640, 'md': 768, 'lg': 1024, 'xl': 1280, '2xl': 1536}
    for name, width in widths.items():
        used_n = len([c for c in used if c.startswith(name + ':')])
        if not used_n:
            print(f'  {name:<4} {width:<5} not used in markup')
            continue
        have_n = len([c for c in available_all if c.startswith(name + ':')])
        flag = 'OK' if have_n else 'MISSING <-- desktop layout breaks'
        print(f'  {name:<4} {width:<5} used={used_n:<4} built={have_n:<5} {flag}')

    # 2. class coverage
    available = available_all

    unresolved = sorted(c for c in used if c not in available)
    suspicious = [c for c in unresolved if TAILWINDISH.match(c)]

    print(f'\n=== class coverage ===')
    print(f'  distinct class tokens used : {len(used)}')
    print(f'  resolved by built CSS      : {len(used) - len(unresolved)}')
    print(f'  unresolved                 : {len(unresolved)}')
    print(f'  of those, Tailwind-shaped  : {len(suspicious)}  <-- real styling risk')

    if suspicious:
        print('\n  Tailwind-shaped classes with no rule (check each):')
        for cls in suspicious[:60]:
            print(f'    {cls}')

    if len(suspicious) > 60:
        print(f'    ... and {len(suspicious) - 60} more')

    return 0


if __name__ == '__main__':
    sys.exit(main())
