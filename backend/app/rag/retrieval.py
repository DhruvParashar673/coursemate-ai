"""Internal retrieval helper (no HTTP route in this module; used by tests and Module 5)."""
from app.rag import vector_store
from app.rag.embeddings import get_embedder
from app.rag.vector_store import RetrievedChunk


def search_chunks(
    user_id: str,
    course_id: str,
    query: str,
    top_k: int = 5,
    document_id: str | None = None,
) -> list[RetrievedChunk]:
    """Embed `query` ("query: " prefix) and search within one user's one course. Synchronous.

    Callers must have verified course ownership; the user_id + course_id scope is still
    enforced on the vector query itself.
    """
    if not query or not query.strip():
        raise ValueError("query is required")
    embedding = get_embedder().embed_query(query.strip())
    return vector_store.query_chunks(user_id, course_id, embedding, top_k=top_k, document_id=document_id)
