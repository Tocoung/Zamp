"""Validation rule registry managing rule lifecycle and configuration."""

from typing import Dict, List, Optional
from app.validation.config import ValidationConfig
from app.validation.rules.base import ValidationRule
from app.validation.rules.required import get_required_field_rules
from app.validation.rules.formats import get_format_rules
from app.validation.rules.consistency import get_consistency_rules

CATEGORY_EXECUTION_ORDER = {
    "required": 1,
    "format": 2,
    "consistency": 3,
    "general": 4,
}


class RuleRegistry:
    """Registry maintaining active validation rules and deterministic ordering."""

    def __init__(self):
        self._rules: Dict[str, ValidationRule] = {}

    def register_rule(self, rule: ValidationRule) -> None:
        """Registers a validation rule into the registry."""
        self._rules[rule.rule_id] = rule

    def get_rule(self, rule_id: str) -> Optional[ValidationRule]:
        """Retrieves a rule by its unique identifier."""
        return self._rules.get(rule_id)

    def list_all_rules(self) -> List[ValidationRule]:
        """Returns all registered rules sorted deterministically."""
        return sorted(
            self._rules.values(),
            key=lambda r: (CATEGORY_EXECUTION_ORDER.get(r.category, 99), r.rule_id)
        )

    def get_active_rules(self, config: ValidationConfig) -> List[ValidationRule]:
        """Returns enabled rules sorted deterministically by category and rule_id."""
        active = [
            rule for rule in self._rules.values()
            if config.is_rule_enabled(rule.rule_id)
        ]
        return sorted(
            active,
            key=lambda r: (CATEGORY_EXECUTION_ORDER.get(r.category, 99), r.rule_id)
        )


def create_default_registry() -> RuleRegistry:
    """Factory creating and populating the standard Phase 1 Step 3 rule registry."""
    registry = RuleRegistry()

    # 1. Register required-field rules
    for rule in get_required_field_rules():
        registry.register_rule(rule)

    # 2. Register format rules
    for rule in get_format_rules():
        registry.register_rule(rule)

    # 3. Register consistency rules
    for rule in get_consistency_rules():
        registry.register_rule(rule)

    return registry


# Singleton default registry
default_registry = create_default_registry()
