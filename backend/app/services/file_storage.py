"""Safe storage of uploaded PDFs. The client-supplied filename is NEVER used as a path."""
import asyncio
import hashlib
import logging
import os
import re
import shutil
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.core.config import get_settings
from app.rag.errors import StorageError

logger = logging.getLogger(__name__)

_ID_RE = re.compile(r"[0-9a-f]{24}")  # server-generated ObjectId hex strings only
_READ_CHUNK = 1024 * 1024


class UploadTooLargeError(Exception):
    pass


class NotAPdfError(Exception):
    pass


class EmptyUploadError(Exception):
    pass


@dataclass(frozen=True)
class StoredUpload:
    path: Path  # temporary file (inside UPLOAD_DIR/.tmp)
    size: int
    sha256: str


def _root() -> Path:
    root = get_settings().UPLOAD_DIR
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _safe_dir(*parts: str) -> Path:
    root = _root()
    for part in parts:
        if not _ID_RE.fullmatch(part):
            raise ValueError("unsafe path component")
    path = root.joinpath(*parts).resolve()
    if not path.is_relative_to(root):  # defence in depth
        raise ValueError("path escapes upload directory")
    return path


def pdf_path(user_id: str, course_id: str, document_id: str) -> Path:
    """uploads/<user_id>/<course_id>/<document_id>.pdf, built only from validated server-side ids."""
    if not _ID_RE.fullmatch(document_id):
        raise ValueError("unsafe document id")
    return _safe_dir(user_id, course_id) / f"{document_id}.pdf"


def sanitize_original_filename(name: str | None) -> str:
    """Display label only: strip directories, control characters, odd whitespace; cap the length."""
    name = (name or "").replace("\\", "/").split("/")[-1]
    name = unicodedata.normalize("NFC", name)
    name = "".join(ch for ch in name if ch.isprintable())
    name = re.sub(r"\s+", " ", name).strip().strip(".")
    if len(name) > 150:
        name = name[:146].rstrip() + ".pdf"
    return name or "document.pdf"


def _new_temp_path() -> Path:
    tmp_dir = _root() / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    return tmp_dir / f"{uuid.uuid4().hex}.part"


def remove_temp(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Could not remove temp upload: %s", type(exc).__name__)


async def save_upload_to_temp(upload: UploadFile, max_bytes: int) -> StoredUpload:
    """Stream the upload to a temp file, enforcing the size limit and the %PDF- signature
    while reading (the declared Content-Length is never trusted)."""
    tmp = _new_temp_path()
    hasher = hashlib.sha256()
    size = 0
    first = True
    try:
        with open(tmp, "wb") as out:
            while True:
                chunk = await upload.read(_READ_CHUNK)
                if not chunk:
                    break
                if first:
                    if not chunk.startswith(b"%PDF-"):
                        raise NotAPdfError
                    first = False
                size += len(chunk)
                if size > max_bytes:
                    raise UploadTooLargeError
                hasher.update(chunk)
                await asyncio.to_thread(out.write, chunk)
        if size == 0:
            raise EmptyUploadError
    except BaseException:
        remove_temp(tmp)
        raise
    return StoredUpload(path=tmp, size=size, sha256=hasher.hexdigest())


def commit_upload(tmp: Path, user_id: str, course_id: str, document_id: str) -> None:
    """Atomically move the validated temp file to its final server-generated location."""
    try:
        dest = pdf_path(user_id, course_id, document_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, dest)
        os.chmod(dest, 0o600)
    except OSError as exc:
        logger.error("Storing PDF failed: %s", type(exc).__name__)
        raise StorageError("could not store file") from None


def delete_pdf(user_id: str, course_id: str, document_id: str) -> None:
    """Idempotent: a missing file is fine."""
    try:
        pdf_path(user_id, course_id, document_id).unlink(missing_ok=True)
    except OSError as exc:
        logger.error("Deleting PDF failed: %s", type(exc).__name__)
        raise StorageError("could not delete file") from None


def delete_course_files(user_id: str, course_id: str) -> None:
    try:
        directory = _safe_dir(user_id, course_id)
        if directory.exists():
            shutil.rmtree(directory)
    except OSError as exc:
        logger.error("Deleting course files failed: %s", type(exc).__name__)
        raise StorageError("could not delete files") from None
