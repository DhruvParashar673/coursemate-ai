"""Exception types for the document/RAG layers. Messages are internal; API responses use fixed text."""


class PdfError(Exception):
    """The uploaded PDF cannot be used."""


class PdfCorruptError(PdfError):
    pass


class PdfEncryptedError(PdfError):
    pass


class PdfTooManyPagesError(PdfError):
    pass


class PdfNoTextError(PdfError):
    """No (or too little) extractable text: scanned / image-only PDF."""


class EmbeddingError(Exception):
    """The embedding model could not be loaded or run."""


class VectorStoreError(Exception):
    """ChromaDB is unavailable, misconfigured or returned an error."""


class StorageError(Exception):
    """Filesystem storage for uploaded PDFs failed."""


class IngestionCancelled(Exception):
    """Cooperative cancellation of a running ingestion (timeout / shutdown)."""
