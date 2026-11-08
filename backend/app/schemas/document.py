from datetime import datetime
from typing import Literal

from pydantic import BaseModel

DocumentStatus = Literal["processing", "ready", "failed", "deleting"]


class DocumentPublic(BaseModel):
    """Public view. Never includes user_id, stored filename, hashes or filesystem paths."""

    document_id: str
    course_id: str
    original_filename: str
    file_size: int
    page_count: int
    pages_without_text: int
    chunk_count: int
    status: DocumentStatus
    error: str | None = None
    created_at: datetime
    updated_at: datetime
