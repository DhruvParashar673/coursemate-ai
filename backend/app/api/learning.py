from bson import ObjectId
from fastapi import APIRouter, Depends

from app.api.auth import get_current_user
from app.api.courses import valid_course_id
from app.schemas.auth import UserPublic
from app.schemas.learning import (
    ExplainRequest,
    ExplanationResponse,
    ImportantQuestionsRequest,
    ImportantQuestionsResponse,
    SummaryRequest,
    SummaryResponse,
)
from app.services import learning as learning_service

router = APIRouter(prefix="/courses/{course_id}", tags=["Learning"])

_ERRORS = {
    401: {"description": "Missing or invalid token"},
    404: {"description": "Course or document not found (or not yours)"},
    503: {"description": "Search index, embedding model or all LLM providers unavailable / invalid output"},
}


# `current_user` is declared first so authentication is always checked before anything else.
# DocumentError subclasses (404, 409, 422) are rendered by the handler registered in main.py.
@router.post(
    "/explanations",
    response_model=ExplanationResponse,
    responses={**_ERRORS, 409: {"description": "The selected document is still processing or failed"}},
)
async def explain_topic(
    payload: ExplainRequest,
    current_user: UserPublic = Depends(get_current_user),
    course_oid: ObjectId = Depends(valid_course_id),
):
    """Explain a topic using only this course's ready documents (optionally one document).

    `grounded=false` means the documents did not contain enough information; nothing is invented."""
    return await learning_service.explain_topic(
        current_user.id, course_oid, payload.topic, payload.level, payload.document_id
    )


@router.post(
    "/summaries",
    response_model=SummaryResponse,
    responses={
        **_ERRORS,
        409: {"description": "The document is still processing or failed"},
        422: {"description": "Invalid page range, range too large, or no text on the selected pages"},
    },
)
async def summarize_chapter(
    payload: SummaryRequest,
    current_user: UserPublic = Depends(get_current_user),
    course_oid: ObjectId = Depends(valid_course_id),
):
    """Summarise a page range ("chapter") of one ready document, in short / medium / detailed form.

    Long ranges are summarised section by section and merged (up to LEARN_SUMMARY_MAX_MAP_CALLS + 1 LLM calls);
    `partial=true` means a very dense range was thinned to respect the call/size limits."""
    return await learning_service.summarize_chapter(
        current_user.id, course_oid, payload.document_id, payload.start_page, payload.end_page, payload.length
    )


@router.post(
    "/important-questions",
    response_model=ImportantQuestionsResponse,
    responses={
        **_ERRORS,
        409: {"description": "The document is still processing or failed"},
        422: {"description": "Invalid scope or page range, range too large, or no text on the selected pages"},
    },
)
async def important_questions(
    payload: ImportantQuestionsRequest,
    current_user: UserPublic = Depends(get_current_user),
    course_oid: ObjectId = Depends(valid_course_id),
):
    """Exam-style important questions, each with a validated document + page citation.

    Document mode: `document_id` (+ optional `start_page` / `end_page`). Topic mode: `topic` (+ optional
    `document_id` filter). `grounded=false` means the content did not support any question."""
    return await learning_service.generate_important_questions(
        current_user.id, course_oid, payload.topic, payload.document_id,
        payload.start_page, payload.end_page, payload.count,
    )
