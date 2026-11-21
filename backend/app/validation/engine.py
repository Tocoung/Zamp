"""Validation Engine orchestrator coordinating deterministic rule evaluation."""

import copy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4
from pydantic import BaseModel

from app.core.logging import logger
from app.validation.config import ValidationConfig
from app.validation.models import (
    Severity,
    ValidationFinding,
    ValidationResult,
    ValidationStatus,
    ValidationSummary,
)
from app.validation.registry import RuleRegistry, default_registry

SEVERITY_ORDER = {
    Severity.ERROR: 1,
    Severity.WARNING: 2,
    Severity.INFO: 3,
}


class ValidationEngine:
    """Deterministic validation orchestrator for vendor onboarding submissions."""

    def __init__(
        self,
        registry: Optional[RuleRegistry] = None,
        config: Optional[ValidationConfig] = None,
    ):
        self.registry = registry or default_registry
        self.config = config or ValidationConfig()

    def validate_vendor(
        self,
        vendor_data: Union[Dict[str, Any], BaseModel],
        vendor_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """Executes all active validation rules deterministically against vendor data.
        
        Guarantees:
        - Zero mutation of the input vendor representation.
        - Deterministic execution and finding ordering.
        - Collects all findings without short-circuiting on the first error.
        - Never exposes or logs sensitive values or account numbers.
        
        Args:
            vendor_data: Vendor dict or Pydantic model representation.
            vendor_id: Optional existing vendor ID if validating a persisted record.
            context: Additional evaluation context.
            
        Returns:
            Structured ValidationResult containing summary metrics and field findings.
        """
        # 1. Normalize data without mutating the input object
        if isinstance(vendor_data, BaseModel):
            raw_dict = vendor_data.model_dump()
        elif isinstance(vendor_data, dict):
            raw_dict = dict(vendor_data)
        else:
            raw_dict = {}

        normalized_data = copy.deepcopy(raw_dict)
        exec_context = dict(context or {})
        if vendor_id:
            exec_context["vendor_id"] = vendor_id

        # 2. Retrieve active rules in deterministic order
        active_rules = self.registry.get_active_rules(self.config)
        total_checks = len(active_rules)

        all_findings: List[ValidationFinding] = []
        passed_rules_count = 0

        # 3. Execute all active rules
        for rule in active_rules:
            try:
                findings = rule.validate(normalized_data, exec_context, self.config)
                if not findings:
                    passed_rules_count += 1
                else:
                    all_findings.extend(findings)
            except Exception as e:
                logger.error(
                    "Unexpected error during rule execution [%s]: %s",
                    rule.rule_id,
                    type(e).__name__,
                )
                # Failsafe finding to avoid silently dropping unhandled runtime rule bugs
                all_findings.append(
                    rule.create_finding(
                        field=rule.target_fields[0] if rule.target_fields else "general",
                        code="RULE_EXECUTION_ERROR",
                        message=f"Internal rule evaluation encountered an issue ({type(e).__name__}).",
                        suggestion="Contact technical support if this persistent issue recurs.",
                        config=self.config,
                    )
                )

        # 4. Sort findings deterministically (Severity -> Field -> Rule ID)
        sorted_findings = sorted(
            all_findings,
            key=lambda f: (
                SEVERITY_ORDER.get(f.severity, 99),
                f.field,
                f.rule_id,
                f.code,
            )
        )

        # 5. Compute summary metrics and overall status
        error_count = sum(1 for f in sorted_findings if f.severity == Severity.ERROR)
        warning_count = sum(1 for f in sorted_findings if f.severity == Severity.WARNING)
        info_count = sum(1 for f in sorted_findings if f.severity == Severity.INFO)

        if error_count > 0:
            overall_status = ValidationStatus.FAILED
            is_valid = False
        elif warning_count > 0:
            overall_status = ValidationStatus.PASSED_WITH_WARNINGS
            is_valid = True
        else:
            overall_status = ValidationStatus.PASSED
            is_valid = True

        summary = ValidationSummary(
            total_checks=total_checks,
            passed=passed_rules_count,
            failed=error_count,
            warnings=warning_count,
            info=info_count,
        )

        return ValidationResult(
            validation_id=str(uuid4()),
            vendor_id=vendor_id,
            status=overall_status,
            valid=is_valid,
            summary=summary,
            findings=sorted_findings,
            validated_at=datetime.now(timezone.utc),
            ruleset_version=self.config.ruleset_version,
        )


# Default engine instance
validation_engine = ValidationEngine()
