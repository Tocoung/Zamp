"""Dedicated OCR and text recognition engine for digital PDFs and raster images."""

import io
import shutil
from dataclasses import dataclass, field
from typing import List, Optional
from pypdf import PdfReader
from app.schemas.extraction import ExtractionLimitationCode
from app.core.logging import logger

try:
    import pytesseract
    from PIL import Image
    import pdf2image
    HAS_OCR_PACKAGES = True
except ImportError:
    HAS_OCR_PACKAGES = False


# Sensible, bounded processing limits
MAX_PAGES_LIMIT = 10
MAX_RENDER_DIMENSION = 2500
MAX_TEXT_CHARS_PAGE = 10000
MAX_TOTAL_CHARS = 50000


@dataclass
class OcrPageResult:
    """Recognized text content and metadata for an individual document page."""
    page_number: int              # 1-indexed original page
    text: str                     # Clean normalized text for the page
    extraction_method: str        # "DIGITAL_TEXT" or "OCR"
    confidence: float             # Heuristic or OCR engine confidence [0.0 - 1.0]
    lines: List[str] = field(default_factory=list) # Extracted lines preserving order


@dataclass
class OcrDocumentResult:
    """Composite recognition output across all pages of a document."""
    pages: List[OcrPageResult] = field(default_factory=list)
    total_pages: int = 0
    limitation_code: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def has_readable_text(self) -> bool:
        total_len = sum(len(p.text.strip()) for p in self.pages)
        return total_len >= 10


