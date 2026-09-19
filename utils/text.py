"""Shared text normalization utilities.

Used by import scripts, diagnostic tools, and the deduplication migration
to ensure consistent Arabic name matching across the codebase.
"""

from __future__ import annotations

import re
import unicodedata

# ─────────────────────────────────────────────

# /     /     >---- ننضّم النصوص العربية لمطابقة الأسماء (همزة/تشكيل/مسافات)
def normalize_arabic_name(text) -> str:
    """Normalize Arabic text for name matching (hamza/diacritics/whitespace).

    This is a *comparison aid*, not an identity proof.  Two names that
    normalize to the same string *may* refer to different people.

    Handles:
      - Hamza variants: أ إ آ -> ا (alef)
      - Yeh/Waw hamza:  ؤ -> و, ئ ى -> ي
      - Diacritics:      stripped via NFKD decomposition
      - Whitespace:      collapsed to single spaces
    """
    # /     /     >---- إذا فاضي نرجع فاضي
    if not text:
        return ""
    s = str(text).strip()
    # /     /     >---- نوحّد أشكال الهمزة
    s = (
        s.replace("\u0623", "\u0627")   # أ ← ا
        .replace("\u0625", "\u0627")    # إ ← ا
        .replace("\u0622", "\u0627")    # آ ← ا
        .replace("\u0624", "\u0648")    # ؤ ← و
        .replace("\u0626", "\u064a")    # ئ ← ي
        .replace("\u0649", "\u064a")    # ى ← ي
    )
    # /     /     >---- نشيل التشكيل
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    # /     /     >---- نضغط المسافات الكثيرة لوحدة
    return re.sub(r"\s+", " ", s)

# ─────────────────────────────────────────────

# /     /     >---- القيم اللي تعتبر "ما فيش رقم أكاديمي"
_ACademic_NUMBER_SENTINELS = frozenset({
    "", "0", "\u063a\u064a\u0631 \u0645\u062d\u062f\u062f",  # غير محدد
    "\u2014", "-", "N/A", "null",
})

# ─────────────────────────────────────────────

# /     /     >---- ننضّم الرقم الأكاديمي: نشيل المسافات والقيم اللي تعتبر لا شيء
def normalize_academic_number(value: str | None) -> str | None:
    """Normalize academic_number: strip whitespace, collapse sentinels to None.

    Returns None for empty/invalid values, the stripped string otherwise.
    """
    # /     /     >---- إذا لا شيء نرجع لا شيء
    if value is None:
        return None
    s = str(value).strip()
    # /     /     >---- إذا في القائمة السنتينيل نرجع لا شيء
    if not s or s in _ACademic_NUMBER_SENTINELS:
        return None
    return s