"""Pydantic schemas for document OCR and structured information extraction."""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class FieldStatus(str, Enum):
    """Status of an individual extracted field."""
    EXTRACTED = "EXTRACTED"        # Value successfully parsed with supporting source evidence
    MISSING = "MISSING"            # Field could not be found in the readable document content
    UNREADABLE = "UNREADABLE"      # Field appears present but cannot be reliably recognized
    NEEDS_REVIEW = "NEEDS_REVIEW"  # Value found but interpretation is ambiguous or uncertain


class ExtractionStatus(str, Enum):
    """Overall execution status of a document extraction run."""
    COMPLETED = "COMPLETED"                # Extraction finished with core fields parsed
    PARTIAL = "PARTIAL"                    # Extraction completed but some fields are missing or unreadable
    INSUFFICIENT_TEXT = "INSUFFICIENT_TEXT"# No readable digital text and OCR yielded empty text
    FAILED = "FAILED"                      # Processing error, encrypted payload, or exceeded limits


class ExtractionLimitationCode(str, Enum):
    """Standardized machine-readable limitation and error codes."""
    OCR_ENGINE_UNAVAILABLE = "OCR_ENGINE_UNAVAILABLE"
    PAGE_LIMIT_EXCEEDED = "PAGE_LIMIT_EXCEEDED"
    DIMENSION_LIMIT_EXCEEDED = "DIMENSION_LIMIT_EXCEEDED"
    TIMEOUT_EXCEEDED = "TIMEOUT_EXCEEDED"
    ENCRYPTED_PDF = "ENCRYPTED_PDF"
    CORRUPTED_DOCUMENT = "CORRUPTED_DOCUMENT"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    INSUFFICIENT_READABLE_TEXT = "INSUFFICIENT_READABLE_TEXT"


class FieldSource(BaseModel):
    """Provenance tracking describing exactly where a field was extracted."""
    model_config = ConfigDict(from_attributes=True)

    document_id: str = Field(..., description="ID of the original source document")
    page_number: int = Field(..., ge=1, description="Original 1-indexed document page number")
    extraction_method: str = Field(..., description="Method: DIGITAL_TEXT or OCR")
    evidence_location: Optional[str] = Field(None, description="Location description within page (e.g. line or section)")
    evidence_snippet: Optional[str] = Field(None, description="Sanitized contextual text snippet supporting the extracted value")


class ExtractedField(BaseModel):
    """Structured representation of a single extracted attribute with field-level provenance."""
    model_config = ConfigDict(from_attributes=True)

    field_name: str = Field(..., description="Attribute name according to document schema")
    value: Optional[str] = Field(None, description="Parsed normalized string or ISO 8601 date, or null if absent")
    masked_value: Optional[str] = Field(None, description="Safe masked representation for standard frontend display")
    status: FieldStatus = Field(..., description="Extraction outcome for this field")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Field extraction quality/confidence score")
    source: FieldSource = Field(..., description="Source document and page provenance")
    limitation_or_reason: Optional[str] = Field(None, description="Reason if field is missing, unreadable, or needs review")


class DocumentExtractionResponse(BaseModel):
    """API response schema for a document extraction run."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    vendor_id: str
    document_category_used: str
    status: ExtractionStatus
    fields: Dict[str, ExtractedField] = Field(default_factory=dict)
    extracted_fields_count: int = 0
    extraction_engine_version: str = "1.0.0"
    limitation_code: Optional[str] = None
    created_at: datetime


class DocumentExtractionHistoryPagination(BaseModel):
    """Paginated response for extraction history."""
    items: List[DocumentExtractionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
