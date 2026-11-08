import re
import unicodedata

# Invisible characters that only add noise (soft hyphen, zero-width space, word joiner, BOM).
# ZWJ/ZWNJ (U+200D/U+200C) are deliberately kept: they matter in Devanagari.
_NOISE_CHARS = dict.fromkeys(map(ord, "\u00ad\u200b\u2060\ufeff"), None)

_HYPHEN_LINE_BREAK = re.compile(r"(?<=\w)-[ \t]*\n[ \t]*(?=[a-z])")  # "exam-\nple" -> "example"
_PAGE_NUMBER_LINE = re.compile(r"\s*(?:page\s+)?\d{1,4}(?:\s*(?:/|of)\s*\d{1,4})?\s*", re.IGNORECASE)
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_INLINE_SPACE = re.compile(r"[ \t\f\v]+")


def clean_page_text(raw: str) -> str:
    """Normalise one page of extracted text. Returns "" if nothing meaningful remains.

    Paragraph breaks are kept ("\\n\\n"); single line-wrap newlines become spaces.
    """
    if not raw:
        return ""

    text = unicodedata.normalize("NFKC", raw)  # ligatures (ﬁ -> fi), NBSP -> space, full-width forms
    text = text.translate(_NOISE_CHARS)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch) != "Cc")  # NUL etc.
    text = _HYPHEN_LINE_BREAK.sub("", text)

    lines = [line for line in text.split("\n") if not _PAGE_NUMBER_LINE.fullmatch(line)]
    text = "\n".join(lines)

    paragraphs = []
    for paragraph in _PARAGRAPH_BREAK.split(text):
        joined = _INLINE_SPACE.sub(" ", " ".join(paragraph.split("\n"))).strip()
        if joined:
            paragraphs.append(joined)
    cleaned = "\n\n".join(paragraphs)

    return cleaned if any(ch.isalnum() for ch in cleaned) else ""
