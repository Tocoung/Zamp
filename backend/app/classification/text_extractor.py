"""Safe internal text extraction for digitally readable PDF document classification."""

import io
import re
from typing import Tuple, Optional
from pypdf import PdfReader
from app.schemas.classification import ClassificationLimitationCode
from app.core.logging import logger


def extract_document_text(
    content: bytes,
    mime_type: str,
    max_chars: int = 50000,
) -> Tuple[str, bool, Optional[str]]:
    """Extracts text from text-based PDFs for internal classification only.
    
    Args:
        content: Decrypted binary file bytes.
        mime_type: Normalized MIME type (application/pdf, image/png, image/jpeg).
        max_chars: Maximum character count to inspect (bounds memory).
        
    Returns:
        Tuple of (clean_text, is_extractable, limitation_code).
        
    Notes:
        - Image documents (PNG/JPEG) are identified immediately as non-text without attempting OCR.
        - Scanned PDFs containing zero font streams return is_extractable=False.
        - Never persists or leaks raw extracted text.
    """
    normalized_mime = str(mime_type or "").strip().lower()

    # 1. Non-PDF images return explicit image limitation
    if normalized_mime in ("image/png", "image/jpeg", "image/jpg"):
        return "", False, ClassificationLimitationCode.IMAGE_ONLY_DOCUMENT.value

    if normalized_mime != "application/pdf":
        return "", False, ClassificationLimitationCode.NO_EXTRACTABLE_TEXT.value

    # 2. Extract text from digital PDF stream
    try:
        stream = io.BytesIO(content)
        reader = PdfReader(stream)

        if reader.is_encrypted:
            # Encrypted or password-locked PDF cannot be safely read
            logger.info("PDF is password-protected or encrypted; unable to extract text.")
            return "", False, ClassificationLimitationCode.NO_EXTRACTABLE_TEXT.value

        extracted_parts = []
        total_len = 0

        # Inspect up to first 25 pages
        for page_idx, page in enumerate(reader.pages[:25]):
            page_text = page.extract_text() or ""
            if page_text:
                extracted_parts.append(page_text)
                total_len += len(page_text)
                if total_len >= max_chars:
                    break

        raw_combined = " ".join(extracted_parts)
        # Normalize whitespace (replace multiple spaces/newlines with single space)
        clean_text = re.sub(r"\s+", " ", raw_combined).strip()

        # Minimum text length threshold to distinguish digital text from noise
        if len(clean_text) < 20:
            return "", False, ClassificationLimitationCode.NO_EXTRACTABLE_TEXT.value

        return clean_text[:max_chars], True, None

    except Exception as e:
        logger.warning("Failed to extract digital text from PDF: %s", type(e).__name__)
        return "", False, ClassificationLimitationCode.NO_EXTRACTABLE_TEXT.value
