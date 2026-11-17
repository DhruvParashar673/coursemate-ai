"""Shared RAG context helpers, used by /ask (Module 5) and the AI learning features (Module 6).

Everything here is scoped by user_id AND course_id. "Usable" always means: the chunk belongs to a document
that is `ready` and owned by this user in this course (one scoped MongoDB lookup, which also resolves the
original filename). Chunks of processing / failed / deleting / orphaned / foreign documents never pass.
"""
import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, TypeVar

from bson import ObjectId

from app.core.database import get_database
from app.rag import retrieval, vector_store
from app.rag.vector_store import RetrievedChunk
from app.schemas.qa import Citation
from app.services.document import DOCUMENTS_COLLECTION, DocumentError, DocumentNotFoundError


class SourceChunk(Protocol):
    document_id: str
    page_number: int
    text: str


T = TypeVar("T", bound=SourceChunk)


class DocumentNotReadyError(DocumentError):
    status_code = 409
    default_detail = "The document is not ready yet; try again once it has finished processing"


class InvalidPageRangeError(DocumentError):
    status_code = 422
    default_detail = "Invalid page range"


class ScopeTooLargeError(DocumentError):
    status_code = 422
    default_detail = "The selected page range is too large"


# ----------------------------------------------------------------------------- prompt hygiene

_FENCE_BREAKER = re.compile(r"<(?=/?\s*(?:source|question)\b)", re.IGNORECASE)


def fence_safe(text: str) -> str:
    """Stop document text from forging </source> or <question> tags (prompt-injection hygiene)."""
    return _FENCE_BREAKER.sub("\u2039", text)


# ----------------------------------------------------------------------------- citations / budget


def build_citations(chunks: Sequence[SourceChunk], filenames: dict[str, str]) -> list[Citation]:
    """One citation per (document, page), in order of first appearance. Only documents present in
    `filenames` (i.e. ready and owned) can ever be cited."""
    seen: set[tuple[str, int]] = set()
    citations: list[Citation] = []
    for chunk in chunks:
        key = (chunk.document_id, chunk.page_number)
        if key in seen or chunk.document_id not in filenames:
            continue
        seen.add(key)
        citations.append(
            Citation(document_id=chunk.document_id, filename=filenames[chunk.document_id], page_number=chunk.page_number)
        )
    return citations


def fit_budget(chunks: Sequence[T], budget: int) -> list[T]:
    """Best-ranked chunks first, stop before the context budget is exceeded (at least one is kept)."""
    selected: list[T] = []
    used = 0
    for chunk in chunks:
        if selected and used + len(chunk.text) > budget:
            break
        selected.append(chunk)
        used += len(chunk.text)
    return selected


def _even_indices(count: int, n: int) -> list[int]:
    if n >= count:
        return list(range(count))
    if n == 1:
        return [0]
    return sorted({round(i * (count - 1) / (n - 1)) for i in range(n)})


