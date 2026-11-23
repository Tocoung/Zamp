"""Pydantic schemas for cross-document validation and discrepancy detection."""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, ConfigDict, Field


class VerificationRunStatus(str, Enum):
    """Overall status of a verification execution."""
    NOT_RUN = "NOT_RUN"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_FINDINGS = "COMPLETED_WITH_FINDINGS"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    INCOMPLETE = "INCOMPLETE"
    FAILED = "FAILED"


class FindingResult(str, Enum):
    """Outcome classification of an individual field comparison."""
    MATCH = "MATCH"
    CONFIRMED_DISCREPANCY = "CONFIRMED_DISCREPANCY"
    POTENTIAL_DISCREPANCY = "POTENTIAL_DISCREPANCY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    MISSING_DOCUMENT = "MISSING_DOCUMENT"
    UNSUPPORTED_DOCUMENT = "UNSUPPORTED_DOCUMENT"


class FindingSeverity(str, Enum):
    """Operational severity of a finding."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class ComparisonType(str, Enum):
    """Methodology applied during verification comparison."""
    EXACT_IDENTIFIER = "EXACT_IDENTIFIER"
    DATE = "DATE"
    STRUCTURED_TEXT = "STRUCTURED_TEXT"
    FUZZY_NAME = "FUZZY_NAME"
    FUZZY_ADDRESS = "FUZZY_ADDRESS"
    UNSUPPORTED = "UNSUPPORTED"


class EvidenceSourceType(str, Enum):
    """Origin of a compared data point."""
    VENDOR_PROFILE = "VENDOR_PROFILE"
    EXTRACTED_DOCUMENT_FIELD = "EXTRACTED_DOCUMENT_FIELD"


class EvidenceSource(BaseModel):
    """Traceable provenance and evidence context for a compared value."""
    model_config = ConfigDict(from_attributes=True)

    source_type: EvidenceSourceType = Field(..., description="VENDOR_PROFILE or EXTRACTED_DOCUMENT_FIELD")
    field_name: str = Field(..., description="Target attribute in the source")
    value_display: Optional[str] = Field(None, description="Masked/sanitized display value; zero full account numbers")
    document_id: Optional[str] = Field(None, description="UUID of source document (if applicable)")
    document_name: Optional[str] = Field(None, description="Filename of source document")
    document_category: Optional[str] = Field(None, description="Category of source document")
    extraction_id: Optional[str] = Field(None, description="UUID of source extraction run")
    page_number: Optional[int] = Field(None, ge=1, description="1-based page number where evidence appears")
    extraction_method: Optional[str] = Field(None, description="DIGITAL_TEXT or OCR")
    extraction_status: Optional[str] = Field(None, description="EXTRACTED, NEEDS_REVIEW, MISSING, UNREADABLE")
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Extraction evidence quality score")
    sanitized_snippet: Optional[str] = Field(None, description="Sanitized contextual snippet from original source")


class VerificationFindingResponse(BaseModel):
    """Detailed finding of a single field comparison."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    verification_run_id: str
    field_name: str
    comparison_type: str
    result: FindingResult
    severity: FindingSeverity
    explanation: str
    similarity_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    comparison_summary: Optional[str] = None
    evidence_sources: List[EvidenceSource] = Field(default_factory=list)
    created_at: datetime


class VerificationRunSummary(BaseModel):
    """Summary overview of a verification run."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    vendor_id: str
    status: VerificationRunStatus
    ruleset_version: str
    total_comparisons: int
    matches: int
    confirmed_discrepancies: int
    potential_discrepancies: int
    insufficient_evidence: int
    missing_documents: int
    unsupported_documents: int
    summary_notes: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class VerificationRunResponse(VerificationRunSummary):
    """Full API response for a verification run with detailed findings."""
    findings: List[VerificationFindingResponse] = Field(default_factory=list)


class VerificationHistoryResponse(BaseModel):
    """Paginated list of previous verification executions."""
    model_config = ConfigDict(from_attributes=True)

    total: int
    page: int
    page_size: int
    items: List[VerificationRunSummary]
