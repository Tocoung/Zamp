"""Service layer coordinating document classification execution, persistence, and audit logging."""

import math
import uuid
from typing import List, Optional, Tuple
from sqlalchemy import select, func, desc, asc
from sqlalchemy.orm import Session

from app.models.vendor import Vendor
from app.models.document import VendorDocument
from app.models.activity import VendorActivity
from app.models.classification import DocumentClassification
from app.services.vendor_service import VendorNotFoundError
from app.services.document_service import document_service, DocumentNotFoundError, DocumentServiceError
from app.classification.engine import classification_engine, ClassificationEngine
from app.classification.privacy import sanitize_filename_for_activity
from app.core.logging import logger


class ClassificationServiceError(Exception):
    """Base exception for document classification service domain errors."""
    pass


class ClassificationNotFoundError(ClassificationServiceError):
    """Raised when no classification record exists for the requested document."""
    pass


class ClassificationService:
    """Coordinates deterministic document classification, persistence, and lifecycle logging."""

    def __init__(self, engine: ClassificationEngine = classification_engine):
        self.engine = engine

    def classify_vendor_document(
        self,
        db: Session,
        vendor_id: str,
        document_id: str,
    ) -> DocumentClassification:
        """Executes deterministic classification on a vendor document and records the result.
        
        Args:
            db: Database session.
            vendor_id: UUID string of the vendor entity.
            document_id: UUID string of the document entity.
            
        Returns:
            Newly created DocumentClassification entity.
            
        Raises:
            VendorNotFoundError: If vendor record does not exist.
            DocumentNotFoundError: If document record does not exist or does not belong to vendor.
            ClassificationServiceError: If decryption or persistence fails.
        """
        # 1. Verify vendor and document access
        vendor = db.get(Vendor, str(vendor_id))
        if not vendor:
            raise VendorNotFoundError(f"Vendor with ID '{vendor_id}' not found.")

        # Document service verifies vendor ownership and retrieves decrypted payload
        doc, content = document_service.retrieve_document_content(
            db=db,
            vendor_id=vendor_id,
            document_id=document_id,
        )

        # 2. Run pure deterministic classification engine
        try:
            result = self.engine.classify(
                content=content,
                filename=doc.sanitized_filename,
                mime_type=doc.mime_type,
            )
        except Exception as e:
            logger.error("Classification engine failed unexpectedly for doc_id=%s: %s", doc.id, e)
            raise ClassificationServiceError(f"Classification execution failed: {type(e).__name__}") from e

        # 3. Create persistent classification audit record
        classification_id = str(uuid.uuid4())
        classification = DocumentClassification(
            id=classification_id,
            document_id=doc.id,
            vendor_id=vendor.id,
            predicted_category=result.predicted_category,
            status=result.status.value,
            confidence_score=result.confidence_score,
            evidence=result.evidence,
            limitation_code=result.limitation_code,
            classifier_version=result.classifier_version,
        )

        # 4. Record lifecycle audit event (vendor compliance status is NEVER altered)
        safe_filename = sanitize_filename_for_activity(doc.sanitized_filename)
        activity = VendorActivity(
            vendor_id=vendor.id,
            event_type="DOCUMENT_CLASSIFIED",
            title="Supporting Document Classified",
            description=(
                f"Document '{safe_filename}' classified as {result.predicted_category} "
                f"[{result.status.value}, rule-based match score: {result.confidence_score:.2f}]."
            ),
            status=vendor.status,
        )

        # 5. Atomic persistence
        try:
            db.add(classification)
            db.add(activity)
            db.commit()
            db.refresh(classification)
            logger.info(
                "Document classified successfully: class_id=%s, doc_id=%s, predicted=%s, status=%s, rule_based_score=%.2f",
                classification.id,
                doc.id,
                classification.predicted_category,
                classification.status,
                classification.confidence_score,
            )
            return classification
        except Exception as e:
            db.rollback()
            logger.error("Failed to persist document classification result: %s", type(e).__name__)
            raise ClassificationServiceError("Failed to persist classification record. Transaction rolled back.") from e

    def get_latest_classification(
        self,
        db: Session,
        vendor_id: str,
        document_id: str,
    ) -> Optional[DocumentClassification]:
        """Retrieves the most recent classification record for a document verified against vendor."""
        # Ensure document belongs to vendor
        document_service.get_document_metadata(db=db, vendor_id=vendor_id, document_id=document_id)

        stmt = (
            select(DocumentClassification)
            .where(
                DocumentClassification.document_id == str(document_id),
                DocumentClassification.vendor_id == str(vendor_id),
            )
            .order_by(
                desc(DocumentClassification.created_at),
                desc(DocumentClassification.id),
            )
        )
        return db.scalar(stmt)

    def get_classification_history(
        self,
        db: Session,
        vendor_id: str,
        document_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[DocumentClassification], int, int]:
        """Returns paginated historical classification runs for a document."""
        # Ensure document belongs to vendor
        document_service.get_document_metadata(db=db, vendor_id=vendor_id, document_id=document_id)

        base_query = select(DocumentClassification).where(
            DocumentClassification.document_id == str(document_id),
            DocumentClassification.vendor_id == str(vendor_id),
        )
        count_query = select(func.count(DocumentClassification.id)).where(
            DocumentClassification.document_id == str(document_id),
            DocumentClassification.vendor_id == str(vendor_id),
        )

        total = db.scalar(count_query) or 0
        total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1

        offset = (page - 1) * page_size
        items = list(
            db.scalars(
                base_query.order_by(
                    desc(DocumentClassification.created_at),
                    desc(DocumentClassification.id),
                )
                .offset(offset)
                .limit(page_size)
            ).all()
        )

        return items, total, total_pages

    # Alias for convenience
    classify_document = classify_vendor_document


# Default singleton service instance
classification_service = ClassificationService()
