import logging
import threading
from collections.abc import Sequence
from dataclasses import dataclass

from app.core.config import get_settings
from app.rag.errors import EmbeddingError

logger = logging.getLogger(__name__)

_LOAD_LOCK = threading.Lock()
_embedder: "Embedder | None" = None


@dataclass(frozen=True)
class Prefixes:
    query: str
    passage: str


def resolve_prefixes(model_name: str, query_override: str | None, passage_override: str | None) -> Prefixes:
    """E5 models REQUIRE "query: " / "passage: " prefixes (they were trained with them).

    Explicit settings win; otherwise they are derived from the model family.
    """
    if "e5" in model_name.lower():
        defaults = Prefixes(query="query: ", passage="passage: ")
    else:
        defaults = Prefixes(query="", passage="")
        if query_override is None and passage_override is None:
            logger.warning(
                "No embedding prefixes known for model %r; using none. Set EMBEDDING_QUERY_PREFIX / "
                "EMBEDDING_PASSAGE_PREFIX if this model needs them.",
                model_name,
            )
    return Prefixes(
        query=defaults.query if query_override is None else query_override,
        passage=defaults.passage if passage_override is None else passage_override,
    )


class Embedder:
    """Thin wrapper that owns prefixing and normalisation, so no caller can get them wrong."""

    def __init__(self, model, model_name: str, prefixes: Prefixes, batch_size: int):
        self._model = model
        self.model_name = model_name
        self.prefixes = prefixes
        self._batch_size = batch_size
        self.dimension = _dimension_of(model)

    def _encode(self, texts: list[str]) -> list[list[float]]:
        try:
            vectors = self._model.encode(
                texts,
                batch_size=self._batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,  # unit vectors + cosine space in Chroma
            )
        except Exception as exc:
            logger.error("Embedding failed: %s", type(exc).__name__)
            raise EmbeddingError("embedding failed") from None
        return vectors.tolist()

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed passages for indexing ("passage: " prefix for E5)."""
        if not texts:
            return []
        return self._encode([self.prefixes.passage + text for text in texts])

    def embed_query(self, text: str) -> list[float]:
        """Embed a search query ("query: " prefix for E5)."""
        return self._encode([self.prefixes.query + text])[0]


def _dimension_of(model) -> int:
    # sentence-transformers >= 5 renamed get_sentence_embedding_dimension -> get_embedding_dimension
    getter = getattr(model, "get_embedding_dimension", None) or getattr(
        model, "get_sentence_embedding_dimension", None
    )
    dimension = getter() if getter else None
    if not dimension:
        raise EmbeddingError("cannot determine embedding dimension")
    return int(dimension)


def _load_model(model_name: str):
    from sentence_transformers import SentenceTransformer  # heavy import: only when first needed

    return SentenceTransformer(model_name)


def get_embedder() -> Embedder:
    """Process-wide embedder; the model is loaded once, on first use."""
    global _embedder
    if _embedder is not None:
        return _embedder
    with _LOAD_LOCK:
        if _embedder is None:
            settings = get_settings()
            try:
                model = _load_model(settings.EMBEDDING_MODEL_NAME)
                _embedder = Embedder(
                    model=model,
                    model_name=settings.EMBEDDING_MODEL_NAME,
                    prefixes=resolve_prefixes(
                        settings.EMBEDDING_MODEL_NAME,
                        settings.EMBEDDING_QUERY_PREFIX,
                        settings.EMBEDDING_PASSAGE_PREFIX,
                    ),
                    batch_size=settings.EMBEDDING_BATCH_SIZE,
                )
            except EmbeddingError:
                raise
            except Exception as exc:
                logger.error("Embedding model load failed: %s", type(exc).__name__)
                raise EmbeddingError("embedding model unavailable") from None
    return _embedder
