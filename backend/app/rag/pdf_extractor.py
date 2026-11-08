import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from app.rag.errors import PdfCorruptError, PdfEncryptedError, PdfTooManyPagesError

logger = logging.getLogger(__name__)

pymupdf.TOOLS.mupdf_display_errors(False)  # MuPDF repair warnings would otherwise spam stderr

# PyMuPDF is not thread-safe: serialise every call into it.
_PYMUPDF_LOCK = threading.Lock()


@dataclass(frozen=True)
class RawPage:
    page_number: int  # 1-based physical page index (matches PDF viewers)
    text: str


@dataclass(frozen=True)
class RawDocument:
    page_count: int
    pages: list[RawPage]


def extract_pages(pdf_path: Path, max_pages: int) -> RawDocument:
    """Extract text page by page, preserving original page numbers.

    Raises PdfCorruptError / PdfEncryptedError / PdfTooManyPagesError. Note that MuPDF silently
    repairs many damaged files, so callers must still check that real text was extracted.
    """
    with _PYMUPDF_LOCK:
        try:
            doc = pymupdf.open(str(pdf_path), filetype="pdf")
        except Exception as exc:
            logger.info("PDF open failed: %s", type(exc).__name__)
            raise PdfCorruptError("cannot open PDF") from None

        try:
            if doc.needs_pass:
                raise PdfEncryptedError("password-protected PDF")
            if not doc.is_pdf or doc.page_count == 0:
                raise PdfCorruptError("not a readable PDF")
            if doc.page_count > max_pages:
                raise PdfTooManyPagesError("too many pages")

            pages: list[RawPage] = []
            for index in range(doc.page_count):
                try:
                    text = doc[index].get_text("text")
                except Exception as exc:  # one broken page must not sink the document
                    logger.info("Page %d text extraction failed: %s", index + 1, type(exc).__name__)
                    text = ""
                pages.append(RawPage(page_number=index + 1, text=text))
            return RawDocument(page_count=doc.page_count, pages=pages)
        finally:
            doc.close()
