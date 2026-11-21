"""Structured models for the Deterministic Validation Engine."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field, ConfigDict


class Severity(str, Enum):
    """Validation finding severity level."""
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class FindingStatus(str, Enum):
    """Finding outcome status."""
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ValidationStatus(str, Enum):
    """Overall validation evaluation status."""
    PASSED = "PASSED"
    PASSED_WITH_WARNINGS = "PASSED_WITH_WARNINGS"
    FAILED = "FAILED"


class ValidationFinding(BaseModel):
    """Individual field-level or cross-field validation finding."""
    rule_id: str = Field(..., examples=["COMPANY_LEGAL_NAME_REQUIRED"])
    field: str = Field(..., examples=["legal_name"])
    severity: Severity = Field(..., examples=[Severity.ERROR])
    status: FindingStatus = Field(FindingStatus.FAILED, examples=[FindingStatus.FAILED])
    code: str = Field(..., examples=["REQUIRED_FIELD_MISSING"])
    message: str = Field(..., examples=["Legal company name is required."])
    suggestion: Optional[str] = Field(None, examples=["Provide the registered legal entity name."])

    model_config = ConfigDict(frozen=True)


class ValidationSummary(BaseModel):
    """Summary metrics of executed validation checks."""
    total_checks: int = Field(..., ge=0, examples=[19])
    passed: int = Field(..., ge=0, examples=[17])
    failed: int = Field(..., ge=0, examples=[1])
    warnings: int = Field(..., ge=0, examples=[1])
    info: int = Field(0, ge=0, examples=[0])


class ValidationResult(BaseModel):
    """Complete, structured validation evaluation result."""
    validation_id: str = Field(default_factory=lambda: str(uuid4()))
    vendor_id: Optional[str] = Field(None, examples=["123e4567-e89b-12d3-a456-426614174000"])
    status: ValidationStatus = Field(..., examples=[ValidationStatus.FAILED])
    valid: bool = Field(..., description="True only when there are zero ERROR findings.")
    summary: ValidationSummary
    findings: List[ValidationFinding] = Field(default_factory=list)
    validated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ruleset_version: str = Field("1.0.0", examples=["1.0.0"])

    model_config = ConfigDict(from_attributes=True)


class VendorValidationRequest(BaseModel):
    """Flexible payload for validating unsaved vendor data (supports partial or complete forms)."""
    legal_name: Optional[str] = None
    trade_name: Optional[str] = None
    business_type: Optional[str] = None
    country_of_incorporation: Optional[str] = None
    registration_number: Optional[str] = None

    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None

    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state_province: Optional[str] = None
    postal_code: Optional[str] = None
    address_country: Optional[str] = None

    tax_id_type: Optional[str] = None
    tax_id_number: Optional[str] = None

    bank_account_holder_name: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_routing_number: Optional[str] = None
    bank_country: Optional[str] = None

    model_config = ConfigDict(extra="ignore")