class OcrEngine:
    """Coordinates digital text stream extraction and local Tesseract OCR."""

    def __init__(self):
        self._tesseract_available = bool(shutil.which("tesseract"))
        self._pdftoppm_available = bool(shutil.which("pdftoppm"))

    @property
    def is_ocr_available(self) -> bool:
        return HAS_OCR_PACKAGES and self._tesseract_available

    def process(self, content: bytes, mime_type: str, filename: str) -> OcrDocumentResult:
        """Extracts or recognizes text per-page from a decrypted document payload."""
        if not content or len(content) == 0:
            return OcrDocumentResult(limitation_code=ExtractionLimitationCode.CORRUPTED_DOCUMENT.value)

        normalized_mime = str(mime_type or "").strip().lower()

        if normalized_mime == "application/pdf":
            return self._process_pdf(content)
        elif normalized_mime in ("image/png", "image/jpeg", "image/jpg"):
            return self._process_image(content, normalized_mime)
        else:
            return OcrDocumentResult(limitation_code=ExtractionLimitationCode.UNSUPPORTED_FORMAT.value)

    def _process_pdf(self, content: bytes) -> OcrDocumentResult:
        """Extracts digital text per page; falls back to raster rendering and OCR if digital text is absent."""
        try:
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted:
                logger.warning("PDF is encrypted; cannot extract or OCR text.")
                return OcrDocumentResult(limitation_code=ExtractionLimitationCode.ENCRYPTED_PDF.value)

            raw_total_pages = len(reader.pages)
            if raw_total_pages == 0:
                return OcrDocumentResult(
                    total_pages=0,
                    limitation_code=ExtractionLimitationCode.INSUFFICIENT_READABLE_TEXT.value
                )

            effective_pages = min(raw_total_pages, MAX_PAGES_LIMIT)
            page_results: List[OcrPageResult] = []

            for page_idx in range(effective_pages):
                page = reader.pages[page_idx]
                page_num = page_idx + 1

                # 1. Attempt digital text stream extraction
                extracted_digital = page.extract_text() or ""
                clean_digital = extracted_digital.strip()

                if len(clean_digital) >= 20:
                    # Digital readable text present
                    lines = [l.strip() for l in extracted_digital.splitlines() if l.strip()]
                    page_results.append(
                        OcrPageResult(
                            page_number=page_num,
                            text=clean_digital[:MAX_TEXT_CHARS_PAGE],
                            extraction_method="DIGITAL_TEXT",
                            confidence=1.0,
                            lines=lines,
                        )
                    )
                else:
                    # 2. Scanned / image-only page: render to raster image and run OCR
                    ocr_res = self._ocr_pdf_page(content, page_num)
                    if ocr_res:
                        page_results.append(ocr_res)
                    else:
                        # Append empty page indicator
                        page_results.append(
                            OcrPageResult(
                                page_number=page_num,
                                text="",
                                extraction_method="OCR",
                                confidence=0.0,
                                lines=[],
                            )
                        )

            doc_result = OcrDocumentResult(pages=page_results, total_pages=raw_total_pages)
            if not doc_result.has_readable_text:
                doc_result.limitation_code = ExtractionLimitationCode.INSUFFICIENT_READABLE_TEXT.value
            return doc_result

        except Exception as e:
            logger.error("Error reading PDF content: %s", type(e).__name__)
            return OcrDocumentResult(
                limitation_code=ExtractionLimitationCode.CORRUPTED_DOCUMENT.value,
                error_message=f"PDF parsing failed ({type(e).__name__})",
            )

    def _ocr_pdf_page(self, pdf_bytes: bytes, page_number: int) -> Optional[OcrPageResult]:
        """Renders a single PDF page into an image and performs OCR."""
        if not self.is_ocr_available or not self._pdftoppm_available:
            logger.info("Local OCR or pdftoppm not available for scanned PDF page %d.", page_number)
            return None

        try:
            rendered_images = pdf2image.convert_from_bytes(
                pdf_bytes,
                first_page=page_number,
                last_page=page_number,
                size=(MAX_RENDER_DIMENSION, None),
            )
            if not rendered_images:
                return None

            img = rendered_images[0]
            return self._ocr_image_object(img, page_number=page_number)
        except Exception as e:
            logger.warning("Failed to render/OCR PDF page %d: %s", page_number, type(e).__name__)
            return None

    def _process_image(self, content: bytes, mime_type: str) -> OcrDocumentResult:
        """Processes raster image (PNG/JPEG) through Tesseract OCR."""
        if not self.is_ocr_available:
            return OcrDocumentResult(
                pages=[],
                total_pages=1,
                limitation_code=ExtractionLimitationCode.OCR_ENGINE_UNAVAILABLE.value,
                error_message="OCR engine is unavailable on host system.",
            )

        try:
            img = Image.open(io.BytesIO(content))
            # Verify and enforce maximum dimensions
            if img.width > MAX_RENDER_DIMENSION or img.height > MAX_RENDER_DIMENSION:
                img.thumbnail((MAX_RENDER_DIMENSION, MAX_RENDER_DIMENSION), Image.Resampling.LANCZOS)

            page_res = self._ocr_image_object(img, page_number=1)
            doc_result = OcrDocumentResult(pages=[page_res], total_pages=1)
            if not doc_result.has_readable_text:
                doc_result.limitation_code = ExtractionLimitationCode.INSUFFICIENT_READABLE_TEXT.value
            return doc_result

        except Exception as e:
            logger.error("Failed to read image payload: %s", type(e).__name__)
            return OcrDocumentResult(
                limitation_code=ExtractionLimitationCode.CORRUPTED_DOCUMENT.value,
                error_message=f"Image processing failed ({type(e).__name__})",
            )

    def _ocr_image_object(self, img: "Image.Image", page_number: int) -> OcrPageResult:
        """Runs Tesseract on a PIL Image and computes confidence."""
        raw_text = pytesseract.image_to_string(img) or ""
        clean_text = raw_text.strip()
        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]

        # Estimate average word confidence from Tesseract data
        try:
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            confs = [float(c) for c in data.get("conf", []) if c != "-1" and float(c) >= 0]
            avg_conf = (sum(confs) / len(confs) / 100.0) if confs else 0.85
            avg_conf = round(min(1.0, max(0.0, avg_conf)), 2)
        except Exception:
            avg_conf = 0.85

        return OcrPageResult(
            page_number=page_number,
            text=clean_text[:MAX_TEXT_CHARS_PAGE],
            extraction_method="OCR",
            confidence=avg_conf,
            lines=lines,
        )


ocr_engine = OcrEngine()
