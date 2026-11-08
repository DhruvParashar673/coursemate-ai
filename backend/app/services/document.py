"""Document metadata (MongoDB), lifecycle, ingestion runner, deletion and startup recovery.

Ownership: every document query is scoped by user_id AND course_id, and every public operation
first verifies that the authenticated user owns the course (reusing the course service).

Mongo status lifecycle:  processing -> ready | failed        (deleting is entered by DELETE)
Write order is chosen so a failure at any step leaves only things that can be found and cleaned:
the Mongo record exists before any Chroma chunk, and is removed last on deletion.
"""
import asyncio
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import UploadFile
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.config import get_settings
from app.core.database import get_database
from app.rag import ingestion, pdf_extractor, vector_store
from app.rag.errors import (
    EmbeddingError,
    IngestionCancelled,
    PdfEncryptedError,
    PdfError,
    PdfNoTextError,
    PdfTooManyPagesError,
    VectorStoreError,
)
from app.rag.vector_store import ChunkToStore
from app.schemas.document import DocumentPublic
from app.services import course as course_service
from app.services import file_storage

logger = logging.getLogger(__name__)

DOCUMENTS_COLLECTION = "documents"
_ACTIVE = ["processing", "ready"]

ERROR_MESSAGES = {
    "embedding_unavailable": "The embedding model was unavailable. Delete this document and upload it again.",
    "vector_store_unavailable": "The search index was unavailable. Delete this document and upload it again.",
    "processing_timeout": "Processing took too long. Delete this document and upload it again.",
    "processing_failed": "Processing failed. Delete this document and upload it again.",
    "interrupted": "Processing was interrupted by a server restart. Delete this document and upload it again.",
}


# ----------------------------------------------------------------------------- errors


class DocumentError(Exception):
    """Client-facing error with a fixed status code and a safe message."""

    status_code = 400
    default_detail = "Bad request"

    def __init__(self, detail: str | None = None):
        self.detail = detail or self.default_detail
        super().__init__(self.detail)


class CourseNotFoundError(DocumentError):
    status_code = 404
    default_detail = "Course not found"


class DocumentNotFoundError(DocumentError):
    status_code = 404
    default_detail = "Document not found"


class DocumentBusyError(DocumentError):
    status_code = 409
    default_detail = "Document is still being processed; try again once it has finished"


class DuplicateDocumentError(DocumentError):
    status_code = 409
    default_detail = "This PDF has already been uploaded to this course"


class FileTooLargeError(DocumentError):
    status_code = 413


class UnsupportedFileTypeError(DocumentError):
    status_code = 415
    default_detail = "Only PDF files are accepted"


class InvalidPdfError(DocumentError):
    status_code = 422
    default_detail = "The file is not a valid, readable PDF"


# ----------------------------------------------------------------------------- helpers


def _documents():
    return get_database()[DOCUMENTS_COLLECTION]


def _now() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)  # Mongo keeps milliseconds


def _owned(user_id: str, course_id: str, document_oid: ObjectId) -> dict:
    """The ONLY filter used to address a single document: id AND owner AND course."""
    if not isinstance(user_id, str) or not user_id or not isinstance(course_id, str) or not course_id:
        raise ValueError("user_id and course_id are required")
    return {"_id": document_oid, "user_id": user_id, "course_id": course_id}


def _course_scope(user_id: str, course_id: str) -> dict:
    if not isinstance(user_id, str) or not user_id or not isinstance(course_id, str) or not course_id:
        raise ValueError("user_id and course_id are required")
    return {"user_id": user_id, "course_id": course_id}


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def document_to_public(doc: dict) -> DocumentPublic:
    """Explicit field list: user_id, stored filename, hash and paths are never exposed."""
    code = doc.get("error_code")
    return DocumentPublic(
        document_id=str(doc["_id"]),
        course_id=doc["course_id"],
        original_filename=doc["original_filename"],
        file_size=doc["file_size"],
        page_count=doc["page_count"],
        pages_without_text=doc.get("pages_without_text", 0),
        chunk_count=doc.get("chunk_count", 0),
        status=doc["status"],
        error=ERROR_MESSAGES.get(code, "Processing failed") if code else None,
        created_at=_utc(doc["created_at"]),
        updated_at=_utc(doc["updated_at"]),
    )


