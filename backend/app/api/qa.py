from bson import ObjectId
from fastapi import APIRouter, Depends

from app.api.auth import get_current_user
from app.api.courses import valid_course_id
from app.schemas.auth import UserPublic
from app.schemas.qa import AskRequest, AskResponse
from app.services import qa as qa_service

router = APIRouter(prefix="/courses/{course_id}", tags=["Question answering"])


# `current_user` is declared first so authentication is always checked before anything else.
# DocumentError subclasses (404 course/document, 409 not ready) are rendered by the handler in main.py.
@router.post(
    "/ask",
    response_model=AskResponse,
    responses={
        401: {"description": "Missing or invalid token"},
        404: {"description": "Course or document not found (or not yours)"},
        409: {"description": "The selected document is still processing or failed"},
        503: {"description": "Search index, embedding model or all LLM providers unavailable"},
    },
)
async def ask_question(
    payload: AskRequest,
    current_user: UserPublic = Depends(get_current_user),
    course_oid: ObjectId = Depends(valid_course_id),
):
    """Answer a question using only this course's ready documents (optionally one document).

    `grounded=false` means the documents did not contain enough information; nothing is invented.
    """
    return await qa_service.answer_question(
        current_user.id, course_oid, payload.question, payload.document_id, payload.top_k
    )
