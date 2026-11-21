"""Decision rules, reason mappings, and recommendation generators."""

from typing import Optional
from app.decision.models import (
    DecisionAction,
    DecisionReason,
    DecisionRecommendation,
)
from app.validation.models import ValidationFinding


# Title mappings for known validation codes
REASON_TITLES = {
    "REQUIRED_FIELD_MISSING": "Missing Mandatory Submission Field",
    "INVALID_EMAIL_FORMAT": "Invalid Contact Email Syntax",
    "INVALID_PHONE_STRUCTURE": "Invalid Contact Phone Format",
    "INVALID_PHONE_DIGIT_COUNT": "Contact Phone Digit Length Mismatch",
    "INVALID_GSTIN_FORMAT": "Statutory GSTIN Format Invalid",
    "INVALID_PAN_FORMAT": "Statutory PAN Format Invalid",
    "INVALID_EIN_FORMAT": "Statutory US EIN Format Invalid",
    "INVALID_EIN_PREFIX": "Non-Standard US EIN Prefix",
    "INVALID_UK_VAT_FORMAT": "Statutory UK VAT Format Invalid",
    "INVALID_IFSC_FORMAT": "Invalid Indian IFSC Code Format",
    "INVALID_ABA_FORMAT": "Invalid US ABA Routing Transit Format",
    "INVALID_ABA_CHECKSUM": "US ABA Routing Transit Checksum Failed",
    "INVALID_SWIFT_BIC_FORMAT": "Invalid International SWIFT/BIC Format",
    "INVALID_ACCOUNT_LENGTH": "Bank Account Structural Length Invalid",
    "DUMMY_ACCOUNT_SEQUENCE": "Placeholder Bank Account Number Detected",
    "SEQUENTIAL_ACCOUNT_DUMMY": "Sequential Placeholder Bank Account Detected",
    "ACCOUNT_HOLDER_NAME_MISMATCH": "Bank Account Holder Name Requires Review",
    "TAX_TYPE_COUNTRY_MISMATCH": "Tax Scheme and Country Alignment Review",
    "ROUTING_BANK_COUNTRY_MISMATCH": "Bank Routing Scheme Alignment Review",
    "UNUSUAL_ROUTING_LENGTH": "Unusual Bank Routing Identifier Length",
    "CROSS_BORDER_OPERATIONS_NOTE": "Cross-Border Corporate Structure Noted",
    "TAX_FORMAT_UNSUPPORTED_NOTE": "Non-Standard Tax Scheme Registered",
}


def map_finding_to_decision_reason(
    finding: ValidationFinding,
    action: DecisionAction,
) -> DecisionReason:
    """Constructs an explainable, sanitized DecisionReason from a ValidationFinding.
    
    CRITICAL SECURITY & PRIVACY CONTROLS:
    - Never reflects plaintext or encrypted bank account numbers.
    - Never reflects raw tax numbers, passwords, or full phone numbers.
    - Sanitizes comparisons (e.g. Account holder name mismatch never echoes raw submitted entity names).
    """
    is_missing = (
        finding.code == "REQUIRED_FIELD_MISSING"
        or (finding.rule_id and finding.rule_id.endswith("_REQUIRED"))
    )

    if is_missing:
        code = f"MISSING_{finding.field.upper()}"
        field_label = finding.field.replace("_", " ").title()
        title = f"Missing Required Field: {field_label}"
        explanation = f"Mandatory field '{finding.field}' is missing or blank. Vendor submission is incomplete."
    else:
        code = finding.code or f"REASON_{finding.rule_id}"
        title = REASON_TITLES.get(code, f"Validation Check: {finding.field}")

        # Objective, sanitized explanations that avoid echoing arbitrary user inputs
        if code == "ACCOUNT_HOLDER_NAME_MISMATCH":
            explanation = (
                "The bank account holder name does not sufficiently match the registered company or trade name."
            )
        elif code in ("DUMMY_ACCOUNT_SEQUENCE", "SEQUENTIAL_ACCOUNT_DUMMY"):
            explanation = (
                "Bank account number appears to be an invalid placeholder sequence. "
                "A genuine active commercial account number is required."
            )
        elif code == "INVALID_ACCOUNT_LENGTH":
            explanation = (
                "Bank account number length does not meet standard domestic or international specifications."
            )
        elif code == "INVALID_EIN_PREFIX":
            explanation = (
                "US EIN prefix is not recognized as an active IRS issuing campus prefix."
            )
        elif code == "INVALID_PHONE_STRUCTURE":
            explanation = "Contact phone number contains invalid formatting characters."
        elif code == "INVALID_PHONE_DIGIT_COUNT":
            explanation = "Contact phone number digit count is outside standard international range (7-17 digits)."
        else:
            explanation = finding.message

    return DecisionReason(
        code=code,
        title=title,
        explanation=explanation,
        source_rule_id=finding.rule_id,
        source_finding_code=finding.code,
        severity=finding.severity,
    )


