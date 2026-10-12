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

# ─────────────────────────────────────────────

# /     /     >---- طيّات إضافية للبحث المرن (ة، حروف فارسية، أرقام هندية)
_SEARCH_FOLD_EXTRA = {
    '\u0671': '\u0627',   # ٱ → ا
    '\u0629': '\u0647',   # ة → ه
    '\u06A9': '\u0643',   # ک → ك
    '\u06CC': '\u064A',   # ی → ي
    '\u06D5': '\u0647',   # ە → ه
    '\u06CD': '\u064A',   # ۍ → ي
    '\u06AF': '\u0643',   # گ → ك
    '\u067E': '\u0628',   # پ → ب
    '\u0686': '\u062C',   # چ → ج
    '\u0698': '\u0632',   # ژ → ز
}

# /     /     >---- نحيط: التطويل ومحارف الاتجاه غير المرئية
_STRIP_CHARS = frozenset('\u0640\u200b\u200c\u200d\u200e\u200f\ufeff')

# /     /     >---- الأرقام العربية الهندية والفارسية → ASCII
_DIGIT_FOLD = {
    base + i: str(i)
    for base in (0x0660, 0x06F0)
    for i in range(10)
}


# /     /     >---- طيّ نص عربي للبحث المرن (مرن وليس حرفياً)
def normalize_search_text(text) -> str:
    """Fold Arabic text for fuzzy, non-literal search comparison.

    Strictly a superset of :func:`normalize_arabic_name` (which is unchanged).
    Additionally folds taa-marbuta, Persian letterforms, tatweel, bidi marks
    and Arabic-Indic / Extended Arabic-Indic digits, and lowercases Latin
    text so SQLite's ASCII-only ``LIKE`` case folding also applies.

    Returns '' for falsy input, so ``normalize_search(NULL) LIKE '%x%'``
    is simply false rather than an error.
    """
    if not text:
        return ''
    # /     /     >---- نبدأ من التطبيع الأساسي (همزة/تشكيل/مسافات)
    s = normalize_arabic_name(text)
    # /     /     >---- نضيف طيّات البحث الإضافية
    s = ''.join(_SEARCH_FOLD_EXTRA.get(ch, ch) for ch in s)
    # /     /     >---- نشيل التطويل والمحارف غير المرئية
    s = ''.join(ch for ch in s if ch not in _STRIP_CHARS)
    # /     /     >---- نحوّل الأرقام الهندية إلى ASCII
    s = s.translate(_DIGIT_FOLD)
    # /     /     >---- نضغط المسافات ونخفض الحروف اللاتينية
    return re.sub(r'\s+', ' ', s).strip().lower()


# /     /     >---- نهرّب محارف LIKE حتى ما يصير البحث قنبلة wildcards
def escape_like(value) -> str:
    """Escape ``\\``, ``%`` and ``_`` so user input matches literally.

    NOTE: SQLite's ``LIKE`` has **no default escape character** — every
    emitted predicate MUST carry an explicit ``ESCAPE '\\'`` clause.
    """
    if not value:
        return ''
    return (str(value).replace('\\', '\\\\')
            .replace('%', '\\%').replace('_', '\\_'))