"""Rewrite external <script src> tags in templates: hashed URLs + defer.

Why: every <script src> in a document has to move to `defer` together, or
their relative execution order inverts. Deferred scripts run in document
order, which is exactly the order the non-deferred tags ran in, so the
migration is order-preserving as long as it is complete. Partial migration
would make page scripts run before the shell scripts.

Transformations:
    src="{{ url_for('static', filename='js/x.js') }}"
        -> defer src="{{ static_asset('js/x.js') }}"
    src="/static/js/x.js"
        -> defer src="{{ static_asset('js/x.js') }}"
    src="{{ static_asset('js/x.js') }}"
        -> adds defer only

Third-party and inline scripts are reported but never rewritten automatically.

Usage: python scripts/harden_script_tags.py [--dry-run]
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / 'templates'

TAG_RE = re.compile(r'<script\b[^>]*\bsrc=[^>]*>', re.I)
URL_FOR_RE = re.compile(r"""src=["']\{\{\s*url_for\(\s*['"]static['"]\s*,\s*filename=['"]([^'"]+)['"]\s*\)\s*\}\}["']""")
HARDCODE_RE = re.compile(r"""src=["'](?:https?://[^'"]*/)?/static/([^'"]+)["']""")
STATIC_ASSET_RE = re.compile(r"""src=["']\{\{\s*static_asset\(""")
HAS_DEFER_RE = re.compile(r'\bdefer\b|\basync\b', re.I)


def target_for(filename: str) -> str | None:
    """Return the static_asset() path for a source file, or None to skip.

    Only css/ and js/ are in the build manifest. Images, fonts and uploads are
    served straight from /static/ and must keep a plain URL.
    """
    rel = filename.lstrip('/').replace('\\', '/')
    if rel.startswith('static/'):
        rel = rel[len('static/'):]
    if rel.startswith(('js/', 'css/')):
        return rel
    return None


def rewrite(tag: str) -> tuple[str, str | None]:
    """Return (new_tag, note). note is None when nothing changed."""
    match = URL_FOR_RE.search(tag)
    if match:
        rel = target_for(match.group(1))
        if rel is None:
            return tag, 'url_for(non-asset)'
        tag = URL_FOR_RE.sub(f'src="{{{{ static_asset(\'{rel}\') }}}}"', tag, count=1)
        return tag, 'url_for -> static_asset'

    match = HARDCODE_RE.search(tag)
    if match:
        rel = target_for(match.group(1))
        if rel is None:
            return tag, 'hardcoded(non-asset)'
        tag = HARDCODE_RE.sub(f'src="{{{{ static_asset(\'{rel}\') }}}}"', tag, count=1)
        return tag, 'hardcoded -> static_asset'

    if STATIC_ASSET_RE.search(tag):
        return tag, 'already static_asset'

    return tag, 'third-party'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    changed_files = 0
    changed_tags = 0
    skipped = []
    third_party = []

    for path in sorted(TEMPLATES.rglob('*.html')):
        original = path.read_text(encoding='utf-8')
        notes = []

        def repl(match: re.Match[str]) -> str:
            nonlocal changed_tags
            tag = match.group(0)
            new_tag, note = rewrite(tag)
            if note in {'url_for(non-asset)', 'hardcoded(non-asset)'}:
                skipped.append((path.relative_to(ROOT).as_posix(), match.start(), note))
            if note == 'third-party':
                third_party.append((path.relative_to(ROOT).as_posix(), new_tag.strip()))
            if new_tag != tag:
                changed_tags += 1
                notes.append(note)
            if not HAS_DEFER_RE.search(new_tag):
                # Insert defer right after <script so the diff reads cleanly.
                new_tag = re.sub(r'^<script\b', '<script defer', new_tag, count=1, flags=re.I)
                changed_tags += 1
                notes.append('+defer')
            return new_tag

        updated = TAG_RE.sub(repl, original)
        if updated != original:
            changed_files += 1
            if not args.dry_run:
                path.write_text(updated, encoding='utf-8')
            print(f'{"would update" if args.dry_run else "updated"}: '
                  f'{path.relative_to(ROOT).as_posix()}  [{", ".join(notes)}]')

    print(f'\n{changed_files} file(s), {changed_tags} edit(s)'
          f'{"  (dry run, nothing written)" if args.dry_run else ""}')

    if skipped:
        print(f'\n{len(skipped)} tag(s) left alone (not css/js, need no hashing):')
        for rel, _pos, note in skipped[:20]:
            print(f'  {rel}  {note}')

    if third_party:
        print(f'\n{len(third_party)} third-party tag(s) left for manual review:')
        for rel, tag in third_party:
            print(f'  {rel}  {tag}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
