"""Data models and schemas for the deterministic decision engine."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DecisionStatus(str, Enum):
    """Deterministic decision outcomes for vendor onboarding."""
    APPROVED = "APPROVED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"


class DecisionAction(str, Enum):
    """Action mapped from validation findings to govern decision outcomes."""
    BLOCK = "BLOCK"      # Forces REJECTED outcome
    REVIEW = "REVIEW"    # Forces PENDING outcome for human evaluation
    IGNORE = "IGNORE"    # Informational only; does not impede APPROVED outcome


class DecisionReason(BaseModel):
    """Structured explanation for a decision outcome."""
    code: str = Field(..., description="Stable programmatic reason code")
    title: str = Field(..., description="Human-readable reason title")
    explanation: str = Field(..., description="Detailed explanation of the underlying condition")
    source_rule_id: Optional[str] = Field(None, description="Originating validation rule ID if derived from a finding")
    source_finding_code: Optional[str] = Field(None, description="Originating finding code if derived from a finding")
    severity: str = Field("INFO", description="Original finding severity or reason level: ERROR, WARNING, INFO")

    model_config = ConfigDict(frozen=True)


class DecisionRecommendation(BaseModel):
    """Actionable recommendation for resolving decision conditions or completing onboarding."""
    action: str = Field(..., description="Programmatic action identifier (e.g., VERIFY_ACCOUNT_HOLDER)")
    description: str = Field(..., description="Actionable guidance for vendor or operations team")
    priority: str = Field("MEDIUM", description="Action priority: HIGH, MEDIUM, LOW")

    model_config = ConfigDict(frozen=True)


class DecisionResult(BaseModel):
    """Complete structured decision result produced by the decision engine."""
    decision_id: str = Field(..., description="Unique decision UUID")
    vendor_id: str = Field(..., description="Associated vendor UUID")
    status: DecisionStatus = Field(..., description="Final decision outcome: APPROVED, PENDING, or REJECTED")
    decision_version: str = Field("1.0.0", description="Decision engine logic version")
    ruleset_version: str = Field("1.0.0", description="Validation ruleset version evaluated")
    validation_id: str = Field(..., description="ID of the validation execution used as decision evidence")
    validation_status: str = Field(..., description="Outcome of the validation execution (PASSED, PASSED_WITH_WARNINGS, FAILED)")
    reason_codes: List[str] = Field(default_factory=list, description="List of unique reason codes leading to this decision")
    reasons: List[DecisionReason] = Field(default_factory=list, description="Structured explanations for the decision")
    recommendations: List[DecisionRecommendation] = Field(default_factory=list, description="Actionable next steps")
    validation_snapshot: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Sanitized snapshot of validation summary and findings (no raw banking data)",
    )
    decided_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the decision was computed (UTC)",
    )

    model_config = ConfigDict(from_attributes=True)


class DecisionHistoryItem(BaseModel):
    """Historical decision record representation."""
    id: str = Field(..., description="Decision UUID")
    vendor_id: str = Field(..., description="Associated vendor UUID")
    status: DecisionStatus = Field(..., description="Decision outcome")
    decision_version: str = Field(..., description="Decision engine version")
    ruleset_version: str = Field(..., description="Validation ruleset version")
    validation_id: str = Field(..., description="Associated validation ID")
    reason_codes: List[str] = Field(default_factory=list)
    reasons: List[DecisionReason] = Field(default_factory=list)
    recommendations: List[DecisionRecommendation] = Field(default_factory=list)
    decided_at: datetime = Field(..., description="Decision timestamp (UTC)")

    model_config = ConfigDict(from_attributes=True)


class DecisionHistoryPagination(BaseModel):
    """Paginated collection of decision history records."""
    items: List[DecisionHistoryItem]
    total: int
    page: int
    page_size: int
    total_pages: int
