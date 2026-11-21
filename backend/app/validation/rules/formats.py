"""Format validation rules for contact, tax, and banking fields."""

import re
from typing import Any, Dict, List, Optional
from app.validation.models import Severity, ValidationFinding
from app.validation.config import ValidationConfig
from app.validation.rules.base import ValidationRule

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")
PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$")
EIN_REGEX = re.compile(r"^([0-9]{2})-?([0-9]{7})$")
UK_VAT_REGEX = re.compile(r"^(?:GB)?\s*([0-9]{9}|[0-9]{12})$", re.IGNORECASE)
IFSC_REGEX = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
SWIFT_REGEX = re.compile(r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?$")

# Invalid IRS EIN 2-digit issuing campus prefixes
INVALID_EIN_PREFIXES = {"00", "07", "08", "09", "17", "18", "19", "28", "29", "49", "78", "79", "89"}


class EmailFormatRule(ValidationRule):
    """Validates corporate contact email address format."""

    def __init__(self):
        super().__init__(
            rule_id="FMT_EMAIL_STRUCTURE",
            name="Email Format Validation",
            description="Validates standard RFC-compliant corporate email syntax.",
            default_severity=Severity.ERROR,
            target_fields=["contact_email"],
            category="format",
        )

    def validate(self, data: Dict[str, Any], context: Dict[str, Any], config: ValidationConfig) -> List[ValidationFinding]:
        email = data.get("contact_email")
        if not email or not isinstance(email, str) or not email.strip():
            return []  # Defer to required check

        clean_email = email.strip()
        if not EMAIL_REGEX.match(clean_email) or clean_email.endswith("."):
            return [
                self.create_finding(
                    field="contact_email",
                    code="INVALID_EMAIL_FORMAT",
                    message="Contact email does not follow standard RFC email structure.",
                    suggestion="Enter a valid corporate email address (e.g., user@company.com).",
                    config=config,
                )
            ]
        return []


class PhoneFormatRule(ValidationRule):
    """Validates international phone number structure."""

    def __init__(self):
        super().__init__(
            rule_id="FMT_PHONE_INTERNATIONAL",
            name="International Phone Structure",
            description="Validates structural format of telephone numbers (7-17 digits with standard separators).",
            default_severity=Severity.ERROR,
            target_fields=["contact_phone"],
            category="format",
        )

    def validate(self, data: Dict[str, Any], context: Dict[str, Any], config: ValidationConfig) -> List[ValidationFinding]:
        phone = data.get("contact_phone")
        if not phone or not isinstance(phone, str) or not phone.strip():
            return []  # Defer to required check

        clean_phone = phone.strip()
        # Structural check: must contain only digits, +, -, (, ), ., and spaces
        if not re.match(r"^[\+]?[0-9\s\-\(\)\.]+$", clean_phone):
            return [
                self.create_finding(
                    field="contact_phone",
                    code="INVALID_PHONE_STRUCTURE",
                    message="Phone number contains invalid characters.",
                    suggestion="Use numeric digits with optional '+' prefix and standard separators (-, space, parentheses).",
                    config=config,
                )
            ]

        # Extract only numeric digits
        digits = re.sub(r"[^0-9]", "", clean_phone)
        if len(digits) < 7 or len(digits) > 17:
            return [
                self.create_finding(
                    field="contact_phone",
                    code="INVALID_PHONE_DIGIT_COUNT",
                    message=f"Phone number contains {len(digits)} digits. Standard international range is 7 to 17 digits.",
                    suggestion="Provide an active phone number including country dialing prefix (structural check only; number reachability is not queried).",
                    config=config,
                )
            ]

        return []


class TaxIdFormatRule(ValidationRule):
    """Country-aware, type-aware tax identification number format rule."""

    def __init__(self):
        super().__init__(
            rule_id="FMT_TAX_ID_SYNTAX",
            name="Tax Identifier Syntax Validation",
            description="Validates tax identifier structure based on country and tax identification type.",
            default_severity=Severity.ERROR,
            target_fields=["tax_id_type", "tax_id_number", "country_of_incorporation"],
            category="format",
        )

    def validate(self, data: Dict[str, Any], context: Dict[str, Any], config: ValidationConfig) -> List[ValidationFinding]:
        tax_type = str(data.get("tax_id_type") or "").strip().upper()
        tax_num = str(data.get("tax_id_number") or "").strip()
        country = str(data.get("country_of_incorporation") or "").strip().lower()

        if not tax_num or not tax_type:
            return []  # Defer to required field checks

        clean_tax_num = tax_num.replace(" ", "")

        # 1. India GSTIN
        if tax_type in ("GSTIN", "GST") or ("india" in country and tax_type in ("GSTIN", "GST")):
            if not GSTIN_REGEX.match(clean_tax_num):
                return [
                    self.create_finding(
                        field="tax_id_number",
                        code="INVALID_GSTIN_FORMAT",
                        message="GSTIN format is invalid. Expected 15-character statutory format (e.g., 29ABCDE1234F1Z5).",
                        suggestion="Verify 2-digit state code, 10-character PAN, entity number, 'Z' identifier, and checksum.",
                        config=config,
                    )
                ]
            return []

        # 2. India PAN
        if tax_type == "PAN" or ("india" in country and tax_type == "PAN"):
            if not PAN_REGEX.match(clean_tax_num):
                return [
                    self.create_finding(
                        field="tax_id_number",
                        code="INVALID_PAN_FORMAT",
                        message="Permanent Account Number (PAN) format is invalid. Expected 10 alphanumeric characters (e.g., ABCDE1234F).",
                        suggestion="Verify the PAN format: 5 uppercase letters, 4 numeric digits, 1 uppercase letter.",
                        config=config,
                    )
                ]
            return []

        # 3. United States EIN
        if tax_type in ("EIN", "FEIN") or ("united states" in country and tax_type in ("EIN", "FEIN", "TAX ID")):
            ein_match = EIN_REGEX.match(clean_tax_num)
            if not ein_match:
                return [
                    self.create_finding(
                        field="tax_id_number",
                        code="INVALID_EIN_FORMAT",
                        message="US Employer Identification Number (EIN) format is invalid. Expected 9 numeric digits (e.g., 12-3456789).",
                        suggestion="Provide a 9-digit numeric EIN in standard XX-XXXXXXX format.",
                        config=config,
                    )
                ]

            prefix = ein_match.group(1)
            if prefix in INVALID_EIN_PREFIXES:
                return [
                    self.create_finding(
                        field="tax_id_number",
                        code="INVALID_EIN_PREFIX",
                        message=f"US EIN prefix '{prefix}' is not an active IRS issuing campus prefix.",
                        suggestion="Verify the first two digits against your official IRS SS-4 confirmation letter.",
                        config=config,
                    )
                ]
            return []

        # 4. United Kingdom VAT
        if tax_type == "VAT" and ("united kingdom" in country or "uk" in country or "britain" in country or clean_tax_num.upper().startswith("GB")):
            vat_match = UK_VAT_REGEX.match(clean_tax_num)
            if not vat_match:
                return [
                    self.create_finding(
                        field="tax_id_number",
                        code="INVALID_UK_VAT_FORMAT",
                        message="UK VAT registration number format is invalid. Expected 9 or 12 numeric digits (optional 'GB' prefix).",
                        suggestion="Provide a valid 9-digit standard or 12-digit branch UK VAT number (syntax check only; HMRC VIES is not queried).",
                        config=config,
                    )
                ]
            return []

        # 5. Unsupported Tax Regime (Informational Note)
        return [
            self.create_finding(
                field="tax_id_number",
                code="TAX_FORMAT_UNSUPPORTED_NOTE",
                severity=Severity.INFO,
                message=f"Tax identifier format validation is not currently available for type '{tax_type}' in '{data.get('country_of_incorporation')}'. Only presence was verified.",
                suggestion="Ensure the tax identifier matches official statutory documents issued by the governing tax authority.",
                config=config,
            )
        ]


def validate_aba_checksum(routing_digits: str) -> bool:
    """Computes Federal Reserve Mod-10 checksum on 9-digit US ABA routing number.
    
    Formula: (3*(d1+d4+d7) + 7*(d2+d5+d8) + 1*(d3+d6+d9)) % 10 == 0
    """
    if len(routing_digits) != 9 or not routing_digits.isdigit():
        return False
    d = [int(ch) for ch in routing_digits]
    weighted_sum = (
        3 * (d[0] + d[3] + d[6]) +
        7 * (d[1] + d[4] + d[7]) +
        1 * (d[2] + d[5] + d[8])
    )
    return weighted_sum % 10 == 0


class BankRoutingFormatRule(ValidationRule):
    """Country-aware bank routing identifier format and checksum validation."""

    def __init__(self):
        super().__init__(
            rule_id="FMT_BANK_ROUTING",
            name="Bank Routing Identifier Validation",
            description="Validates banking routing codes (India IFSC, US ABA with Mod-10 checksum, SWIFT/BIC).",
            default_severity=Severity.ERROR,
            target_fields=["bank_routing_number", "bank_country"],
            category="format",
        )

    def validate(self, data: Dict[str, Any], context: Dict[str, Any], config: ValidationConfig) -> List[ValidationFinding]:
        routing = str(data.get("bank_routing_number") or "").strip().upper()
        country = str(data.get("bank_country") or "").strip().lower()

        if not routing:
            return []  # Defer to required check

        clean_routing = routing.replace(" ", "").replace("-", "")

        # 1. SWIFT / BIC Code (8 or 11 characters starting with alpha bank & country codes)
        if len(clean_routing) in (8, 11) and clean_routing[:6].isalpha():
            if not SWIFT_REGEX.match(clean_routing):
                return [
                    self.create_finding(
                        field="bank_routing_number",
                        code="INVALID_SWIFT_BIC_FORMAT",
                        message="SWIFT/BIC format is invalid. Expected 8 or 11 characters (4 letters bank, 2 letters country, 2 alphanumeric location, optional 3 alphanumeric branch).",
                        suggestion="Verify the international SWIFT/BIC code provided by the beneficiary institution.",
                        config=config,
                    )
                ]
            return []

        # 2. India IFSC (11 characters starting with 4 letters, '0', and 6 alphanumeric characters)
        if (len(clean_routing) == 11 and clean_routing[:4].isalpha() and clean_routing[4] == "0") or "india" in country:
            if not IFSC_REGEX.match(clean_routing):
                return [
                    self.create_finding(
                        field="bank_routing_number",
                        code="INVALID_IFSC_FORMAT",
                        message="Indian IFSC code format is invalid. Expected 11 characters starting with 4 letters, '0', and 6 alphanumeric characters.",
                        suggestion="Verify the IFSC code on an official bank passbook, statement, or cheque leaf.",
                        config=config,
                    )
                ]
            return []

        # 3. US ABA Routing Transit Number (9 numeric digits with Mod-10 checksum)
        if "united states" in country or (clean_routing.isdigit() and len(clean_routing) == 9):
            if not clean_routing.isdigit() or len(clean_routing) != 9:
                return [
                    self.create_finding(
                        field="bank_routing_number",
                        code="INVALID_ABA_FORMAT",
                        message="US ABA routing transit number must contain exactly 9 numeric digits.",
                        suggestion="Enter the 9-digit ABA routing transit number located between the MICR colons on a check.",
                        config=config,
                    )
                ]
            if not validate_aba_checksum(clean_routing):
                return [
                    self.create_finding(
                        field="bank_routing_number",
                        code="INVALID_ABA_CHECKSUM",
                        message="US ABA routing number failed the Federal Reserve Mod-10 checksum verification.",
                        suggestion="Double-check the 9 digits against your bank branch routing transit specification.",
                        config=config,
                    )
                ]
            return []

        # 4. Fallback Generic Routing Warning (Unknown format)
        if len(clean_routing) < 3 or len(clean_routing) > 20:
            return [
                self.create_finding(
                    field="bank_routing_number",
                    code="UNUSUAL_ROUTING_LENGTH",
                    severity=Severity.WARNING,
                    message=f"Bank routing identifier length ({len(clean_routing)} characters) is unusual for {data.get('bank_country')}.",
                    suggestion="Ensure routing code matches the local clearing system (e.g., Sort Code, BSB, ABA, IFSC, or SWIFT/BIC).",
                    config=config,
                )
            ]

        return []


class BankAccountStructureRule(ValidationRule):
    """Structural format and sanity check for bank account numbers.
    
    CRITICAL: Never reveals, echoes, or logs the raw account number in findings!
    """

    def __init__(self):
        super().__init__(
            rule_id="FMT_BANK_ACCOUNT_STRUCTURAL",
            name="Bank Account Structural Validation",
            description="Verifies bank account number character length and rejects obvious dummy sequences.",
            default_severity=Severity.ERROR,
            target_fields=["bank_account_number"],
            category="format",
        )

    def validate(self, data: Dict[str, Any], context: Dict[str, Any], config: ValidationConfig) -> List[ValidationFinding]:
        account = data.get("bank_account_number")
        if not account or not isinstance(account, str) or not account.strip():
            return []  # Defer to required check

        clean_account = account.strip().replace(" ", "").replace("-", "")

        # Structural length: typical range for domestic accounts & international IBAN is 6 to 34 characters
        if len(clean_account) < 6 or len(clean_account) > 34:
            return [
                self.create_finding(
                    field="bank_account_number",
                    code="INVALID_ACCOUNT_LENGTH",
                    message="Bank account number length must be between 6 and 34 characters.",
                    suggestion="Verify the complete domestic account number or international IBAN.",
                    config=config,
                )
            ]

        # Reject obvious dummy sequences (all identical digits, e.g. "00000000", "11111111")
        if clean_account.isdigit() and len(set(clean_account)) == 1:
            return [
                self.create_finding(
                    field="bank_account_number",
                    code="DUMMY_ACCOUNT_SEQUENCE",
                    message="Bank account number appears to be an invalid placeholder sequence (repeated single digit).",
                    suggestion="Provide the legitimate, active commercial bank account number.",
                    config=config,
                )
            ]

        # Reject simple ascending or descending sequences
        digits = clean_account
        if digits.isdigit() and len(digits) >= 8:
            asc = "01234567890123456789"
            desc = "98765432109876543210"
            if digits in asc or digits in desc:
                return [
                    self.create_finding(
                        field="bank_account_number",
                        code="SEQUENTIAL_ACCOUNT_DUMMY",
                        message="Bank account number appears to be an invalid sequential placeholder.",
                        suggestion="Enter the genuine commercial account number assigned by your financial institution.",
                        config=config,
                    )
                ]

        return []


def get_format_rules() -> List[ValidationRule]:
    """Instantiates and returns all format validation rules."""
    return [
        EmailFormatRule(),
        PhoneFormatRule(),
        TaxIdFormatRule(),
        BankRoutingFormatRule(),
        BankAccountStructureRule(),
    ]
