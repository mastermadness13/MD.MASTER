"""Shared text normalization utilities.

Used by import scripts, diagnostic tools, and the deduplication migration
to ensure consistent Arabic name matching across the codebase.
"""

from __future__ import annotations

import re
import unicodedata


def normalize_arabic_name(text) -> str:
    """Normalize Arabic text for name matching (hamza/diacritics/whitespace).

    This is a *comparison aid*, not an identity proof.  Two names that
    normalize to the same string *may* refer to different people.

    Handles:
      - Hamza variants: \u0623 \u0625 \u0622 -> \u0627 (alef)
      - Yeh/Waw hamza:  \u0624 -> \u0648, \u0626 \u0649 -> \u064a
      - Diacritics:      stripped via NFKD decomposition
      - Whitespace:      collapsed to single spaces
    """
    if not text:
        return ""
    s = str(text).strip()
    s = (
        s.replace("\u0623", "\u0627")
        .replace("\u0625", "\u0627")
        .replace("\u0622", "\u0627")
        .replace("\u0624", "\u0648")
        .replace("\u0626", "\u064a")
        .replace("\u0649", "\u064a")
    )
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s)


# Sentinel values that should be treated as "no academic number"
_ACademic_NUMBER_SENTINELS = frozenset({
    "", "0", "\u063a\u064a\u0631 \u0645\u062d\u062f\u062f",  # غير محدد
    "\u2014", "-", "N/A", "null",
})


def normalize_academic_number(value: str | None) -> str | None:
    """Normalize academic_number: strip whitespace, collapse sentinels to None.

    Returns None for empty/invalid values, the stripped string otherwise.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s in _ACademic_NUMBER_SENTINELS:
        return None
    return s
