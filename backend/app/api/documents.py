import re

from bson import ObjectId
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.exceptions import RequestValidationError

from app.api.auth import get_current_user
from app.api.courses import valid_course_id
from app.schemas.auth import UserPublic
from app.schemas.document import DocumentPublic
from app.services import document as document_service

router = APIRouter(prefix="/courses/{course_id}/documents", tags=["Documents"])

_OBJECT_ID_RE = re.compile(r"[0-9a-fA-F]{24}")

_ERRORS = {
    401: {"description": "Missing or invalid token"},
    404: {"description": "Course or document not found (or not yours)"},
}


def valid_document_id(document_id: str) -> ObjectId:
    if not _OBJECT_ID_RE.fullmatch(document_id):
        raise RequestValidationError(
            [{"type": "value_error", "loc": ("path", "document_id"), "msg": "Invalid document ID"}]
        )
    return ObjectId(document_id)


# `current_user` comes first in every route so authentication is always checked before anything else.
# Errors raised by the service (DocumentError) are rendered by the handler registered in main.py.


@router.post(
    "",
    response_model=DocumentPublic,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        **_ERRORS,
        409: {"description": "This PDF was already uploaded to this course"},
        413: {"description": "File too large"},
        415: {"description": "Not a PDF (extension, MIME type or signature)"},
        422: {"description": "Encrypted, corrupt, too many pages, or no extractable text"},
    },
)
async def upload_document(
    background_tasks: BackgroundTasks,
    response: Response,
    current_user: UserPublic = Depends(get_current_user),
    course_oid: ObjectId = Depends(valid_course_id),
    file: UploadFile = File(...),
):
    """Accepts a PDF and returns 202 immediately; poll GET .../documents/{document_id} until
    `status` is `ready` (or `failed`)."""
    try:
        document, job = await document_service.accept_upload(current_user.id, course_oid, file)
    finally:
        await file.close()
    background_tasks.add_task(document_service.run_ingestion, job)
    response.headers["Location"] = f"/courses/{course_oid}/documents/{document.document_id}"
    return document


@router.get("", response_model=list[DocumentPublic], responses=_ERRORS)
async def list_documents(
    current_user: UserPublic = Depends(get_current_user),
    course_oid: ObjectId = Depends(valid_course_id),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
):
    """Documents of this course, newest first."""
    return await document_service.list_documents(current_user.id, course_oid, skip, limit)


@router.get("/{document_id}", response_model=DocumentPublic, responses=_ERRORS)
async def get_document(
    current_user: UserPublic = Depends(get_current_user),
    course_oid: ObjectId = Depends(valid_course_id),
    document_oid: ObjectId = Depends(valid_document_id),
):
    return await document_service.get_document(current_user.id, course_oid, document_oid)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_ERRORS, 409: {"description": "Still being processed"}},
)
async def delete_document(
    current_user: UserPublic = Depends(get_current_user),
    course_oid: ObjectId = Depends(valid_course_id),
    document_oid: ObjectId = Depends(valid_document_id),
):
    """Removes the metadata, the stored PDF and all of the document's vector chunks."""
    await document_service.delete_document(current_user.id, course_oid, document_oid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
