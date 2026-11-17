"""AI learning features. Step 1: structured-output plumbing + topic explanations.

Structured output: the model must return one JSON object. Each provider's raw text is validated; invalid or
truncated output makes llm.generate_answer fall through to the next provider. Citations are never taken from
model text: the model only names source NUMBERS, which are mapped onto the chunks that were actually supplied.
"""
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TypeVar

from bson import ObjectId
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.rag.vector_store import RetrievedChunk
from app.schemas.learning import (
    ExplanationOutput,
    ExplanationResponse,
    ImportantQuestion,
    ImportantQuestionsOutput,
    ImportantQuestionsResponse,
    Level,
    PageRange,
    SummaryLength,
    SummaryOutput,
    SummaryResponse,
)
from app.services import llm
from app.services.document import DocumentError, require_course
from app.services.learning_prompts import (
    build_explain_prompt,
    build_important_questions_prompt,
    build_map_prompt,
    build_reduce_prompt,
    build_summary_prompt,
)
from app.services.rag_context import (
    SourceChunk,
    build_citations,
    fit_budget,
    plan_groups,
    require_ready_document,
    resolve_document_context,
    retrieve_ready_chunks,
)

NO_CONTEXT_EXPLANATION = "I couldn't find enough information about this topic in the documents of this course."

M = TypeVar("M", bound=BaseModel)
T = TypeVar("T", bound=SourceChunk)

_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


# ----------------------------------------------------------------------------- structured-output plumbing


def extract_json_object(raw: str) -> dict | None:
    """The first JSON object in `raw` (tolerates ```json fences and a short preface). Truncated or malformed
    JSON returns None."""
    text = _FENCE.sub("", raw.strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def parse_structured(raw: str, model_cls: type[M]) -> M | None:
    data = extract_json_object(raw)
    if data is None:
        return None
    try:
        return model_cls.model_validate(data)
    except ValidationError:
        return None


async def generate_structured(
    system: str, user: str, model_cls: type[M], check: Callable[[M], bool] | None = None
) -> tuple[M, str]:
    """(validated output, provider). A provider whose output does not validate is skipped (fallback);
    `check` (optional) can reject output that parses but is unusable for this request, e.g. citations that
    point at nothing. LLMInvalidOutputError if none is acceptable, LLMUnavailableError if none answers."""

    def acceptable(text: str) -> bool:
        parsed = parse_structured(text, model_cls)
        return parsed is not None and (check is None or bool(check(parsed)))

    raw, provider = await llm.generate_answer(system, user, validate=acceptable)
    parsed = parse_structured(raw, model_cls)
    assert parsed is not None  # validate() already accepted this exact text
    return parsed, provider


X = TypeVar("X")


def pick_numbered(numbers: Sequence[int], items: Sequence[X]) -> list[X]:
    """Items the model says it used, validated against what was actually supplied (1-based numbers,
    out-of-range and duplicates ignored). If it named nothing valid, every supplied item is returned."""
    valid: list[int] = []
    for n in numbers:
        if 1 <= n <= len(items) and n not in valid:
            valid.append(n)
    return [items[n - 1] for n in valid] or list(items)


def select_cited(source_numbers: Sequence[int], context: Sequence[T]) -> list[T]:
    """Chunks the model says it used (see pick_numbered); if none valid, every supplied chunk is cited."""
    return pick_numbered(source_numbers, context)


# ----------------------------------------------------------------------------- explanations


def _no_context(provider: str | None) -> ExplanationResponse:
    return ExplanationResponse(
        explanation=NO_CONTEXT_EXPLANATION, key_points=[], example=None, provider=provider, grounded=False, citations=[]
    )


async def explain_topic(
    user_id: str, course_oid: ObjectId, topic: str, level: Level, document_id: str | None
) -> ExplanationResponse:
    settings = get_settings()
    await require_course(user_id, course_oid)  # 404 for missing OR someone else's course
    course_id = str(course_oid)

    document_oid = ObjectId(document_id) if document_id else None
    if document_oid is not None:
        await require_ready_document(user_id, course_id, document_oid)

    usable, filenames = await retrieve_ready_chunks(
        user_id, course_id, topic, document_oid, settings.LEARN_TOPIC_TOP_K, settings.QA_MIN_SCORE
    )
    context = fit_budget(usable, settings.LEARN_MAX_CONTEXT_CHARS)
    if not context:  # nothing to ground an explanation in: do not call an LLM at all
        return _no_context(provider=None)

    system, user = build_explain_prompt(topic, level, context)
    output, provider = await generate_structured(system, user, ExplanationOutput)  # may raise -> 503

    if output.insufficient:
        return _no_context(provider=provider)

    cited = select_cited(output.sources, context)
    return ExplanationResponse(
        explanation=output.explanation,
        key_points=output.key_points,
        example=output.example,
        provider=provider,
        grounded=True,
        citations=build_citations(cited, filenames),
    )


# ----------------------------------------------------------------------------- chapter summaries

NO_SUMMARY = "The selected pages do not contain enough information to summarize."


class NoTextInRangeError(DocumentError):
    status_code = 422
    default_detail = "The selected pages contain no text to summarize"


@dataclass(frozen=True)
class _Part:
    """One section's notes (map output) plus the chunks the model said it used for them."""

    number: int  # 1-based among the usable parts: this is what the reduce step refers to
    first_page: int
    last_page: int
    summary: str
    key_points: list[str]
    cited: list[RetrievedChunk]


def _clip(text: str, limit: int) -> str:
    """Cut at a word boundary so the reduce prompt stays inside the context budget."""
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0] or text[:limit]
    return cut.rstrip() + "\u2026"


