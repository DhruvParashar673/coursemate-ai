"""Pure-ish pipeline steps: clean + chunk (fast, done in the upload request) and
embed + store (slow, done in the background)."""
import threading
from dataclasses import dataclass

from app.rag import vector_store
from app.rag.chunking import chunk_pages
from app.rag.embeddings import get_embedder
from app.rag.errors import IngestionCancelled, PdfNoTextError, VectorStoreError
from app.rag.pdf_extractor import RawDocument
from app.rag.text_cleaning import clean_page_text
from app.rag.vector_store import ChunkToStore

_EMBED_GROUP = 64  # embed in groups so a cancel request is noticed quickly


@dataclass(frozen=True)
class PreparedDocument:
    page_count: int
    pages_without_text: int
    chunks: list[ChunkToStore]


def prepare_document(document_id: str, raw: RawDocument, chunk_size: int, overlap: int) -> PreparedDocument:
    """Clean every page, then chunk page by page (page numbers are preserved)."""
    cleaned = [(page.page_number, clean_page_text(page.text)) for page in raw.pages]
    pages_without_text = sum(1 for _, text in cleaned if not text)
    chunks = chunk_pages(cleaned, chunk_size, overlap)
    return PreparedDocument(
        page_count=raw.page_count,
        pages_without_text=pages_without_text,
        chunks=[
            ChunkToStore(
                chunk_id=f"{document_id}_{index:05d}",
                chunk_index=index,
                page_number=chunk.page_number,
                text=chunk.text,
            )
            for index, chunk in enumerate(chunks)
        ],
    )


def ensure_extractable(prepared: PreparedDocument, min_text_page_ratio: float) -> None:
    """Refuse scanned / image-only PDFs instead of silently accepting an empty document."""
    pages_with_text = prepared.page_count - prepared.pages_without_text
    if not prepared.chunks or pages_with_text / prepared.page_count < min_text_page_ratio:
        raise PdfNoTextError("no extractable text")


def embed_and_store(
    user_id: str,
    course_id: str,
    document_id: str,
    chunks: list[ChunkToStore],
    cancel_event: threading.Event | None = None,
) -> int:
    """Embed each distinct chunk text once, write everything to Chroma, return the stored count."""
    embedder = get_embedder()
    texts = [chunk.text for chunk in chunks]
    unique = list(dict.fromkeys(texts))  # identical texts (e.g. repeated boilerplate) are embedded once

    vector_by_text: dict[str, list[float]] = {}
    for i in range(0, len(unique), _EMBED_GROUP):
        if cancel_event is not None and cancel_event.is_set():
            raise IngestionCancelled("cancelled")
        group = unique[i : i + _EMBED_GROUP]
        vector_by_text.update(zip(group, embedder.embed_documents(group)))

    # Nothing is written to Chroma until every embedding exists.
    vector_store.add_chunks(
        user_id, course_id, document_id, chunks, [vector_by_text[t] for t in texts], cancel_event
    )
    stored = vector_store.count_document_chunks(user_id, course_id, document_id)
    if stored != len(chunks):
        raise VectorStoreError("stored chunk count mismatch")
    return stored