async def require_course(user_id: str, course_oid: ObjectId) -> None:
    """Course ownership check (404 for missing OR someone else's course)."""
    if await course_service.get_course(user_id, course_oid) is None:
        raise CourseNotFoundError


async def ensure_document_indexes() -> bool:
    try:
        collection = _documents()
        await collection.create_index(
            [("user_id", 1), ("course_id", 1), ("created_at", -1), ("_id", -1)],
            name="idx_doc_user_course_created",
        )
        # One ACTIVE copy of the same file per course. Failed/deleting records don't block a re-upload.
        await collection.create_index(
            [("user_id", 1), ("course_id", 1), ("file_sha256", 1)],
            unique=True,
            name="uniq_doc_active_hash",
            partialFilterExpression={"status": {"$in": _ACTIVE}},
        )
        await collection.create_index([("status", 1)], name="idx_doc_status")
        return True
    except PyMongoError as exc:
        logger.error("Could not create documents indexes: %s", type(exc).__name__)
        return False


# ----------------------------------------------------------------------------- upload


@dataclass(frozen=True)
class IngestionJob:
    document_id: str
    user_id: str
    course_id: str
    chunks: list[ChunkToStore]


def _validate_declared_type(upload: UploadFile) -> str:
    name = upload.filename or ""
    if not name.lower().endswith(".pdf"):
        raise UnsupportedFileTypeError("Only .pdf files are accepted")
    content_type = (upload.content_type or "").split(";")[0].strip().lower()
    if content_type != "application/pdf":
        raise UnsupportedFileTypeError("Only application/pdf uploads are accepted")
    return file_storage.sanitize_original_filename(name)


async def _prepare(document_id: str, pdf_path) -> ingestion.PreparedDocument:
    settings = get_settings()
    try:
        raw = await asyncio.to_thread(pdf_extractor.extract_pages, pdf_path, settings.MAX_PDF_PAGES)
        prepared = await asyncio.to_thread(
            ingestion.prepare_document, document_id, raw, settings.CHUNK_SIZE_CHARS, settings.CHUNK_OVERLAP_CHARS
        )
        ingestion.ensure_extractable(prepared, settings.MIN_TEXT_PAGE_RATIO)
    except PdfEncryptedError:
        raise InvalidPdfError("The PDF is password-protected") from None
    except PdfTooManyPagesError:
        raise InvalidPdfError(f"The PDF has more than {settings.MAX_PDF_PAGES} pages") from None
    except PdfNoTextError:
        raise InvalidPdfError(
            "No extractable text found. Scanned or image-only PDFs are not supported yet"
        ) from None
    except PdfError:
        raise InvalidPdfError from None
    return prepared


async def accept_upload(
    user_id: str, course_oid: ObjectId, upload: UploadFile
) -> tuple[DocumentPublic, IngestionJob]:
    """Validate, store and register an upload (everything fast). Embedding runs later in the background."""
    settings = get_settings()
    course_id = str(course_oid)

    await require_course(user_id, course_oid)  # ownership first, before touching the file
    original_filename = _validate_declared_type(upload)

    limit_mb = settings.MAX_UPLOAD_SIZE_MB
    try:
        stored = await file_storage.save_upload_to_temp(upload, limit_mb * 1024 * 1024)
    except file_storage.UploadTooLargeError:
        raise FileTooLargeError(f"The PDF exceeds the {limit_mb} MB limit") from None
    except file_storage.NotAPdfError:
        raise UnsupportedFileTypeError("The file content is not a PDF") from None
    except file_storage.EmptyUploadError:
        raise InvalidPdfError("The uploaded file is empty") from None

    document_oid = ObjectId()
    document_id = str(document_oid)
    try:
        duplicate = await _documents().find_one(
            {**_course_scope(user_id, course_id), "file_sha256": stored.sha256, "status": {"$in": _ACTIVE}},
            projection={"_id": 1},
        )
        if duplicate is not None:
            raise DuplicateDocumentError
        prepared = await _prepare(document_id, stored.path)
        await asyncio.to_thread(file_storage.commit_upload, stored.path, user_id, course_id, document_id)
    except BaseException:
        file_storage.remove_temp(stored.path)
        raise

    now = _now()
    doc = {
        "_id": document_oid,
        "user_id": user_id,  # from the authenticated user, never from the request
        "course_id": course_id,  # from the ownership-checked path, never from the body
        "filename": f"{document_id}.pdf",  # server-generated stored name
        "original_filename": original_filename,  # display label only
        "file_size": stored.size,
        "file_sha256": stored.sha256,
        "page_count": prepared.page_count,
        "pages_without_text": prepared.pages_without_text,
        "chunk_count": 0,
        "status": "processing",
        "error_code": None,
        "embedding_model": None,
        "created_at": now,
        "updated_at": now,
    }
    try:
        await _documents().insert_one(doc)
        # The course could have been deleted while we were working: don't leave an orphan behind.
        if await course_service.get_course(user_id, course_oid) is None:
            await _documents().delete_one(_owned(user_id, course_id, document_oid))
            raise CourseNotFoundError
    except DuplicateKeyError:
        await asyncio.to_thread(file_storage.delete_pdf, user_id, course_id, document_id)
        raise DuplicateDocumentError from None
    except BaseException:
        await asyncio.to_thread(file_storage.delete_pdf, user_id, course_id, document_id)
        raise

    return document_to_public(doc), IngestionJob(document_id, user_id, course_id, prepared.chunks)


