"""Base rule interface and abstract classes for the Validation Engine."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from app.validation.models import Severity, FindingStatus, ValidationFinding
from app.validation.config import ValidationConfig


class ValidationRule(ABC):
    """Abstract base class representing an independent, deterministic validation rule."""

    def __init__(
        self,
        rule_id: str,
        name: str,
        description: str,
        default_severity: Severity,
        target_fields: List[str],
        category: str = "general",
    ):
        self.rule_id = rule_id
        self.name = name
        self.description = description
        self.default_severity = default_severity
        self.target_fields = target_fields
        self.category = category

    def create_finding(
        self,
        field: str,
        code: str,
        message: str,
        suggestion: Optional[str] = None,
        severity: Optional[Severity] = None,
        config: Optional[ValidationConfig] = None,
    ) -> ValidationFinding:
        """Helper to construct a structured ValidationFinding respecting configuration overrides."""
        effective_severity = severity
        if effective_severity is None and config is not None:
            effective_severity = config.get_effective_severity(self.rule_id, self.default_severity)
        elif effective_severity is None:
            effective_severity = self.default_severity

        return ValidationFinding(
            rule_id=self.rule_id,
            field=field,
            severity=effective_severity,
            status=FindingStatus.FAILED,
            code=code,
            message=message,
            suggestion=suggestion,
        )

    @abstractmethod
    def validate(
        self,
        data: Dict[str, Any],
        context: Dict[str, Any],
        config: ValidationConfig,
    ) -> List[ValidationFinding]:
        """Executes the validation rule against normalized vendor dictionary.
        
        Args:
            data: Normalized vendor dictionary containing submitted or stored fields.
            context: Additional runtime context (e.g. is_stored_record, vendor_id).
            config: Active ValidationConfig governing execution.
            
        Returns:
            List of ValidationFinding objects. Empty list indicates rule passed.
        """
        pass
