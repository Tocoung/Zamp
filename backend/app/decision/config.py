"""Configuration for the deterministic decision engine."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.decision.models import DecisionAction


# Default mapping from validation rule IDs to DecisionAction
# Every single rule in the validation registry (28 total) is explicitly mapped below.
DEFAULT_RULE_ACTIONS: Dict[str, DecisionAction] = {
    # 1. Mandatory required fields (19 rules):
    # Missing information is NOT conclusive proof of ineligibility or fraud.
    # Therefore, all missing required fields map to REVIEW -> produces PENDING.
    "COMPANY_LEGAL_NAME_REQUIRED": DecisionAction.REVIEW,
    "COMPANY_BUSINESS_TYPE_REQUIRED": DecisionAction.REVIEW,
    "COMPANY_INCORPORATION_COUNTRY_REQUIRED": DecisionAction.REVIEW,
    "COMPANY_REGISTRATION_NUMBER_REQUIRED": DecisionAction.REVIEW,
    "CONTACT_NAME_REQUIRED": DecisionAction.REVIEW,
    "CONTACT_EMAIL_REQUIRED": DecisionAction.REVIEW,
    "CONTACT_PHONE_REQUIRED": DecisionAction.REVIEW,
    "ADDRESS_LINE1_REQUIRED": DecisionAction.REVIEW,
    "ADDRESS_CITY_REQUIRED": DecisionAction.REVIEW,
    "ADDRESS_STATE_PROVINCE_REQUIRED": DecisionAction.REVIEW,
    "ADDRESS_POSTAL_CODE_REQUIRED": DecisionAction.REVIEW,
    "ADDRESS_COUNTRY_REQUIRED": DecisionAction.REVIEW,
    "TAX_ID_TYPE_REQUIRED": DecisionAction.REVIEW,
    "TAX_ID_NUMBER_REQUIRED": DecisionAction.REVIEW,
    "BANK_ACCOUNT_HOLDER_REQUIRED": DecisionAction.REVIEW,
    "BANK_NAME_REQUIRED": DecisionAction.REVIEW,
    "BANK_ACCOUNT_NUMBER_REQUIRED": DecisionAction.REVIEW,
    "BANK_ROUTING_NUMBER_REQUIRED": DecisionAction.REVIEW,
    "BANK_COUNTRY_REQUIRED": DecisionAction.REVIEW,

    # 2. Syntax, format, and structural validations (5 rules):
    # Violations of statutory syntax or invalid structural checks block onboarding -> REJECTED.
    "FMT_EMAIL_STRUCTURE": DecisionAction.BLOCK,
    "FMT_PHONE_INTERNATIONAL": DecisionAction.BLOCK,
    "FMT_TAX_ID_SYNTAX": DecisionAction.BLOCK,
    "FMT_BANK_ROUTING": DecisionAction.BLOCK,
    "FMT_BANK_ACCOUNT_STRUCTURAL": DecisionAction.BLOCK,

    # 3. Cross-field consistency rules (4 rules):
    # Discrepancies warrant human review (REVIEW -> PENDING), while cross-border operations are noted (IGNORE).
    "CONST_ACCOUNT_HOLDER_MATCH": DecisionAction.REVIEW,
    "CONST_TAX_TYPE_COUNTRY": DecisionAction.REVIEW,
    "CONST_ROUTING_BANK_COUNTRY": DecisionAction.REVIEW,
    "CONST_CROSS_BORDER_REGISTRATION": DecisionAction.IGNORE,
}

# Fine-grained mapping by specific finding code
DEFAULT_FINDING_CODE_ACTIONS: Dict[str, DecisionAction] = {
    # Incomplete submission / Missing required fields: REVIEW (PENDING)
    "REQUIRED_FIELD_MISSING": DecisionAction.REVIEW,
    "MISSING_LEGAL_NAME": DecisionAction.REVIEW,
    "MISSING_BUSINESS_TYPE": DecisionAction.REVIEW,
    "MISSING_COUNTRY_OF_INCORPORATION": DecisionAction.REVIEW,
    "MISSING_REGISTRATION_NUMBER": DecisionAction.REVIEW,
    "MISSING_CONTACT_NAME": DecisionAction.REVIEW,
    "MISSING_CONTACT_EMAIL": DecisionAction.REVIEW,
    "MISSING_CONTACT_PHONE": DecisionAction.REVIEW,
    "MISSING_ADDRESS_LINE1": DecisionAction.REVIEW,
    "MISSING_CITY": DecisionAction.REVIEW,
    "MISSING_STATE_PROVINCE": DecisionAction.REVIEW,
    "MISSING_POSTAL_CODE": DecisionAction.REVIEW,
    "MISSING_ADDRESS_COUNTRY": DecisionAction.REVIEW,
    "MISSING_TAX_ID_TYPE": DecisionAction.REVIEW,
    "MISSING_TAX_ID_NUMBER": DecisionAction.REVIEW,
    "MISSING_BANK_ACCOUNT_HOLDER_NAME": DecisionAction.REVIEW,
    "MISSING_BANK_NAME": DecisionAction.REVIEW,
    "MISSING_BANK_ACCOUNT_NUMBER": DecisionAction.REVIEW,
    "MISSING_BANK_ROUTING_NUMBER": DecisionAction.REVIEW,
    "MISSING_BANK_COUNTRY": DecisionAction.REVIEW,

    # Format blocking codes: BLOCK (REJECTED)
    "INVALID_EMAIL_FORMAT": DecisionAction.BLOCK,
    "INVALID_PHONE_STRUCTURE": DecisionAction.BLOCK,
    "INVALID_PHONE_DIGIT_COUNT": DecisionAction.BLOCK,
    "INVALID_GSTIN_FORMAT": DecisionAction.BLOCK,
    "INVALID_PAN_FORMAT": DecisionAction.BLOCK,
    "INVALID_EIN_FORMAT": DecisionAction.BLOCK,
    "INVALID_EIN_PREFIX": DecisionAction.BLOCK,
    "INVALID_UK_VAT_FORMAT": DecisionAction.BLOCK,
    "INVALID_IFSC_FORMAT": DecisionAction.BLOCK,
    "INVALID_ABA_FORMAT": DecisionAction.BLOCK,
    "INVALID_ABA_CHECKSUM": DecisionAction.BLOCK,
    "INVALID_SWIFT_BIC_FORMAT": DecisionAction.BLOCK,
    "INVALID_ACCOUNT_LENGTH": DecisionAction.BLOCK,
    "DUMMY_ACCOUNT_SEQUENCE": DecisionAction.BLOCK,
    "SEQUENTIAL_ACCOUNT_DUMMY": DecisionAction.BLOCK,

    # Warnings / Consistency review codes: REVIEW (PENDING)
    "ACCOUNT_HOLDER_NAME_MISMATCH": DecisionAction.REVIEW,
    "TAX_TYPE_COUNTRY_MISMATCH": DecisionAction.REVIEW,
    "ROUTING_BANK_COUNTRY_MISMATCH": DecisionAction.REVIEW,
    "UNUSUAL_ROUTING_LENGTH": DecisionAction.REVIEW,

    # Informational codes (non-blocking): IGNORE (APPROVED if no blockers)
    "CROSS_BORDER_OPERATIONS_NOTE": DecisionAction.IGNORE,
    "TAX_FORMAT_UNSUPPORTED_NOTE": DecisionAction.IGNORE,
}


class DecisionConfig(BaseModel):
    """Configuration options governing decision thresholds and action mappings."""

    decision_version: str = Field(
        default="1.0.0",
        description="Version string for decision logic, independently tracked from validation ruleset.",
    )

    # Action mappings
    rule_actions: Dict[str, DecisionAction] = Field(
        default_factory=lambda: dict(DEFAULT_RULE_ACTIONS)
    )
    finding_code_actions: Dict[str, DecisionAction] = Field(
        default_factory=lambda: dict(DEFAULT_FINDING_CODE_ACTIONS)
    )

    # Severity fallbacks when rule_id and finding_code are not explicitly mapped
    default_error_action: DecisionAction = Field(default=DecisionAction.BLOCK)
    default_warning_action: DecisionAction = Field(default=DecisionAction.REVIEW)
    default_info_action: DecisionAction = Field(default=DecisionAction.IGNORE)

    def resolve_action(
        self,
        rule_id: Optional[str],
        finding_code: Optional[str],
        severity: str,
    ) -> DecisionAction:
        """Deterministically resolves the DecisionAction for a given finding.
        
        Resolution Precedence:
        1. Explicit finding code override (highest priority)
        2. Explicit rule ID override
        3. Documented fallback based on severity level (ERROR -> BLOCK, WARNING -> REVIEW, INFO -> IGNORE)
        """
        if finding_code and finding_code in self.finding_code_actions:
            return self.finding_code_actions[finding_code]

        if rule_id and rule_id in self.rule_actions:
            return self.rule_actions[rule_id]

        sev_upper = (severity or "INFO").strip().upper()
        if sev_upper == "ERROR":
            return self.default_error_action
        elif sev_upper == "WARNING":
            return self.default_warning_action
        return self.default_info_action

    def verify_registry_coverage(self, registry: Any) -> Dict[str, Any]:
        """Validates that every rule in the rule registry has an explicit mapping or documented fallback.
        
        Returns a coverage audit dictionary.
        """
        all_rules = registry.list_all_rules()
        explicitly_mapped = []
        fallback_covered = []

        for rule in all_rules:
            if rule.rule_id in self.rule_actions:
                explicitly_mapped.append({
                    "rule_id": rule.rule_id,
                    "action": self.rule_actions[rule.rule_id].value,
                    "category": getattr(rule, "category", "general"),
                })
            else:
                action = self.resolve_action(
                    rule.rule_id, None, rule.default_severity.value
                )
                fallback_covered.append({
                    "rule_id": rule.rule_id,
                    "action": action.value,
                    "severity": rule.default_severity.value,
                    "category": getattr(rule, "category", "general"),
                })

        return {
            "total_registered_rules": len(all_rules),
            "explicitly_mapped_count": len(explicitly_mapped),
            "fallback_covered_count": len(fallback_covered),
            "explicitly_mapped": explicitly_mapped,
            "fallback_covered": fallback_covered,
            "is_fully_covered": (len(explicitly_mapped) + len(fallback_covered)) == len(all_rules),
        }
