import re
from dataclasses import dataclass

_SENTENCE_END = re.compile(r"(?:[.!?\u0964][\"')\]]*\s)|\n\n")  # \u0964 = Devanagari danda


@dataclass(frozen=True)
class TextChunk:
    page_number: int
    start: int  # offsets into the cleaned page text; chunks of a page cover [0, len(text)) exactly
    end: int
    text: str


def _snap_end(text: str, start: int, hard_end: int, size: int, overlap: int) -> int:
    """Prefer ending at a sentence boundary, else at whitespace, else hard-split."""
    lower = start + max(overlap + 1, size // 2)  # guarantees forward progress
    window = text[lower:hard_end]
    matches = list(_SENTENCE_END.finditer(window))
    if matches:
        return lower + matches[-1].end()
    cut = max(window.rfind(" "), window.rfind("\n"), window.rfind("\t"))
    if cut >= 0:
        return lower + cut + 1
    return hard_end


def _snap_start(text: str, pos: int, end: int) -> int:
    """Move an overlap start forward to a word boundary so chunks don't begin mid-word."""
    if pos <= 0 or text[pos - 1].isspace() or text[pos].isspace():
        return max(pos, 0)
    for i in range(pos, end):
        if text[i].isspace():
            return i + 1
    return pos


def chunk_text(text: str, page_number: int, chunk_size: int, overlap: int) -> list[TextChunk]:
    """Sliding-window chunking of one page. Consecutive chunks overlap by ~`overlap` characters,
    and no part of the text is dropped between chunks."""
    if chunk_size < 4 or overlap < 0 or overlap > chunk_size // 2:
        raise ValueError("overlap must be between 0 and chunk_size // 2")

    n = len(text)
    chunks: list[TextChunk] = []
    start = 0
    while start < n:
        hard_end = min(start + chunk_size, n)
        end = n if hard_end == n else _snap_end(text, start, hard_end, chunk_size, overlap)
        piece = text[start:end].strip()
        if piece and any(ch.isalnum() for ch in piece):
            chunks.append(TextChunk(page_number=page_number, start=start, end=end, text=piece))
        if end >= n:
            break
        start = max(_snap_start(text, end - overlap, end), start + 1)
    return chunks


def chunk_pages(pages: list[tuple[int, str]], chunk_size: int, overlap: int) -> list[TextChunk]:
    """Chunk (page_number, cleaned_text) pairs; each chunk belongs to exactly one page."""
    chunks: list[TextChunk] = []
    for page_number, text in pages:
        chunks.extend(chunk_text(text, page_number, chunk_size, overlap))
    return chunks
