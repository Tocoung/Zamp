"""Configuration for the deterministic decision engine."""

from typing import Dict, Optional
from pydantic import BaseModel, Field
from app.decision.models import DecisionAction


# Default mapping from validation rule IDs to DecisionAction
DEFAULT_RULE_ACTIONS: Dict[str, DecisionAction] = {
    # Syntax and format validations: blocking errors
    "FMT_EMAIL_STRUCTURE": DecisionAction.BLOCK,
    "FMT_PHONE_E164": DecisionAction.BLOCK,
    "FMT_TAX_ID_SYNTAX": DecisionAction.BLOCK,
    "FMT_BANK_ROUTING": DecisionAction.BLOCK,
    "FMT_BANK_ACCOUNT_STRUCTURAL": DecisionAction.BLOCK,

    # Mandatory fields: review/clarification by default (incomplete submission)
    "REQ_LEGAL_NAME": DecisionAction.BLOCK,
    "REQ_REGISTRATION_NUMBER": DecisionAction.BLOCK,
    "REQ_COUNTRY_OF_INCORPORATION": DecisionAction.BLOCK,
    "REQ_TAX_ID_NUMBER": DecisionAction.BLOCK,
    "REQ_BANK_ACCOUNT_NUMBER": DecisionAction.BLOCK,
    "REQ_BANK_ROUTING_NUMBER": DecisionAction.BLOCK,

    # Cross-field consistency rules: review items (not outright rejection)
    "CONST_ACCOUNT_HOLDER_MATCH": DecisionAction.REVIEW,
    "CONST_TAX_TYPE_COUNTRY": DecisionAction.REVIEW,
    "CONST_ROUTING_BANK_COUNTRY": DecisionAction.REVIEW,

    # Informational rules: do not impede approval
    "CONST_CROSS_BORDER_REGISTRATION": DecisionAction.IGNORE,
}

# Fine-grained mapping by specific finding code
DEFAULT_FINDING_CODE_ACTIONS: Dict[str, DecisionAction] = {
    # Format blocking codes
    "INVALID_EMAIL_FORMAT": DecisionAction.BLOCK,
    "INVALID_PHONE_FORMAT": DecisionAction.BLOCK,
    "INVALID_GSTIN_FORMAT": DecisionAction.BLOCK,
    "INVALID_PAN_FORMAT": DecisionAction.BLOCK,
    "INVALID_EIN_FORMAT": DecisionAction.BLOCK,
    "INVALID_VAT_FORMAT": DecisionAction.BLOCK,
    "INVALID_IFSC_FORMAT": DecisionAction.BLOCK,
    "INVALID_ABA_FORMAT": DecisionAction.BLOCK,
    "INVALID_ABA_CHECKSUM": DecisionAction.BLOCK,
    "INVALID_SWIFT_BIC_FORMAT": DecisionAction.BLOCK,
    "INVALID_ACCOUNT_LENGTH": DecisionAction.BLOCK,
    "DUMMY_ACCOUNT_SEQUENCE": DecisionAction.BLOCK,
    "SEQUENTIAL_ACCOUNT_DUMMY": DecisionAction.BLOCK,

    # Warnings / Consistency review codes
    "ACCOUNT_HOLDER_NAME_MISMATCH": DecisionAction.REVIEW,
    "TAX_TYPE_COUNTRY_MISMATCH": DecisionAction.REVIEW,
    "ROUTING_BANK_COUNTRY_MISMATCH": DecisionAction.REVIEW,
    "UNUSUAL_ROUTING_LENGTH": DecisionAction.REVIEW,

    # Informational codes (non-blocking)
    "CROSS_BORDER_OPERATIONS_NOTE": DecisionAction.IGNORE,
    "UNSUPPORTED_TAX_TYPE": DecisionAction.IGNORE,
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
        
        Resolution precedence:
        1. Explicit finding code override
        2. Explicit rule ID override
        3. Fallback based on severity level
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