def _no_summary(page_range: PageRange, partial: bool, calls: int, provider: str | None) -> SummaryResponse:
    return SummaryResponse(
        summary=NO_SUMMARY, key_points=[], page_range=page_range, partial=partial, llm_calls=calls,
        provider=provider, grounded=False, citations=[],
    )


async def summarize_chapter(
    user_id: str,
    course_oid: ObjectId,
    document_id: str,
    start_page: int | None,
    end_page: int | None,
    length: SummaryLength,
) -> SummaryResponse:
    """Summarise a page range ("chapter") of one ready document.

    Short ranges: one direct call. Long ranges: map-reduce, one "map" call per group of consecutive chunks (each
    within LEARN_MAX_CONTEXT_CHARS), then one "reduce" call over the section notes: at most
    LEARN_SUMMARY_MAX_MAP_CALLS + 1 calls. Ranges too dense for that are thinned evenly (partial=true).
    Every call is validated JSON with provider fallback; any failure is a clean 503 (no partial summary)."""
    settings = get_settings()
    await require_course(user_id, course_oid)  # 404 for missing OR someone else's course
    course_id = str(course_oid)
    per_call, max_calls = settings.LEARN_MAX_CONTEXT_CHARS, settings.LEARN_SUMMARY_MAX_MAP_CALLS

    # Raises 404 (not found / not yours), 409 (not ready), 422 (invalid range / too many pages).
    bundle = await resolve_document_context(
        user_id, course_id, ObjectId(document_id), start_page, end_page,
        budget=per_call * max_calls, max_pages=settings.LEARN_MAX_PAGES,
    )
    if not bundle.chunks:
        raise NoTextInRangeError
    groups, thinned = plan_groups(bundle.chunks, per_call, max_calls)
    partial = bundle.sampled or thinned
    page_range = PageRange(start_page=bundle.start_page, end_page=bundle.end_page)

    if len(groups) == 1:  # ---- direct: the whole range fits one call
        system, user = build_summary_prompt(length, groups[0])
        output, provider = await generate_structured(system, user, SummaryOutput)
        if output.insufficient:
            return _no_summary(page_range, partial, 1, provider)
        cited = select_cited(output.sources, groups[0])
        return SummaryResponse(
            summary=output.summary, key_points=output.key_points, page_range=page_range, partial=partial,
            llm_calls=1, provider=provider, grounded=True, citations=build_citations(cited, bundle.filenames),
        )

    # ---- map: notes for each section, in reading order
    parts: list[_Part] = []
    provider: str | None = None
    calls = 0
    for group in groups:
        system, user = build_map_prompt(group)
        output, provider = await generate_structured(system, user, SummaryOutput)
        calls += 1
        if output.insufficient:  # a section with nothing to summarise is skipped
            continue
        pages = [c.page_number for c in group]
        parts.append(_Part(len(parts) + 1, min(pages), max(pages), output.summary, output.key_points,
                           select_cited(output.sources, group)))
    if not parts:
        return _no_summary(page_range, partial, calls, provider)

    if len(parts) == 1:  # nothing to merge: the single section's notes are the summary
        only = parts[0]
        return SummaryResponse(
            summary=only.summary, key_points=only.key_points, page_range=page_range, partial=partial,
            llm_calls=calls, provider=provider, grounded=True, citations=build_citations(only.cited, bundle.filenames),
        )

    # ---- reduce: merge the notes (clipped so the prompt respects the context budget)
    limit = max(500, per_call // len(parts))
    system, user = build_reduce_prompt(
        length, [(p.number, p.first_page, p.last_page, _clip(p.summary, limit), p.key_points) for p in parts]
    )
    output, provider = await generate_structured(system, user, SummaryOutput)
    calls += 1
    if output.insufficient:
        return _no_summary(page_range, partial, calls, provider)
    used = pick_numbered(output.sources, parts)  # part numbers, validated; none valid -> all parts
    cited = [chunk for part in used for chunk in part.cited]
    return SummaryResponse(
        summary=output.summary, key_points=output.key_points, page_range=page_range, partial=partial,
        llm_calls=calls, provider=provider, grounded=True, citations=build_citations(cited, bundle.filenames),
    )


# ----------------------------------------------------------------------------- important questions

NO_QUESTIONS = "I couldn't find enough information in the selected content to write important questions."


def _usable_items(output: ImportantQuestionsOutput, source_count: int) -> list:
    """Items whose source number points at a chunk that was really supplied; duplicates removed (first wins)."""
    seen: set[str] = set()
    items = []
    for item in output.questions:
        key = " ".join(item.question.lower().split())
        if 1 <= item.source <= source_count and key not in seen:
            seen.add(key)
            items.append(item)
    return items


def _no_questions(provider: str | None, page_range: PageRange | None, partial: bool) -> ImportantQuestionsResponse:
    return ImportantQuestionsResponse(
        questions=[], page_range=page_range, partial=partial, provider=provider, grounded=False, message=NO_QUESTIONS
    )


async def generate_important_questions(
    user_id: str,
    course_oid: ObjectId,
    topic: str | None,
    document_id: str | None,
    start_page: int | None,
    end_page: int | None,
    count: int,
) -> ImportantQuestionsResponse:
    """Exam-style questions grounded in a document / page range (document mode) or in the best-matching
    chunks for a topic (topic mode). One LLM call; each question's citation is built server-side from the
    chunk whose number the model named, and questions without a valid source are dropped."""
    settings = get_settings()
    await require_course(user_id, course_oid)  # 404 for missing OR someone else's course
    course_id = str(course_oid)
    budget = settings.LEARN_MAX_CONTEXT_CHARS
    page_range: PageRange | None = None
    partial = False

    if topic is None:  # ---- document mode (document_id is guaranteed by the schema)
        bundle = await resolve_document_context(  # 404 / 409 / 422 as for summaries
            user_id, course_id, ObjectId(document_id), start_page, end_page,
            budget=budget, max_pages=settings.LEARN_MAX_PAGES,
        )
        if not bundle.chunks:
            raise NoTextInRangeError
        context, filenames, partial = bundle.chunks, bundle.filenames, bundle.sampled
        page_range = PageRange(start_page=bundle.start_page, end_page=bundle.end_page)
    else:  # ---- topic mode: same retrieval + ready-only filtering as /explanations
        document_oid = ObjectId(document_id) if document_id else None
        if document_oid is not None:
            await require_ready_document(user_id, course_id, document_oid)
        usable, filenames = await retrieve_ready_chunks(
            user_id, course_id, topic, document_oid, settings.LEARN_TOPIC_TOP_K, settings.QA_MIN_SCORE
        )
        context = fit_budget(usable, budget)
        if not context:  # nothing to ground questions in: do not call an LLM
            return _no_questions(None, None, False)

    system, user = build_important_questions_prompt(count, context, topic)
    n = len(context)
    output, provider = await generate_structured(
        system, user, ImportantQuestionsOutput, check=lambda o: o.insufficient or bool(_usable_items(o, n))
    )
    if output.insufficient:
        return _no_questions(provider, page_range, partial)

    questions: list[ImportantQuestion] = []
    for item in _usable_items(output, n):
        citations = build_citations([context[item.source - 1]], filenames)  # only ready, owned documents
        if citations:
            questions.append(ImportantQuestion(
                question=item.question, type=item.type, why_important=item.why_important, citation=citations[0]
            ))
        if len(questions) == count:
            break
    if not questions:  # cannot happen after `check`, but never return ungrounded questions
        return _no_questions(provider, page_range, partial)
    return ImportantQuestionsResponse(
        questions=questions, page_range=page_range, partial=partial, provider=provider, grounded=True
    )