# ----------------------------------------------------------------------------- background ingestion

_slot: asyncio.Semaphore | None = None
_slot_loop: asyncio.AbstractEventLoop | None = None


def _ingestion_slot() -> asyncio.Semaphore:
    """One embedding job at a time (CPU-heavy). Re-created if the event loop changed (tests)."""
    global _slot, _slot_loop
    loop = asyncio.get_running_loop()
    if _slot is None or _slot_loop is not loop:
        _slot, _slot_loop = asyncio.Semaphore(1), loop
    return _slot


async def _mark_ready(document_id: str, chunk_count: int) -> bool:
    """Only succeeds while the record is still 'processing': a deleted/failed record is never resurrected."""
    result = await _documents().update_one(
        {"_id": ObjectId(document_id), "status": "processing"},
        {
            "$set": {
                "status": "ready",
                "chunk_count": chunk_count,
                "embedding_model": get_settings().EMBEDDING_MODEL_NAME,
                "error_code": None,
                "updated_at": _now(),
            }
        },
    )
    return result.modified_count == 1


async def _mark_failed(document_id: str, error_code: str) -> None:
    await _documents().update_one(
        {"_id": ObjectId(document_id), "status": "processing"},
        {"$set": {"status": "failed", "error_code": error_code, "updated_at": _now()}},
    )


async def _purge_artifacts(user_id: str, course_id: str, document_id: str) -> None:
    """Remove a document's Chroma chunks and stored PDF. Idempotent; raises on real failures."""
    await asyncio.to_thread(vector_store.delete_document_chunks, user_id, course_id, document_id)
    await asyncio.to_thread(file_storage.delete_pdf, user_id, course_id, document_id)


async def _purge_quietly(job: IngestionJob) -> None:
    try:
        await _purge_artifacts(job.user_id, job.course_id, job.document_id)
    except Exception as exc:  # startup recovery will retry anything left behind
        logger.error("Cleanup after failed ingestion incomplete: %s", type(exc).__name__)