def map_finding_to_recommendation(
    finding: ValidationFinding,
    action: DecisionAction,
) -> Optional[DecisionRecommendation]:
    """Generates an actionable recommendation corresponding to a ValidationFinding.
    
    CRITICAL: Never reveals, repeats, or hints at raw banking numbers or sensitive user inputs.
    """
    is_missing = (
        finding.code == "REQUIRED_FIELD_MISSING"
        or (finding.rule_id and finding.rule_id.endswith("_REQUIRED"))
    )

    # Priority derived from decision action
    priority = (
        "HIGH"
        if action == DecisionAction.BLOCK
        else ("MEDIUM" if action == DecisionAction.REVIEW else "LOW")
    )

    if is_missing:
        return DecisionRecommendation(
            action=f"PROVIDE_{finding.field.upper()}",
            description=f"Provide a valid value for mandatory field '{finding.field}' to complete submission.",
            priority=priority,
        )

    code = finding.code or ""

    if code == "INVALID_EMAIL_FORMAT":
        return DecisionRecommendation(
            action="CORRECT_CONTACT_EMAIL",
            description="Obtain and enter an active, deliverable corporate email address conforming to standard RFC format.",
            priority=priority,
        )

    if code in ("INVALID_PHONE_STRUCTURE", "INVALID_PHONE_DIGIT_COUNT"):
        return DecisionRecommendation(
            action="CORRECT_CONTACT_PHONE",
            description="Enter a standard telephone number including international dialing prefix (+country code).",
            priority=priority,
        )

    if code in (
        "INVALID_GSTIN_FORMAT",
        "INVALID_PAN_FORMAT",
        "INVALID_EIN_FORMAT",
        "INVALID_EIN_PREFIX",
        "INVALID_UK_VAT_FORMAT",
    ):
        return DecisionRecommendation(
            action="VERIFY_TAX_REGISTRATION",
            description="Request a verified copy of the vendor's official tax certificate and correct the statutory tax identifier.",
            priority=priority,
        )

    if code in (
        "INVALID_IFSC_FORMAT",
        "INVALID_ABA_FORMAT",
        "INVALID_ABA_CHECKSUM",
        "INVALID_SWIFT_BIC_FORMAT",
    ):
        return DecisionRecommendation(
            action="CORRECT_ROUTING_IDENTIFIER",
            description="Verify the routing number against official bank documentation (e.g., voided cheque, deposit ticket, or wire instructions).",
            priority=priority,
        )

    if code in (
        "INVALID_ACCOUNT_LENGTH",
        "DUMMY_ACCOUNT_SEQUENCE",
        "SEQUENTIAL_ACCOUNT_DUMMY",
    ):
        return DecisionRecommendation(
            action="PROVIDE_GENUINE_ACCOUNT_NUMBER",
            description="Provide the legitimate, active commercial bank account number issued by the financial institution.",
            priority=priority,
        )

    if code == "ACCOUNT_HOLDER_NAME_MISMATCH":
        return DecisionRecommendation(
            action="VERIFY_ACCOUNT_HOLDER",
            description="Confirm the bank account belongs to the submitted legal entity, or request documentation explaining the DBA or parent company relationship.",
            priority=priority,
        )

    if code in ("TAX_TYPE_COUNTRY_MISMATCH", "ROUTING_BANK_COUNTRY_MISMATCH"):
        return DecisionRecommendation(
            action="CLARIFY_JURISDICTION_DETAILS",
            description="Confirm clearing method and statutory tax scheme for the vendor's registered jurisdiction.",
            priority=priority,
        )

    # General fallback for any remaining findings
    if finding.suggestion and action != DecisionAction.IGNORE:
        return DecisionRecommendation(
            action=f"REVIEW_{finding.field.upper()}",
            description=finding.suggestion,
            priority=priority,
        )

    return None
