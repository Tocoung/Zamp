"""Pydantic schemas for vendor document intake, metadata, and responses."""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.classification import DocumentClassificationResponse
from app.schemas.extraction import DocumentExtractionResponse


class DocumentCategory(str, Enum):
    """Recognized document categories for vendor onboarding."""
    CERTIFICATE_OF_INCORPORATION = "CERTIFICATE_OF_INCORPORATION"
    TAX_CERTIFICATE = "TAX_CERTIFICATE"
    BANK_PROOF = "BANK_PROOF"
    ADDRESS_PROOF = "ADDRESS_PROOF"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class DocumentStatus(str, Enum):
    """Processing and lifecycle status of uploaded documents."""
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class VendorDocumentResponse(BaseModel):
    """Public metadata representation of a vendor document (strictly no internal paths)."""
    id: str = Field(..., examples=["123e4567-e89b-12d3-a456-426614174000"])
    vendor_id: str = Field(..., examples=["123e4567-e89b-12d3-a456-426614174000"])
    original_filename: str = Field(..., examples=["tax_certificate_2024.pdf"])
    sanitized_filename: str = Field(..., examples=["tax_certificate_2024.pdf"])
    document_category: str = Field(..., examples=["TAX_CERTIFICATE"])
    mime_type: str = Field(..., examples=["application/pdf"])
    file_extension: str = Field(..., examples=[".pdf"])
    file_size_bytes: int = Field(..., examples=[1048576])
    sha256_checksum: str = Field(..., examples=["e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"])
    upload_status: str = Field(..., examples=["UPLOADED"])
    document_version: int = Field(..., examples=[1])
    latest_classification: Optional[DocumentClassificationResponse] = None
    latest_extraction: Optional[DocumentExtractionResponse] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VendorDocumentPagination(BaseModel):
    """Paginated collection of vendor documents."""
    items: List[VendorDocumentResponse]
    total: int = Field(..., examples=[5])
    page: int = Field(..., examples=[1])
    page_size: int = Field(..., examples=[20])
    total_pages: int = Field(..., examples=[1])
