from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from .text_cleaner import clean_text


def extract_pdf_text(pdf_bytes: bytes) -> tuple[str, str, int]:
    """Return ``(title, cleaned_text, page_count)`` from a text-based PDF.

    Image-only/scanned PDFs intentionally produce little or no text and are
    skipped by the caller. OCR is outside the scope of the current pipeline.
    """
    reader = PdfReader(BytesIO(pdf_bytes))
    title = ""
    if reader.metadata and reader.metadata.title:
        title = clean_text(str(reader.metadata.title))

    page_text: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = clean_text(text)
        if text:
            page_text.append(text)

    return title, clean_text("\n\n".join(page_text)), len(reader.pages)
