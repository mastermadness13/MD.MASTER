"""Sanitization gateway for untrusted user content.

Two dead dependencies (``bleach``, ``defusedxml``) were vendored in
``requirements.txt`` but never imported. This module is the single, tested
entry point that actually uses them:

- ``sanitize_string`` / ``clean_html`` — bleach-based HTML/text scrubbing.
- ``parse_xml_safe`` / ``iter_parse_xml_safe`` — defusedxml-based parsing that
  rejects entity expansion, external entities and external DTDs (XXE).

Policy notes:
- The app currently has NO sanctioned rich-text fields, so ``clean_html``
  strips *all* tags by default (plain text out). Rich text must be enabled
  explicitly per call site via ``SAFE_BASIC_TAGS``.
- XML parsing defaults to ``forbid_dtd=True`` — the strictest sane default for
  untrusted documents, on top of defusedxml's entity/external blocking.
"""

from __future__ import annotations

from xml.etree.ElementTree import ParseError as ElementTreeParseError

import bleach
from defusedxml import ElementTree as DefusedET
from defusedxml.common import DefusedXmlException

__all__ = [
    'SAFE_BASIC_TAGS',
    'clean_html',
    'sanitize_string',
    'parse_xml_safe',
    'iter_parse_xml_safe',
    'XML_FORBIDDEN',
]

# Untrusted input can't carry CSS: bleach 6 has no ``styles`` argument and
# would pass raw CSS to the attribute value without a CSS sanitizer.
_ATTRIBUTES = {'*': ['class', 'id', 'dir', 'lang', 'title']}

# Bleach's basic rich-text set, kept as the explicit opt-in for the day the
# app adopts a rich-text editor. Default policy stays tag-free.
SAFE_BASIC_TAGS = set(bleach.sanitizer.ALLOWED_TAGS)


def sanitize_string(text):
    """Strip all markup/control sequences, return trimmed plain text.

    Modeled on AI-Horde's worker-name scrubber: attacker-supplied names are
    reduced to harmless text before being stored or rendered.
    """
    if text is None:
        return ''
    return bleach.clean(str(text), tags=(), strip=True).strip()


def clean_html(raw, *, tags=None, attributes=None, protocols=None):
    """Sanitize untrusted HTML.

    ``tags=None`` (default) strips every tag, yielding plain text — the safe
    default for an app with no sanctioned rich-text fields. Opt into rich text
    by passing ``tags=SAFE_BASIC_TAGS`` and suitable attributes/protocols.
    Always strips (never escapes) disallowed markup, so output can be rendered
    without further escaping worry (the caller still escapes it on render).
    """
    if raw is None:
        return ''
    return bleach.clean(
        str(raw),
        tags=() if tags is None else tags,
        attributes=attributes or _ATTRIBUTES,
        protocols=protocols or ('http', 'https', 'mailto'),
        strip=True,
    )


# Exceptions that indicate the parser refused potentially-dangerous content.
XML_FORBIDDEN = (DefusedXmlException, ElementTreeParseError)


def parse_xml_safe(source):
    """Parse XML through defusedxml, refusing entity-expansion/XXE payloads.

    ``forbid_dtd=True``: even an unused external/system DTD declaration makes
    the document untrusted. Returns an ``xml.etree.ElementTree.Element``.
    Raises ``ValueError`` on anything defusedxml classifies as forbidden or
    unparseable, so callers get a uniform, safe failure instead of a
    half-parsed tree.
    """
    try:
        return DefusedET.fromstring(source, forbid_dtd=True)
    except XML_FORBIDDEN as exc:
        raise ValueError('Untrusted XML rejected') from exc


def iter_parse_xml_safe(source):
    """Iteratively parse XML like ``ET.iterparse`` but through defusedxml."""
    try:
        return DefusedET.iterparse(source, forbid_dtd=True)
    except XML_FORBIDDEN as exc:
        raise ValueError('Untrusted XML rejected') from exc