def sample_to_budget(chunks: Sequence[T], budget: int) -> list[T]:
    """Reading-ordered chunks -> a subset that fits `budget` characters.

    If everything fits it is returned unchanged; otherwise evenly spaced chunks (always including the first
    and, where possible, the last) are kept so the whole range stays represented."""
    items = list(chunks)
    if len(items) <= 1 or sum(len(c.text) for c in items) <= budget:
        return items
    average = sum(len(c.text) for c in items) / len(items)
    n = max(1, min(len(items), int(budget // average)))
    while True:
        picked = [items[i] for i in _even_indices(len(items), n)]
        if n == 1 or sum(len(c.text) for c in picked) <= budget:
            return picked
        n -= 1


def _pack(chunks: Sequence[T], budget: int) -> list[list[T]]:
    """Greedy, order-preserving packing into contiguous groups of at most `budget` characters
    (a single chunk larger than the budget forms its own group)."""
    groups: list[list[T]] = []
    current: list[T] = []
    used = 0
    for chunk in chunks:
        if current and used + len(chunk.text) > budget:
            groups.append(current)
            current, used = [], 0
        current.append(chunk)
        used += len(chunk.text)
    if current:
        groups.append(current)
    return groups


def _balanced(chunks: Sequence[T], group_count: int, budget: int) -> list[list[T]]:
    """Re-split into the same number of contiguous groups with near-equal character loads: each cut is
    placed where the cumulative size is closest to k/group_count of the total. Every group is still
    <= budget (otherwise the plain greedy packing is kept), so each LLM call carries a similar load and the
    chapter is covered evenly."""
    cumulative: list[int] = []
    running = 0
    for chunk in chunks:
        running += len(chunk.text)
        cumulative.append(running)
    total = running
    cuts: list[int] = []
    previous = 0
    for k in range(1, group_count):
        low, high = previous + 1, len(chunks) - (group_count - k)  # leave >= 1 chunk for every later group
        if low > high:
            return _pack(chunks, budget)
        target = total * k / group_count
        previous = min(range(low, high + 1), key=lambda i: abs(cumulative[i - 1] - target))
        cuts.append(previous)
    bounds = [0, *cuts, len(chunks)]
    groups = [list(chunks[a:b]) for a, b in zip(bounds, bounds[1:])]
    if any(sum(len(c.text) for c in group) > budget for group in groups):
        return _pack(chunks, budget)
    return groups


def plan_groups(chunks: Sequence[T], budget: int, max_groups: int) -> tuple[list[list[T]], bool]:
    """Split reading-ordered chunks into at most `max_groups` contiguous, near-equal groups, each within
    `budget` characters (one LLM call each). If the text cannot fit, it is thinned evenly (see
    sample_to_budget) until it does. Returns (groups, thinned)."""
    original = list(chunks)
    kept = original
    groups = _pack(kept, budget)
    thinned = len(groups) > max_groups
    if thinned:
        allowance = budget * max_groups
        while True:  # terminates: the allowance shrinks until one group (or one chunk) remains
            allowance = int(allowance * 0.95)
            kept = sample_to_budget(original, allowance)
            groups = _pack(kept, budget)
            if len(groups) <= max_groups:
                break
    if len(groups) > 1:
        groups = _balanced(kept, len(groups), budget)
    return groups, thinned


# ----------------------------------------------------------------------------- MongoDB (always user + course scoped)


def _scope(user_id: str, course_id: str) -> dict:
    if not isinstance(user_id, str) or not user_id or not isinstance(course_id, str) or not course_id:
        raise ValueError("user_id and course_id are required")
    return {"user_id": user_id, "course_id": course_id}


async def require_ready_document(user_id: str, course_id: str, document_oid: ObjectId) -> dict:
    """The document record (status, page_count, original_filename) if it is ready and in scope.
    DocumentNotFoundError (404) if missing / not yours; DocumentNotReadyError (409) if not ready."""
    doc = await get_database()[DOCUMENTS_COLLECTION].find_one(
        {"_id": document_oid, **_scope(user_id, course_id)},
        projection={"status": 1, "page_count": 1, "original_filename": 1},
    )
    if doc is None:
        raise DocumentNotFoundError
    if doc["status"] != "ready":
        raise DocumentNotReadyError
    return doc


async def ready_filenames(user_id: str, course_id: str, document_ids: set[str]) -> dict[str, str]:
    """document_id -> original_filename for READY documents of this user + course only.
    Anything else (processing, failed, deleting, orphaned, another user's/course's) is absent."""
    oids = [ObjectId(d) for d in document_ids if ObjectId.is_valid(d)]
    if not oids:
        return {}
    cursor = get_database()[DOCUMENTS_COLLECTION].find(
        {"_id": {"$in": oids}, **_scope(user_id, course_id), "status": "ready"},
        projection={"original_filename": 1},
    )
    return {str(doc["_id"]): doc["original_filename"] async for doc in cursor}


# ----------------------------------------------------------------------------- retrieval (topic / question mode)


async def retrieve_ready_chunks(
    user_id: str,
    course_id: str,
    query: str,
    document_oid: ObjectId | None,
    top_k: int,
    min_score: float,
) -> tuple[list[RetrievedChunk], dict[str, str]]:
    """Vector search via app.rag.retrieval.search_chunks, then keep only chunks of READY documents of this
    user + course. Returns (best-first chunks, document_id -> filename). The caller checks course ownership
    (and the optional document) beforehand."""
    # Over-fetch: chunks of non-ready documents (rare, transient) are dropped below without starving the result.
    fetch_k = min(max(top_k * 3, top_k + 10), 60)
    hits = await asyncio.to_thread(
        retrieval.search_chunks, user_id, course_id, query, fetch_k, str(document_oid) if document_oid else None
    )
    filenames = await ready_filenames(user_id, course_id, {h.document_id for h in hits})
    usable = [h for h in hits if h.document_id in filenames and h.score >= min_score][:top_k]
    return usable, filenames


# ----------------------------------------------------------------------------- document mode (page range)


@dataclass(frozen=True)
class ContextBundle:
    chunks: list[RetrievedChunk]  # reading order
    filenames: dict[str, str]
    total_chunks: int  # chunks available in the requested range
    sampled: bool  # True if the range had to be thinned to fit the context budget
    start_page: int  # the resolved page range (defaults applied)
    end_page: int


async def resolve_document_context(
    user_id: str,
    course_id: str,
    document_oid: ObjectId,
    start_page: int | None,
    end_page: int | None,
    budget: int,
    max_pages: int,
) -> ContextBundle:
    """A document's chunks for a page range ("chapter"), in reading order, thinned evenly to `budget`
    characters. The caller checks course ownership. Raises DocumentNotFound/NotReady (404/409) and
    InvalidPageRange/ScopeTooLarge (422)."""
    doc = await require_ready_document(user_id, course_id, document_oid)
    page_count = doc["page_count"]
    start = 1 if start_page is None else start_page
    end = page_count if end_page is None else end_page
    if not (1 <= start <= end <= page_count):
        raise InvalidPageRangeError(f"Pages must be between 1 and {page_count}, with start <= end")
    if end - start + 1 > max_pages:
        raise ScopeTooLargeError(f"Select at most {max_pages} pages at a time")

    chunks = await asyncio.to_thread(
        vector_store.get_document_chunks, user_id, course_id, str(document_oid), start, end
    )
    selected = sample_to_budget(chunks, budget)
    return ContextBundle(
        chunks=selected,
        filenames={str(document_oid): doc["original_filename"]},
        total_chunks=len(chunks),
        sampled=len(selected) < len(chunks),
        start_page=start,
        end_page=end,
    )
