"""All ChromaDB access lives here.

Isolation rule: every operation requires user_id AND course_id and is built through `_scope()`.
There is intentionally no function that reads, counts or deletes chunks without that scope.
Functions are synchronous (Chroma is blocking): call them via asyncio.to_thread.
"""
import logging
import threading
from dataclasses import dataclass

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import get_settings
from app.rag.errors import IngestionCancelled, VectorStoreError

logger = logging.getLogger(__name__)

_INIT_LOCK = threading.Lock()
_collection = None
_UPSERT_BATCH = 256


@dataclass(frozen=True)
class ChunkToStore:
    chunk_id: str  # "<document_id>_<chunk_index:05d>": unique and deterministic
    chunk_index: int
    page_number: int
    text: str


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    document_id: str
    page_number: int
    text: str
    score: float  # cosine similarity (1 = identical)


def get_collection():
    """Open (once) the persistent client + collection; retried on the next call if it fails."""
    global _collection
    if _collection is not None:
        return _collection
    with _INIT_LOCK:
        if _collection is None:
            settings = get_settings()
            try:
                settings.CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
                client = chromadb.PersistentClient(
                    path=str(settings.CHROMA_PERSIST_DIR),
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
                collection = client.get_or_create_collection(
                    name=settings.CHROMA_COLLECTION_NAME,
                    embedding_function=None,  # we always supply our own vectors; never Chroma's default model
                    configuration={"hnsw": {"space": "cosine"}},
                    metadata={"embedding_model": settings.EMBEDDING_MODEL_NAME},
                )
            except Exception as exc:
                logger.error("ChromaDB init failed: %s", type(exc).__name__)
                raise VectorStoreError("vector store unavailable") from None

            stored_model = (collection.metadata or {}).get("embedding_model")
            if stored_model != settings.EMBEDDING_MODEL_NAME:
                # Vectors from different models are not comparable, even at equal dimensions.
                logger.error(
                    "Chroma collection was built with embedding model %r but %r is configured",
                    stored_model,
                    settings.EMBEDDING_MODEL_NAME,
                )
                raise VectorStoreError("embedding model mismatch")
            _collection = collection
    return _collection


def _require(label: str, value) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is required")
    return value


def _scope(user_id: str, course_id: str, document_id: str | None = None) -> dict:
    """The only way a metadata filter is built: owner AND course (AND document)."""
    clauses = [
        {"user_id": _require("user_id", user_id)},
        {"course_id": _require("course_id", course_id)},
    ]
    if document_id is not None:
        clauses.append({"document_id": _require("document_id", document_id)})
    return {"$and": clauses}


def add_chunks(
    user_id: str,
    course_id: str,
    document_id: str,
    chunks: list[ChunkToStore],
    embeddings: list[list[float]],
    cancel_event: threading.Event | None = None,
) -> None:
    """Upsert chunks (idempotent by chunk_id). Ownership metadata comes from the arguments only."""
    if len(chunks) != len(embeddings):
        raise ValueError("chunks and embeddings must have the same length")
    _scope(user_id, course_id, document_id)  # validates all three ids
    collection = get_collection()
    try:
        for i in range(0, len(chunks), _UPSERT_BATCH):
            if cancel_event is not None and cancel_event.is_set():
                raise IngestionCancelled("cancelled")
            batch = chunks[i : i + _UPSERT_BATCH]
            collection.upsert(
                ids=[c.chunk_id for c in batch],
                embeddings=embeddings[i : i + _UPSERT_BATCH],
                documents=[c.text for c in batch],
                metadatas=[
                    {
                        "user_id": user_id,
                        "course_id": course_id,
                        "document_id": document_id,
                        "page_number": c.page_number,
                        "chunk_id": c.chunk_id,
                        "chunk_index": c.chunk_index,
                    }
                    for c in batch
                ],
            )
    except IngestionCancelled:
        raise
    except Exception as exc:
        logger.error("Chroma upsert failed: %s", type(exc).__name__)
        raise VectorStoreError("vector store write failed") from None


def count_document_chunks(user_id: str, course_id: str, document_id: str) -> int:
    try:
        result = get_collection().get(where=_scope(user_id, course_id, document_id), include=[])
        return len(result["ids"])
    except VectorStoreError:
        raise
    except Exception as exc:
        logger.error("Chroma count failed: %s", type(exc).__name__)
        raise VectorStoreError("vector store read failed") from None


def delete_document_chunks(user_id: str, course_id: str, document_id: str) -> None:
    """Idempotent: deleting nothing is fine."""
    where = _scope(user_id, course_id, document_id)
    try:
        get_collection().delete(where=where)
    except VectorStoreError:
        raise
    except Exception as exc:
        logger.error("Chroma delete failed: %s", type(exc).__name__)
        raise VectorStoreError("vector store delete failed") from None


def delete_course_chunks(user_id: str, course_id: str) -> None:
    where = _scope(user_id, course_id)
    try:
        get_collection().delete(where=where)
    except VectorStoreError:
        raise
    except Exception as exc:
        logger.error("Chroma course delete failed: %s", type(exc).__name__)
        raise VectorStoreError("vector store delete failed") from None


def query_chunks(
    user_id: str,
    course_id: str,
    query_embedding: list[float],
    top_k: int = 5,
    document_id: str | None = None,
) -> list[RetrievedChunk]:
    """Nearest chunks within ONE user's ONE course (optionally one document). Internal API."""
    where = _scope(user_id, course_id, document_id)
    if top_k < 1:
        raise ValueError("top_k must be >= 1")
    try:
        result = get_collection().query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except VectorStoreError:
        raise
    except Exception as exc:
        logger.error("Chroma query failed: %s", type(exc).__name__)
        raise VectorStoreError("vector store read failed") from None

    return [
        RetrievedChunk(
            chunk_id=meta["chunk_id"],
            document_id=meta["document_id"],
            page_number=int(meta["page_number"]),
            text=text,
            score=1.0 - float(distance),
        )
        for text, meta, distance in zip(
            result["documents"][0], result["metadatas"][0], result["distances"][0]
        )
    ]
