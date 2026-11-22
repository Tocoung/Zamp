"""Extraction service coordinating OCR, structured field parsing, persistence, audit activities, and page preview."""

import io
from typing import List, Optional, Tuple
from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session
from pypdf import PdfReader

try:
    import pdf2image
    from PIL import Image
    HAS_PREVIEW_IMAGING = True
except ImportError:
    HAS_PREVIEW_IMAGING = False

from app.models.vendor import Vendor
from app.models.document import VendorDocument
from app.models.extraction import DocumentExtraction
from app.models.activity import VendorActivity
from app.schemas.extraction import (
    ExtractionStatus,
    ExtractionLimitationCode,
    ExtractedField,
    FieldStatus,
)
from app.extraction.ocr_engine import ocr_engine
from app.extraction.parsers import document_parser
from app.classification.privacy import sanitize_filename_for_activity
from app.core.storage import document_storage
from app.core.logging import logger


class ExtractionServiceError(Exception):
    """Base exception for document extraction failures."""
    pass


class ExtractionNotFoundError(ExtractionServiceError):
    """Raised when an extraction result is not found."""
    pass


class DocumentPreviewError(ExtractionServiceError):
    """Raised when an original document page preview cannot be rendered."""
    pass


class ExtractionService:
    """Coordinates document decryption, OCR parsing, structured field extraction, and database persistence."""

    def __init__(self, storage=document_storage, ocr=ocr_engine, parser=document_parser):
        self.storage = storage
        self.ocr = ocr
        self.parser = parser

    def extract_document(
        self,
        db: Session,
        vendor_id: str,
        document_id: str,
        category_override: Optional[str] = None,
    ) -> DocumentExtraction:
        """Runs OCR and structured information extraction for an uploaded vendor document."""
        # 1. Verify vendor
        vendor = db.get(Vendor, str(vendor_id))
        if not vendor:
            raise ExtractionServiceError(f"Vendor with ID '{vendor_id}' not found.")

        # 2. Verify document and vendor ownership
        doc = db.get(VendorDocument, str(document_id))
        if not doc or str(doc.vendor_id) != str(vendor_id):
            raise ExtractionServiceError(f"Document with ID '{document_id}' not found for vendor '{vendor_id}'.")

        # 3. Retrieve and decrypt document content
        try:
            content = self.storage.retrieve_document(doc.storage_identifier)
        except Exception as e:
            logger.error("Failed to retrieve decrypted document '%s': %s", document_id, type(e).__name__)
            raise ExtractionServiceError(f"Failed to access secure document storage ({type(e).__name__}).")

        # 4. Resolve document category to guide schema extraction
        if category_override and str(category_override).strip():
            category_used = str(category_override).strip().upper()
        else:
            latest_cls = doc.latest_classification
            if (
                latest_cls
                and latest_cls.status == "CLASSIFIED"
                and latest_cls.predicted_category not in ("UNKNOWN", "OTHER")
                and doc.document_category == "OTHER"
            ):
                category_used = latest_cls.predicted_category
            else:
                category_used = doc.document_category

        # 5. Execute OCR / text recognition pipeline
        ocr_result = self.ocr.process(content, doc.mime_type, doc.original_filename)

        # 6. Execute deterministic schema parser with explainable confidence assessment
        parsed_fields = self.parser.parse(
            document_id=str(document_id),
            category=category_used,
            ocr_result=ocr_result,
        )

        # 7. Evaluate overall extraction run status
        extracted_count = sum(1 for f in parsed_fields.values() if f.status == FieldStatus.EXTRACTED)
        needs_review_count = sum(1 for f in parsed_fields.values() if f.status == FieldStatus.NEEDS_REVIEW)

        if ocr_result.limitation_code in (
            ExtractionLimitationCode.ENCRYPTED_PDF.value,
            ExtractionLimitationCode.CORRUPTED_DOCUMENT.value,
            ExtractionLimitationCode.UNSUPPORTED_FORMAT.value,
        ):
            status = ExtractionStatus.FAILED
            limitation_code = ocr_result.limitation_code
        elif ocr_result.limitation_code in (
            ExtractionLimitationCode.INSUFFICIENT_READABLE_TEXT.value,
            ExtractionLimitationCode.OCR_ENGINE_UNAVAILABLE.value,
        ):
            status = ExtractionStatus.INSUFFICIENT_TEXT
            limitation_code = ocr_result.limitation_code
        elif extracted_count == len(parsed_fields) and len(parsed_fields) > 0:
            status = ExtractionStatus.COMPLETED
            limitation_code = None
        elif extracted_count > 0 or needs_review_count > 0:
            status = ExtractionStatus.PARTIAL
            limitation_code = None
        else:
            status = ExtractionStatus.INSUFFICIENT_TEXT
            limitation_code = ExtractionLimitationCode.INSUFFICIENT_READABLE_TEXT.value

        # 8. Serialize fields dictionary for persistent JSON storage
        fields_json = {k: v.model_dump() for k, v in parsed_fields.items()}

        # 9. Create and persist DocumentExtraction record
        extraction = DocumentExtraction(
            document_id=str(doc.id),
            vendor_id=str(vendor.id),
            document_category_used=category_used,
            status=status.value,
            fields=fields_json,
            extracted_fields_count=extracted_count,
            extraction_engine_version="2.0.0",
            limitation_code=limitation_code,
        )
        db.add(extraction)

        # 10. Record safe lifecycle activity event
        safe_filename = sanitize_filename_for_activity(doc.sanitized_filename)
        review_note = f", {needs_review_count} needs review" if needs_review_count > 0 else ""
        activity = VendorActivity(
            vendor_id=str(vendor.id),
            event_type="DOCUMENT_EXTRACTED",
            title="Document Information Extracted",
            description=(
                f"Document '{safe_filename}' extracted as {category_used} "
                f"[{status.value}, {extracted_count}/{len(parsed_fields)} fields extracted{review_note}]."
            ),
            status=status.value,
        )
        db.add(activity)

        try:
            db.commit()
            db.refresh(extraction)
            logger.info(
                "Document '%s' successfully extracted: status=%s, fields=%d, needs_review=%d",
                document_id,
                status.value,
                extracted_count,
                needs_review_count,
            )
            return extraction
        except Exception as e:
            db.rollback()
            logger.error("Failed to persist document extraction: %s", type(e).__name__)
            raise ExtractionServiceError(f"Failed to persist extraction result ({type(e).__name__}).")

    def render_document_page_preview(
        self,
        db: Session,
        vendor_id: str,
        document_id: str,
        page_number: int = 1,
    ) -> Tuple[bytes, str, int]:
        """Renders a single page of an original document as a PNG image in memory.
        
        Returns:
            Tuple[image_bytes, mime_type, total_pages]
        """
        if page_number < 1:
            raise DocumentPreviewError("Page number must be at least 1.")

        doc = db.get(VendorDocument, str(document_id))
        if not doc or str(doc.vendor_id) != str(vendor_id):
            raise ExtractionServiceError(f"Document '{document_id}' not found for vendor '{vendor_id}'.")

        try:
            content = self.storage.retrieve_document(doc.storage_identifier)
        except Exception as e:
            logger.error("Failed to retrieve decrypted document '%s' for preview: %s", document_id, type(e).__name__)
            raise ExtractionServiceError(f"Failed to access document storage ({type(e).__name__}).")

        norm_mime = str(doc.mime_type or "").strip().lower()

        # 1. Image documents: serve the image bytes directly
        if norm_mime in ("image/png", "image/jpeg", "image/jpg"):
            if page_number != 1:
                raise DocumentPreviewError(f"Image document only has 1 page (requested page {page_number}).")
            return content, norm_mime, 1

        # 2. PDF documents: render the requested page via pdf2image
        if norm_mime == "application/pdf":
            try:
                reader = PdfReader(io.BytesIO(content))
                total_pages = len(reader.pages)
            except Exception as e:
                raise DocumentPreviewError(f"Invalid or corrupted PDF document ({type(e).__name__}).")

            if total_pages == 0:
                raise DocumentPreviewError("Document contains zero pages.")
            if page_number > total_pages:
                raise DocumentPreviewError(f"Page {page_number} exceeds total document pages ({total_pages}).")

            if not HAS_PREVIEW_IMAGING:
                raise DocumentPreviewError("PDF preview rendering engine is unavailable on host.")

            try:
                images = pdf2image.convert_from_bytes(
                    content,
                    first_page=page_number,
                    last_page=page_number,
                    size=(1800, None),
                )
                if not images:
                    raise DocumentPreviewError(f"Failed to render page {page_number}.")

                img_buf = io.BytesIO()
                images[0].save(img_buf, format="PNG")
                return img_buf.getvalue(), "image/png", total_pages
            except Exception as e:
                logger.error("Failed to render PDF page %d preview: %s", page_number, type(e).__name__)
                raise DocumentPreviewError(f"Failed to render page preview ({type(e).__name__}).")

        raise DocumentPreviewError(f"Unsupported document mime type '{doc.mime_type}' for preview.")

    def get_latest_extraction(
        self,
        db: Session,
        vendor_id: str,
        document_id: str,
    ) -> Optional[DocumentExtraction]:
        """Retrieves the most recent extraction record for a document."""
        doc = db.get(VendorDocument, str(document_id))
        if not doc or str(doc.vendor_id) != str(vendor_id):
            raise ExtractionServiceError(f"Document '{document_id}' not found for vendor '{vendor_id}'.")

        stmt = (
            select(DocumentExtraction)
            .where(
                DocumentExtraction.document_id == str(document_id),
                DocumentExtraction.vendor_id == str(vendor_id),
            )
            .order_by(desc(DocumentExtraction.created_at))
            .limit(1)
        )
        return db.scalar(stmt)

    def get_extraction_history(
        self,
        db: Session,
        vendor_id: str,
        document_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[DocumentExtraction], int, int]:
        """Retrieves paginated extraction runs for a document in reverse chronological order."""
        doc = db.get(VendorDocument, str(document_id))
        if not doc or str(doc.vendor_id) != str(vendor_id):
            raise ExtractionServiceError(f"Document '{document_id}' not found for vendor '{vendor_id}'.")

        total_stmt = (
            select(func.count(DocumentExtraction.id))
            .where(
                DocumentExtraction.document_id == str(document_id),
                DocumentExtraction.vendor_id == str(vendor_id),
            )
        )
        total = db.scalar(total_stmt) or 0
        total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 1

        offset = (page - 1) * page_size
        items_stmt = (
            select(DocumentExtraction)
            .where(
                DocumentExtraction.document_id == str(document_id),
                DocumentExtraction.vendor_id == str(vendor_id),
            )
            .order_by(desc(DocumentExtraction.created_at))
            .offset(offset)
            .limit(page_size)
        )
        items = list(db.scalars(items_stmt).all())
        return items, total, total_pages

    def list_vendor_extractions(
        self,
        db: Session,
        vendor_id: str,
    ) -> List[DocumentExtraction]:
        """Lists latest extraction for each document belonging to a vendor."""
        stmt = (
            select(DocumentExtraction)
            .where(DocumentExtraction.vendor_id == str(vendor_id))
            .order_by(desc(DocumentExtraction.created_at))
        )
        return list(db.scalars(stmt).all())


extraction_service = ExtractionService()
