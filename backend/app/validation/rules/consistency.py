"""Cross-field consistency validation rules."""

import re
from typing import Any, Dict, List, Set
from app.validation.models import Severity, ValidationFinding
from app.validation.config import ValidationConfig
from app.validation.rules.base import ValidationRule

COMMON_CORP_SUFFIXES: Set[str] = {
    "inc", "incorporated", "corp", "corporation", "llc", "ltd", "limited",
    "pvt", "private", "co", "company", "gmbh", "sa", "sarl", "bv", "nv", "plc"
}


def tokenize_name(name: str) -> Set[str]:
    """Normalizes and extracts significant tokens from a business entity name."""
    cleaned = re.sub(r"[^\w\s]", " ", name.lower())
    tokens = {t.strip() for t in cleaned.split() if len(t.strip()) > 1}
    # Filter out corporate structure noise words unless that's all there is
    significant = {t for t in tokens if t not in COMMON_CORP_SUFFIXES}
    return significant if significant else tokens


class TaxCountryCompatibilityRule(ValidationRule):
    """Checks whether tax identifier type aligns with the company's incorporation jurisdiction."""

    def __init__(self):
        super().__init__(
            rule_id="CONST_TAX_TYPE_COUNTRY",
            name="Tax Type and Country Consistency",
            description="Verifies that statutory tax schemes align with the claimed jurisdiction of incorporation.",
            default_severity=Severity.WARNING,
            target_fields=["tax_id_type", "country_of_incorporation"],
            category="consistency",
        )

    def validate(self, data: Dict[str, Any], context: Dict[str, Any], config: ValidationConfig) -> List[ValidationFinding]:
        tax_type = str(data.get("tax_id_type") or "").strip().upper()
        country = str(data.get("country_of_incorporation") or "").strip().lower()

        if not tax_type or not country:
            return []

        # GSTIN or PAN outside India
        if tax_type in ("GSTIN", "PAN") and "india" not in country:
            return [
                self.create_finding(
                    field="tax_id_type",
                    code="TAX_TYPE_COUNTRY_MISMATCH",
                    message=f"Tax identifier type '{tax_type}' is standard for India, but country of incorporation is '{data.get('country_of_incorporation')}'.",
                    suggestion="Confirm whether the foreign entity is registered under Indian tax authority or update tax ID type.",
                    config=config,
                )
            ]

        # EIN outside United States
        if tax_type in ("EIN", "FEIN") and "united states" not in country:
            return [
                self.create_finding(
                    field="tax_id_type",
                    code="TAX_TYPE_COUNTRY_MISMATCH",
                    message=f"Tax identifier type 'EIN' is standard for the United States, but country of incorporation is '{data.get('country_of_incorporation')}'.",
                    suggestion="Verify if the vendor has a US EIN for foreign business operations or update tax ID type.",
                    config=config,
                )
            ]

        # VAT claimed for US corporation
        if tax_type == "VAT" and "united states" in country:
            return [
                self.create_finding(
                    field="tax_id_type",
                    code="TAX_TYPE_COUNTRY_MISMATCH",
                    message="The United States does not assess national VAT. US entities typically report an EIN.",
                    suggestion="Select 'EIN' or state tax identifier for US domestic entities unless reporting foreign VAT.",
                    config=config,
                )
            ]

        return []


class RoutingBankCountryCompatibilityRule(ValidationRule):
    """Checks whether the banking routing scheme aligns with the bank's country of domicile."""

    def __init__(self):
        super().__init__(
            rule_id="CONST_ROUTING_BANK_COUNTRY",
            name="Routing Scheme and Bank Country Consistency",
            description="Checks whether domestic clearing codes (IFSC, ABA) match the bank domicile country.",
            default_severity=Severity.WARNING,
            target_fields=["bank_routing_number", "bank_country"],
            category="consistency",
        )

    def validate(self, data: Dict[str, Any], context: Dict[str, Any], config: ValidationConfig) -> List[ValidationFinding]:
        routing = str(data.get("bank_routing_number") or "").strip().upper().replace(" ", "").replace("-", "")
        country = str(data.get("bank_country") or "").strip().lower()

        if not routing or not country:
            return []

        # Looks like Indian IFSC, but bank is not India
        if len(routing) == 11 and routing[:4].isalpha() and routing[4] == "0" and "india" not in country:
            return [
                self.create_finding(
                    field="bank_routing_number",
                    code="ROUTING_BANK_COUNTRY_MISMATCH",
                    message=f"Routing code format matches Indian IFSC, but bank country is '{data.get('bank_country')}'.",
                    suggestion="Confirm the bank country or provide the international SWIFT/BIC code for cross-border wires.",
                    config=config,
                )
            ]

        # Looks like US ABA 9-digit, but bank country is not United States
        if routing.isdigit() and len(routing) == 9 and "united states" not in country:
            return [
                self.create_finding(
                    field="bank_routing_number",
                    code="ROUTING_BANK_COUNTRY_MISMATCH",
                    message=f"9-digit numeric routing code matches US ABA format, but bank country is '{data.get('bank_country')}'.",
                    suggestion="Ensure routing code matches the local national clearing system or provide SWIFT/BIC.",
                    config=config,
                )
            ]

        return []