async def run_ingestion(job: IngestionJob) -> None:
    """Background task: embed + store, then flip the record to ready (or clean up and mark failed)."""
    async with _ingestion_slot():
        settings = get_settings()
        cancel = threading.Event()
        task = asyncio.create_task(
            asyncio.to_thread(
                ingestion.embed_and_store, job.user_id, job.course_id, job.document_id, job.chunks, cancel
            )
        )
        error_code: str | None = None
        stored = 0
        try:
            stored = await asyncio.wait_for(asyncio.shield(task), timeout=settings.INGESTION_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            cancel.set()
            try:
                await task  # the worker stops at its next batch boundary
            except Exception:
                pass
            error_code = "processing_timeout"
        except asyncio.CancelledError:
            cancel.set()
            raise
        except EmbeddingError:
            error_code = "embedding_unavailable"
        except VectorStoreError:
            error_code = "vector_store_unavailable"
        except IngestionCancelled:
            error_code = "interrupted"
        except Exception as exc:
            logger.error("Ingestion failed unexpectedly: %s", type(exc).__name__)
            error_code = "processing_failed"

        try:
            if error_code is None:
                if await _mark_ready(job.document_id, stored):
                    return
                # Record was deleted (or failed) while we worked: remove what we just wrote.
                await _purge_quietly(job)
            else:
                await _purge_quietly(job)
                await _mark_failed(job.document_id, error_code)
        except PyMongoError as exc:
            logger.error("Could not update document status: %s", type(exc).__name__)  # recovered at startup


# ----------------------------------------------------------------------------- list / get / delete


async def list_documents(user_id: str, course_oid: ObjectId, skip: int, limit: int) -> list[DocumentPublic]:
    await require_course(user_id, course_oid)
    cursor = (
        _documents()
        .find(_course_scope(user_id, str(course_oid)))
        .sort([("created_at", -1), ("_id", -1)])
        .skip(skip)
        .limit(limit)
    )
    return [document_to_public(doc) for doc in await cursor.to_list(length=limit)]


async def get_document(user_id: str, course_oid: ObjectId, document_oid: ObjectId) -> DocumentPublic:
    await require_course(user_id, course_oid)
    doc = await _documents().find_one(_owned(user_id, str(course_oid), document_oid))
    if doc is None:
        raise DocumentNotFoundError
    return document_to_public(doc)


async def delete_document(user_id: str, course_oid: ObjectId, document_oid: ObjectId) -> None:
    """Order: mark 'deleting' -> Chroma chunks -> PDF -> Mongo record (last).
    If any step fails the record remains, so DELETE can simply be retried."""
    await require_course(user_id, course_oid)
    course_id = str(course_oid)
    scope = _owned(user_id, course_id, document_oid)

    doc = await _documents().find_one_and_update(
        {**scope, "status": {"$in": ["ready", "failed", "deleting"]}},
        {"$set": {"status": "deleting", "updated_at": _now()}},
    )
    if doc is None:
        if await _documents().find_one(scope, projection={"_id": 1}) is None:
            raise DocumentNotFoundError
        raise DocumentBusyError  # still processing

    await _purge_artifacts(user_id, course_id, str(document_oid))
    await _documents().delete_one(scope)


async def delete_course_documents(user_id: str, course_id: str) -> None:
    """Cascade used when a course is deleted (the caller has already verified ownership)."""
    scope = _course_scope(user_id, course_id)
    if await _documents().count_documents(scope, limit=1) == 0:
        return
    await _documents().update_many(scope, {"$set": {"status": "deleting", "updated_at": _now()}})
    await asyncio.to_thread(vector_store.delete_course_chunks, user_id, course_id)
    await asyncio.to_thread(file_storage.delete_course_files, user_id, course_id)
    await _documents().delete_many(scope)


# ----------------------------------------------------------------------------- startup


async def reconcile_documents() -> None:
    """Runs once at startup (single worker): nothing can legitimately be 'processing' yet, so those
    records were interrupted; 'deleting' records get their deletion finished."""
    stale = await _documents().find({"status": {"$in": ["processing", "deleting"]}}).to_list(length=None)
    for doc in stale:
        user_id, course_id, document_id = doc["user_id"], doc["course_id"], str(doc["_id"])
        try:
            await _purge_artifacts(user_id, course_id, document_id)
            if doc["status"] == "deleting":
                await _documents().delete_one({"_id": doc["_id"], "status": "deleting"})
            else:
                await _mark_failed(document_id, "interrupted")
        except Exception as exc:
            logger.error("Startup recovery skipped a document: %s", type(exc).__name__)


async def initialize_documents() -> None:
    """Called from lifespan. Never prevents the app from starting."""
    await ensure_document_indexes()
    try:
        await asyncio.to_thread(vector_store.get_collection)
    except VectorStoreError:
        logger.warning("Vector store not available at startup; document endpoints will retry on use")
        return
    try:
        await reconcile_documents()
    except Exception as exc:
        logger.error("Startup reconciliation failed: %s", type(exc).__name__)
