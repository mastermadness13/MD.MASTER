"""Tests for the bleach/defusedxml sanitization gateway (security/sanitize.py).

Locks down that the two vendored-but-dead dependencies are genuinely wired in
and behave safely:
  XSS: payloads in user-supplied text are neutralized before storage/render.
  XXE: entity-expansion / external-entity XML is refused, never half-parsed.
"""

import io

import pytest

from security.sanitize import (
    SAFE_BASIC_TAGS,
    clean_html,
    iter_parse_xml_safe,
    parse_xml_safe,
    sanitize_string,
)


# ── plain-text sanitization (sanitize_string) ──────────────────────────────


@pytest.mark.parametrize('payload', [
    '<script>alert(1)</script>',
    '<img src=x onerror=alert(1)>',
    '<svg onload=alert(1)>',
    '<a href="javascript:alert(1)">x</a>',
    '<iframe src="file:///etc/passwd">',
    '">&lt;html&gt;',
])
def test_sanitize_string_strips_markup(payload):
    out = sanitize_string(payload)
    assert '<' not in out
    assert '>' not in out
    assert 'javascript:' not in out.lower()


def test_sanitize_string_preserves_plain_text():
    out = sanitize_string('مرحبا بالعالم Hello world (مثال 123)!')
    assert out == 'مرحبا بالعالم Hello world (مثال 123)!'


def test_sanitize_string_none_and_blank():
    assert sanitize_string(None) == ''
    assert sanitize_string('   ') == ''
    assert sanitize_string(123) == '123'


# ── HTML sanitization (clean_html) ─────────────────────────────────────────


def test_clean_html_default_strips_all_tags():
    out = clean_html('<b>bold</b> <i>italic</i> plain')
    assert out == 'bold italic plain'
    assert '<' not in out and '>' not in out


def test_clean_html_opt_in_rich_text_keeps_basic_tags():
    out = clean_html('<b>ok</b><script>alert(1)</script><img src=x onerror=alert(1)>',
                     tags=SAFE_BASIC_TAGS)
    assert '<b>ok</b>' in out
    # Disallowed tags are stripped (harmless inner text may survive), and no
    # tag attribute/name carrying an execution vector survives.
    assert '<script' not in out.lower()
    assert '<img' not in out.lower()
    assert 'onerror' not in out.lower()
    assert 'javascript:' not in out.lower()


def test_clean_html_handles_none():
    assert clean_html(None) == ''


# ── XXE-safe XML parsing (defusedxml) ──────────────────────────────────────


_BILLION_LAUGHS = '''<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<root>&lol3;</root>'''

_EXTERNAL_ENTITY = '''<?xml version="1.0"?>
<!DOCTYPE root [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<root>&xxe;</root>'''

_EXTERNAL_DTD = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                 '<!DOCTYPE root SYSTEM "http://evil.example/dtd">\n'
                 '<root/>')


@pytest.mark.parametrize('malicious', [
    _BILLION_LAUGHS,
    _EXTERNAL_ENTITY,
    _EXTERNAL_DTD,
])
def test_parse_xml_safe_refuses_entity_attacks(malicious):
    with pytest.raises(ValueError):
        parse_xml_safe(malicious.encode('utf-8'))


def test_parse_xml_safe_parses_benign_xml():
    el = parse_xml_safe('<student id="7"><name>ليبي</name></student>'.encode('utf-8'))
    assert el.tag == 'student'
    assert el.get('id') == '7'
    assert el.findtext('name') == 'ليبي'


def test_parse_xml_safe_rejects_malformed_xml():
    with pytest.raises(ValueError):
        parse_xml_safe('<root><unclosed>'.encode('utf-8'))


def test_iter_parse_uses_defusedxml():
    events = list(iter_parse_xml_safe(io.BytesIO(b'<root><a>x</a></root>')))
    assert any(getattr(item, 'tag', '') == 'a' for _, item in events)
    with pytest.raises(ValueError):
        list(iter_parse_xml_safe(io.BytesIO(_EXTERNAL_ENTITY.encode('utf-8'))))