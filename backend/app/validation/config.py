"""Validation configuration definitions."""

from typing import Dict, Optional, Set
from pydantic import BaseModel, Field
from app.validation.models import Severity

RULESET_VERSION = "1.0.0"


class ValidationConfig(BaseModel):
    """Configuration governing validation engine execution and rule parameters."""
    ruleset_version: str = Field(default=RULESET_VERSION, description="Active validation ruleset semantic version.")
    disabled_rules: Set[str] = Field(default_factory=set, description="Set of rule IDs disabled from execution.")
    severity_overrides: Dict[str, Severity] = Field(
        default_factory=dict,
        description="Optional mapping of rule_id to overridden Severity level."
    )
    allow_cross_border_banking: bool = Field(
        default=True,
        description="Whether cross-border banking generates informational warnings rather than errors."
    )

    def is_rule_enabled(self, rule_id: str) -> bool:
        """Returns True if the given rule ID is not disabled."""
        return rule_id not in self.disabled_rules

    def get_effective_severity(self, rule_id: str, default_severity: Severity) -> Severity:
        """Returns the configured severity override for a rule, or its default severity."""
        return self.severity_overrides.get(rule_id, default_severity)
