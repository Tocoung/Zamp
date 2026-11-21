"""Service layer for vendor document intake, retrieval, deletion, and lifecycle logging."""

import math
import uuid
from typing import List, Optional, Tuple
from sqlalchemy import select, func, desc, asc
from sqlalchemy.orm import Session

from app.models.vendor import Vendor
from app.models.document import VendorDocument
from app.models.activity import VendorActivity
from app.schemas.document import DocumentCategory, DocumentStatus
from app.core.storage import document_storage, StorageError, StorageFileNotFoundError, StorageDecryptionError
from app.core.document_validator import validate_document_upload, DocumentValidationError
from app.services.vendor_service import VendorNotFoundError
from app.core.logging import logger


class DocumentServiceError(Exception):
    """Base exception for document service domain errors."""
    pass


class DocumentNotFoundError(DocumentServiceError):
    """Raised when a requested document record does not exist or does not belong to the vendor."""
    pass


def format_file_size(size_bytes: int) -> str:
    """Helper to format byte count into human-readable string (KB/MB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


class DocumentService:
    """Coordinates document storage, database records, and lifecycle activity events."""

    def __init__(self, storage=document_storage):
        self.storage = storage

    def upload_vendor_document(
        self,
        db: Session,
        vendor_id: str,
        filename: str,
        declared_content_type: Optional[str],
        content: bytes,
        category: Optional[str] = None,
    ) -> VendorDocument:
        """Validates, encrypts, and persists a supporting document for an existing vendor."""
        # 1. Verify vendor existence
        vendor = db.get(Vendor, str(vendor_id))
        if not vendor:
            raise VendorNotFoundError(f"Vendor with ID '{vendor_id}' not found.")

        # 2. Strict format, extension, size, and magic signature validation
        sanitized_filename, canonical_mime, file_extension, file_size_bytes = validate_document_upload(
            filename=filename,
            declared_content_type=declared_content_type,
            content=content,
        )

        # 3. Normalize category
        normalized_category = "OTHER"
        if category and str(category).strip():
            candidate = str(category).strip().upper()
            valid_categories = {c.value for c in DocumentCategory}
            if candidate in valid_categories:
                normalized_category = candidate

        # 4. Content integrity checksum
        sha256_checksum = self.storage.calculate_sha256(content)

        # 5. Determine document category version
        prior_version_count = db.scalar(
            select(func.count(VendorDocument.id)).where(
                VendorDocument.vendor_id == vendor.id,
                VendorDocument.document_category == normalized_category,
            )
        ) or 0
        document_version = prior_version_count + 1

        # 6. Generate UUID and persist encrypted file to disk
        document_id = str(uuid.uuid4())
        try:
            storage_identifier = self.storage.store_document(
                vendor_id=vendor.id,
                document_id=document_id,
                content=content,
            )
        except Exception as e:
            logger.error("Failed to store encrypted document for vendor_id=%s: %s", vendor.id, e)
            raise DocumentServiceError(f"Secure document storage failed: {e}") from e

        # 7. Create database entity
        doc = VendorDocument(
            id=document_id,
            vendor_id=vendor.id,
            original_filename=filename,
            sanitized_filename=sanitized_filename,
            document_category=normalized_category,
            mime_type=canonical_mime,
            file_extension=file_extension,
            file_size_bytes=file_size_bytes,
            storage_identifier=storage_identifier,
            sha256_checksum=sha256_checksum,
            upload_status=DocumentStatus.UPLOADED.value,
            document_version=document_version,
        )

        # 8. Record lightweight lifecycle activity
        activity = VendorActivity(
            vendor_id=vendor.id,
            event_type="DOCUMENT_UPLOADED",
            title="Supporting Document Uploaded",
            description=(
                f"Document uploaded: '{sanitized_filename}' "
                f"[{normalized_category}, {format_file_size(file_size_bytes)}]."
            ),
            status=vendor.status,
        )

        # 9. Atomic database commit with filesystem cleanup rollback
        try:
            db.add(doc)
            db.add(activity)
            db.commit()
            db.refresh(doc)
            logger.info(
                "Document uploaded successfully: doc_id=%s, vendor_id=%s, category=%s, filename=%s",
                doc.id,
                vendor.id,
                doc.document_category,
                doc.sanitized_filename,
            )
            return doc
        except Exception as e:
            db.rollback()
            # Clean up the encrypted file from storage to prevent orphan storage leakage
            self.storage.delete_document(storage_identifier)
            logger.error("Database persistence failed for document; storage rolled back: %s", e)
            raise DocumentServiceError("Failed to persist document metadata. Transaction rolled back.") from e

    def list_vendor_documents(
        self,
        db: Session,
        vendor_id: str,
        category: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[VendorDocument], int, int]:
        """Returns paginated document metadata for a vendor in deterministic order."""
        vendor = db.get(Vendor, str(vendor_id))
        if not vendor:
            raise VendorNotFoundError(f"Vendor with ID '{vendor_id}' not found.")

        query = select(VendorDocument).where(VendorDocument.vendor_id == vendor.id)
        count_query = select(func.count(VendorDocument.id)).where(VendorDocument.vendor_id == vendor.id)

        if category and str(category).strip():
            cat_upper = str(category).strip().upper()
            query = query.where(VendorDocument.document_category == cat_upper)
            count_query = count_query.where(VendorDocument.document_category == cat_upper)

        total = db.scalar(count_query) or 0
        total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1

        offset = (page - 1) * page_size
        docs = list(
            db.scalars(
                query.order_by(
                    desc(VendorDocument.created_at),
                    asc(VendorDocument.id),
                ).offset(offset).limit(page_size)
            ).all()
        )

        return docs, total, total_pages

    def get_document_metadata(
        self,
        db: Session,
        vendor_id: str,
        document_id: str,
    ) -> VendorDocument:
        """Retrieves metadata for a specific document verified against the vendor."""
        doc = db.scalar(
            select(VendorDocument).where(
                VendorDocument.id == str(document_id),
                VendorDocument.vendor_id == str(vendor_id),
            )
        )
        if not doc:
            raise DocumentNotFoundError(
                f"Document '{document_id}' not found for vendor '{vendor_id}'."
            )
        return doc

    def retrieve_document_content(
        self,
        db: Session,
        vendor_id: str,
        document_id: str,
    ) -> Tuple[VendorDocument, bytes]:
        """Retrieves and decrypts the original document bytes, verifying integrity."""
        doc = self.get_document_metadata(db=db, vendor_id=vendor_id, document_id=document_id)

        try:
            content = self.storage.retrieve_document(doc.storage_identifier)
        except StorageFileNotFoundError as e:
            logger.error("Stored document file is missing on disk: %s", doc.storage_identifier)
            raise DocumentServiceError("Document file is missing from secure storage.") from e
        except StorageDecryptionError as e:
            logger.error("Stored document file decryption failed: %s", doc.storage_identifier)
            raise DocumentServiceError("Document data integrity error: File decryption failed.") from e
        except Exception as e:
            logger.error("Failed to retrieve document: %s", e)
            raise DocumentServiceError(f"Document retrieval failed: {e}") from e

        # Checksum integrity verification
        current_checksum = self.storage.calculate_sha256(content)
        if current_checksum != doc.sha256_checksum:
            logger.error(
                "Document integrity failure: checksum mismatch: stored=%s, calculated=%s",
                doc.sha256_checksum,
                current_checksum,
            )
            raise DocumentServiceError("Document integrity check failed: Checksum mismatch.")

        return doc, content

    def delete_vendor_document(
        self,
        db: Session,
        vendor_id: str,
        document_id: str,
    ) -> bool:
        """Deletes a document record and its encrypted file on disk, logging the lifecycle event."""
        doc = self.get_document_metadata(db=db, vendor_id=vendor_id, document_id=document_id)
        storage_id = doc.storage_identifier
        category = doc.document_category
        filename = doc.sanitized_filename

        # Record activity event
        activity = VendorActivity(
            vendor_id=str(vendor_id),
            event_type="DOCUMENT_DELETED",
            title="Supporting Document Deleted",
            description=f"Document deleted: '{filename}' [{category}].",
            status=doc.vendor.status if doc.vendor else "SUBMITTED",
        )

        try:
            db.delete(doc)
            db.add(activity)
            db.commit()
            logger.info("Deleted document record: id=%s, vendor_id=%s", document_id, vendor_id)
        except Exception as e:
            db.rollback()
            logger.error("Failed to delete document from database: %s", e)
            raise DocumentServiceError("Failed to delete document record. Transaction rolled back.") from e

        # Remove physical file from disk
        try:
            self.storage.delete_document(storage_id)
        except Exception as e:
            logger.warning("Document file disk deletion encountered an issue (non-fatal): %s", e)

        return True


# Default service instance
document_service = DocumentService()