class CrossBorderRegistrationRule(ValidationRule):
    """Informational rule noting multinational / cross-border operational setup."""

    def __init__(self):
        super().__init__(
            rule_id="CONST_CROSS_BORDER_REGISTRATION",
            name="Cross-Border Registration Check",
            description="Identifies vendors with registered office addresses in a different country from incorporation.",
            default_severity=Severity.INFO,
            target_fields=["country_of_incorporation", "address_country"],
            category="consistency",
        )

    def validate(self, data: Dict[str, Any], context: Dict[str, Any], config: ValidationConfig) -> List[ValidationFinding]:
        inc_country = str(data.get("country_of_incorporation") or "").strip()
        addr_country = str(data.get("address_country") or "").strip()

        if not inc_country or not addr_country:
            return []

        if inc_country.lower() != addr_country.lower():
            return [
                self.create_finding(
                    field="address_country",
                    code="CROSS_BORDER_OPERATIONS_NOTE",
                    severity=Severity.INFO,
                    message=f"Cross-border operations: Incorporated in '{inc_country}', but registered operating address is in '{addr_country}'.",
                    suggestion="Ensure foreign authorization documents or local branch registration certificates are prepared for compliance.",
                    config=config,
                )
            ]

        return []


class AccountHolderLegalNameMatchRule(ValidationRule):
    """Compares bank account holder name against legal entity and trade names."""

    def __init__(self):
        super().__init__(
            rule_id="CONST_ACCOUNT_HOLDER_MATCH",
            name="Account Holder and Legal Name Consistency",
            description="Verifies that bank account holder name shares identity with legal company name or DBA.",
            default_severity=Severity.WARNING,
            target_fields=["bank_account_holder_name", "legal_name", "trade_name"],
            category="consistency",
        )

    def validate(self, data: Dict[str, Any], context: Dict[str, Any], config: ValidationConfig) -> List[ValidationFinding]:
        holder = str(data.get("bank_account_holder_name") or "").strip()
        legal = str(data.get("legal_name") or "").strip()
        trade = str(data.get("trade_name") or "").strip()

        if not holder or not legal:
            return []

        # 1. Exact or Substring match
        holder_lower = holder.lower()
        legal_lower = legal.lower()
        trade_lower = trade.lower() if trade else ""

        if holder_lower in legal_lower or legal_lower in holder_lower:
            return []
        if trade_lower and (holder_lower in trade_lower or trade_lower in holder_lower):
            return []

        # 2. Token overlap analysis
        holder_tokens = tokenize_name(holder)
        legal_tokens = tokenize_name(legal)
        trade_tokens = tokenize_name(trade) if trade else set()

        if holder_tokens.intersection(legal_tokens):
            return []
        if trade_tokens and holder_tokens.intersection(trade_tokens):
            return []

        # Discrepancy detected -> emit WARNING
        return [
            self.create_finding(
                field="bank_account_holder_name",
                code="ACCOUNT_HOLDER_NAME_MISMATCH",
                message=f"Bank account holder name ('{holder}') does not appear to match legal company name ('{legal}')" + (f" or trade name ('{trade}')." if trade else "."),
                suggestion="If using a parent entity, subsidiary, or DBA, ensure a supporting authorization letter is submitted during document review.",
                config=config,
            )
        ]


def get_consistency_rules() -> List[ValidationRule]:
    """Instantiates and returns all cross-field consistency rules."""
    return [
        TaxCountryCompatibilityRule(),
        RoutingBankCountryCompatibilityRule(),
        CrossBorderRegistrationRule(),
        AccountHolderLegalNameMatchRule(),
    ]
