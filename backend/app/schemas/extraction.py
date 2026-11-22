"""Pydantic schemas for document OCR and structured information extraction."""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, ConfigDict, Field, model_validator


class FieldStatus(str, Enum):
    """Status of an individual extracted field."""
    EXTRACTED = "EXTRACTED"        # Value extracted with sufficient evidence and valid syntax
    NEEDS_REVIEW = "NEEDS_REVIEW"  # Candidate exists but interpretation is ambiguous or low confidence
    MISSING = "MISSING"            # Field is genuinely absent from readable document content
    UNREADABLE = "UNREADABLE"      # Field label/region detected but value is illegible or corrupted


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


class QualityBreakdown(BaseModel):
    """Measured signal breakdown contributing to a field's extraction quality score."""
    model_config = ConfigDict(from_attributes=True)

    source_quality: float = Field(0.0, ge=0.0, le=1.0, description="Fidelity of text source (Digital vs OCR)")
    label_match: float = Field(0.0, ge=0.0, le=1.0, description="Strength of association with field label")
    format_validity: float = Field(0.0, ge=0.0, le=1.0, description="Conformance with statutory syntax/pattern")
    normalization_adjustment: float = Field(0.0, ge=0.0, le=1.0, description="Penalties for ambiguity or repair")
    ambiguity_penalty: float = Field(1.0, ge=0.0, le=1.0, description="Penalty for multiple competing candidates")
    provenance_quality: float = Field(0.0, ge=0.0, le=1.0, description="Completeness of document/page location")


class FieldSource(BaseModel):
    """Provenance tracking describing exactly where a field was extracted."""
    model_config = ConfigDict(from_attributes=True)

    document_id: Optional[str] = Field(None, description="ID of the original source document")
    page_number: Optional[int] = Field(None, ge=1, description="Original 1-indexed document page number, or null if absent")
    extraction_method: Optional[str] = Field(None, description="Method: DIGITAL_TEXT, OCR, or null if absent")
    evidence_location: Optional[str] = Field(None, description="Location description within page (e.g. line or section)")
    evidence_snippet: Optional[str] = Field(None, description="Sanitized contextual text snippet supporting the extracted value")
    bounding_box: Optional[Dict[str, float]] = Field(None, description="Normalized coordinates of the source text")


class ExtractedField(BaseModel):
    """Structured representation of a single extracted attribute with field-level provenance."""
    model_config = ConfigDict(from_attributes=True)

    field_name: str = Field(..., description="Attribute name according to document schema")
    value: Optional[str] = Field(None, description="Parsed normalized string or ISO 8601 date, or null if absent")
    masked_value: Optional[str] = Field(None, description="Safe masked representation for standard frontend display")
    status: FieldStatus = Field(..., description="Extraction outcome for this field")
    quality_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Deterministic evidence quality score [0.0 - 1.0]")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Legacy/alias confidence score for backward compatibility")
    quality_breakdown: Optional[QualityBreakdown] = Field(None, description="Measured signal breakdown")
    quality_explanation: Optional[str] = Field(None, description="Human-readable explanation of the quality score")
    normalization_notes: Optional[str] = Field(None, description="Notes on transformations applied during normalization")
    source: Optional[FieldSource] = Field(None, description="Source document and page provenance (null for MISSING fields)")
    limitation_or_reason: Optional[str] = Field(None, description="Reason if field is missing, unreadable, or needs review")

    @model_validator(mode="before")
    @classmethod
    def sync_confidence_and_quality(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Sync quality_score and confidence for bidirectional backward compatibility
            qs = data.get("quality_score")
            conf = data.get("confidence")
            if qs is None and conf is not None:
                data["quality_score"] = conf
            elif conf is None and qs is not None:
                data["confidence"] = qs
            # If source has no document_id or page_number and status is MISSING, allow None
            if data.get("status") == "MISSING" and data.get("source") is None:
                data["source"] = None
        return data


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
    needs_review_fields_count: int = 0
    extraction_engine_version: str = "2.0.0"
    limitation_code: Optional[str] = None
    created_at: datetime


class DocumentExtractionHistoryPagination(BaseModel):
    """Paginated response for extraction history."""
    items: List[DocumentExtractionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
