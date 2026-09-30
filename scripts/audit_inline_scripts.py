"""Audit inline <script> blocks in templates for parse-time use of deferred JS.

Why this exists: `defer` on the base scripts changes when they execute.
A deferred external script runs after HTML parsing but BEFORE
DOMContentLoaded; an inline <script> runs during parsing. So an inline block
that *invokes* a base-layer global at parse time would silently break.

The rule this checks is therefore narrow and precise:

    invoking a base global at parse time      -> breaks, must be wrapped
    referencing one inside a function body    -> fine, resolved at call time

A reference inside `function foo() {...}` or an event handler is not a hazard,
because the call can only happen after the user acts, which is long after
both the parse and the deferred scripts have finished.

Run:  python scripts/audit_inline_scripts.py     (exit 1 if anything breaks)
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / 'templates'

# Globals defined by the scripts the shared layouts load.
BASE_GLOBALS = [
    'showNotification', 'hideNotification', 'showToast',
    'askConfirm', 'toggleTheme', 'applyTheme',
    'toggleSidebar', 'closeSidebarMobile', 'toggleUserMenu', 'closeUserMenu',
    'toggleRoleMenu', 'openBottomSheet', 'closeBottomSheet', 'withBusy',
]

INLINE_RE = re.compile(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', re.S | re.I)
CALL_RE = re.compile(
    r'\b(?:window\.)?(' + '|'.join(re.escape(g) for g in BASE_GLOBALS) + r')\s*\('
)


def brace_depth_at(body: str, index: int) -> int:
    """Net brace nesting depth at `index`, ignoring braces in strings/comments."""
    depth = 0
    i = 0
    n = len(body)
    while i < index:
        ch = body[i]
        two = body[i:i + 2]
        if two == '//':
            i = body.find('\n', i)
            if i == -1:
                return depth
            continue
        if two == '/*':
            end = body.find('*/', i)
            if end == -1:
                return depth
            i = end + 2
            continue
        if ch in '\'"`':
            quote = ch
            i += 1
            while i < n:
                if body[i] == '\\':
                    i += 2
                    continue
                if body[i] == quote:
                    break
                i += 1
            i += 1
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
        i += 1
    return depth


def main() -> int:
    hazards = []
    reviewed = 0

    for path in sorted(TEMPLATES.rglob('*.html')):
        if path.name in {'theme_init.html', 'tailwind_config.html'}:
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        for match in INLINE_RE.finditer(text):
            body = match.group(1)
            if not body.strip():
                continue
            rel = path.relative_to(ROOT).as_posix()
            line = text[: match.start()].count('\n') + 1

            for call in CALL_RE.finditer(body):
                name = call.group(1)
                reviewed += 1
                depth = brace_depth_at(body, call.start())
                if depth == 0:
                    hazards.append((rel, line, name))

    print(f'scanned inline <script> blocks; {reviewed} base-global call site(s)')

    if not hazards:
        print('ok: no block invokes a base global at parse time — defer is safe.')
        return 0

    print(f'\n{len(hazards)} parse-time invocation(s) would break under defer:')
    for rel, line, name in hazards:
        print(f'  {rel}:{line}  {name}()')
    print(
        '\nWrap these in the readyState guard already used by\n'
        'shared/layouts/auth.html, or move them into the deferred bundle.'
    )
    return 1


if __name__ == '__main__':
    sys.exit(main())
