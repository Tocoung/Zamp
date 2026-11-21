"""Pydantic schemas for document classification contracts, explainability, and responses."""

from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class ClassificationStatus(str, Enum):
    """Operational status of a document classification execution."""
    CLASSIFIED = "CLASSIFIED"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    INSUFFICIENT_TEXT = "INSUFFICIENT_TEXT"
    FAILED = "FAILED"


class ClassificationLimitationCode(str, Enum):
    """Limitation and ambiguity reason codes for explainability."""
    NO_EXTRACTABLE_TEXT = "NO_EXTRACTABLE_TEXT"
    IMAGE_ONLY_DOCUMENT = "IMAGE_ONLY_DOCUMENT"
    AMBIGUOUS_SIGNALS = "AMBIGUOUS_SIGNALS"
    CONFLICTING_SIGNALS = "CONFLICTING_SIGNALS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class DocumentClassificationResponse(BaseModel):
    """Public representation of a document classification execution result."""
    id: str = Field(..., examples=["123e4567-e89b-12d3-a456-426614174000"])
    document_id: str = Field(..., examples=["123e4567-e89b-12d3-a456-426614174000"])
    vendor_id: str = Field(..., examples=["123e4567-e89b-12d3-a456-426614174000"])
    declared_category: str = Field(..., examples=["TAX_CERTIFICATE"])
    predicted_category: str = Field(..., examples=["TAX_CERTIFICATE"])
    status: ClassificationStatus = Field(..., examples=[ClassificationStatus.CLASSIFIED])
    confidence_score: float = Field(..., examples=[0.92])
    evidence: Dict[str, Any] = Field(default_factory=dict)
    limitation_code: Optional[str] = Field(None, examples=["CONFLICTING_SIGNALS"])
    classifier_version: str = Field(..., examples=["1.0.0"])
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentClassificationHistoryPagination(BaseModel):
    """Paginated collection of classification audit history records."""
    items: List[DocumentClassificationResponse]
    total: int = Field(..., examples=[1])
    page: int = Field(..., examples=[1])
    page_size: int = Field(..., examples=[20])
    total_pages: int = Field(..., examples=[1])
