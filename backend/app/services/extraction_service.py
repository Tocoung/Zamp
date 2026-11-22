"""Extraction service coordinating OCR, structured field parsing, persistence, and audit activities."""

from typing import List, Optional, Tuple
from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

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
            # Check latest classification result as a guiding hint if available
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

        # 6. Execute deterministic schema parser
        parsed_fields = self.parser.parse(
            document_id=str(document_id),
            category=category_used,
            ocr_result=ocr_result,
        )

        # 7. Evaluate overall extraction run status
        extracted_count = sum(1 for f in parsed_fields.values() if f.status == FieldStatus.EXTRACTED)

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
        elif extracted_count > 0:
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
            extraction_engine_version="1.0.0",
            limitation_code=limitation_code,
        )
        db.add(extraction)

        # 10. Record safe lifecycle activity event
        safe_filename = sanitize_filename_for_activity(doc.sanitized_filename)
        activity = VendorActivity(
            vendor_id=str(vendor.id),
            event_type="DOCUMENT_EXTRACTED",
            title="Document Information Extracted",
            description=(
                f"Document '{safe_filename}' extracted as {category_used} "
                f"[{status.value}, {extracted_count}/{len(parsed_fields)} fields extracted]."
            ),
            status=status.value,
        )
        db.add(activity)

        try:
            db.commit()
            db.refresh(extraction)
            logger.info(
                "Document '%s' successfully extracted: status=%s, fields=%d",
                document_id,
                status.value,
                extracted_count,
            )
            return extraction
        except Exception as e:
            db.rollback()
            logger.error("Failed to persist document extraction: %s", type(e).__name__)
            raise ExtractionServiceError(f"Failed to persist extraction result ({type(e).__name__}).")

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
