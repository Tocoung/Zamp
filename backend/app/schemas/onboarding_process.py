"""Pydantic schemas for end-to-end onboarding orchestration runs."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class StageStatus(BaseModel):
    """Execution status for a single onboarding pipeline stage."""
    stage: str
    status: str = Field(description="PENDING, IN_PROGRESS, COMPLETED, SKIPPED, FAILED")
    details: Optional[Dict[str, Any]] = None
    message: Optional[str] = None


class DocumentProcessItem(BaseModel):
    """Status and metrics for an individual document evaluated in the workflow."""
    document_id: str
    file_name: str
    file_type: str
    category: Optional[str] = None
    classification_status: str
    classification_confidence: Optional[float] = None
    extraction_status: str
    extracted_fields_count: int = 0
    average_confidence: Optional[float] = None
    eligible_for_verification: bool = True
    error: Optional[str] = None


class OnboardingProcessRunResponse(BaseModel):
    """Complete summary response for an end-to-end onboarding processing run."""
    id: str
    vendor_id: str
    status: str
    trigger_source: str
    total_documents: int
    successful_documents: int
    failed_documents: int
    verification_run_id: Optional[str] = None
    decision_id: Optional[str] = None
    decision_status: Optional[str] = None
    decision_reasons: List[str] = Field(default_factory=list)
    stage_results: Dict[str, Any] = Field(default_factory=dict)
    document_breakdown: List[DocumentProcessItem] = Field(default_factory=list)
    findings_summary: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class OnboardingProcessHistoryResponse(BaseModel):
    """Paginated or listed history of onboarding processing runs for a vendor."""
    vendor_id: str
    total_runs: int
    runs: List[OnboardingProcessRunResponse]
