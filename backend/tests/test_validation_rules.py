"""Unit tests for individual validation rules (required, formats, consistency)."""

import pytest
from app.validation.config import ValidationConfig
from app.validation.models import Severity
from app.validation.rules.required import get_required_field_rules
from app.validation.rules.formats import (
    EmailFormatRule,
    PhoneFormatRule,
    TaxIdFormatRule,
    BankRoutingFormatRule,
    BankAccountStructureRule,
    validate_aba_checksum,
)
from app.validation.rules.consistency import (
    TaxCountryCompatibilityRule,
    RoutingBankCountryCompatibilityRule,
    CrossBorderRegistrationRule,
    AccountHolderLegalNameMatchRule,
)


# ==============================================================================
# 1. Required Fields Tests
# ==============================================================================

class TestRequiredFieldRules:
    """Verifies mandatory fields, empty values, whitespace, and optional field handling."""

    def test_missing_mandatory_field_emits_error(self):
        rules = {r.target_fields[0]: r for r in get_required_field_rules()}
        config = ValidationConfig()

        # Missing legal_name
        legal_rule = rules["legal_name"]
        findings = legal_rule.validate({}, {}, config)
        assert len(findings) == 1
        assert findings[0].severity == Severity.ERROR
        assert findings[0].code == "REQUIRED_FIELD_MISSING"
        assert findings[0].field == "legal_name"

    def test_empty_string_and_whitespace_only_fail_required_check(self):
        rules = {r.target_fields[0]: r for r in get_required_field_rules()}
        config = ValidationConfig()

        email_rule = rules["contact_email"]
        assert len(email_rule.validate({"contact_email": ""}, {}, config)) == 1
        assert len(email_rule.validate({"contact_email": "   \t\n  "}, {}, config)) == 1

        # Non-empty passes
        assert len(email_rule.validate({"contact_email": "ops@vendor.com"}, {}, config)) == 0

    def test_optional_fields_have_no_required_rules(self):
        """trade_name and address_line2 are optional and have no mandatory required rules."""
        target_fields = [r.target_fields[0] for r in get_required_field_rules()]
        assert "trade_name" not in target_fields
        assert "address_line2" not in target_fields


# ==============================================================================
# 2. Format Validation Rules Tests
# ==============================================================================

class TestFormatRules:
    """Verifies contact, tax, and banking format validation."""

    def test_email_format_valid_and_invalid(self):
        rule = EmailFormatRule()
        config = ValidationConfig()

        assert rule.validate({"contact_email": "valid.person@acme-logistics.com"}, {}, config) == []
        assert rule.validate({"contact_email": "contact+support@vendor.co.uk"}, {}, config) == []

        # Invalid emails
        assert len(rule.validate({"contact_email": "not-an-email"}, {}, config)) == 1
        assert len(rule.validate({"contact_email": "user@domain"}, {}, config)) == 1
        assert len(rule.validate({"contact_email": "user@domain."}, {}, config)) == 1
        assert len(rule.validate({"contact_email": "@domain.com"}, {}, config)) == 1

    def test_phone_format_valid_and_invalid(self):
        rule = PhoneFormatRule()
        config = ValidationConfig()

        # Valid international forms
        assert rule.validate({"contact_phone": "+1 (555) 234-5678"}, {}, config) == []
        assert rule.validate({"contact_phone": "+91 98765 43210"}, {}, config) == []
        assert rule.validate({"contact_phone": "020 7946 0912"}, {}, config) == []
        assert rule.validate({"contact_phone": "+44-20-7946-0912"}, {}, config) == []

        # Invalid: contains letters
        findings_alpha = rule.validate({"contact_phone": "+1 555-CALL-NOW"}, {}, config)
        assert len(findings_alpha) == 1
        assert findings_alpha[0].code == "INVALID_PHONE_STRUCTURE"

        # Invalid: too short (< 7 digits)
        findings_short = rule.validate({"contact_phone": "12345"}, {}, config)
        assert len(findings_short) == 1
        assert findings_short[0].code == "INVALID_PHONE_DIGIT_COUNT"

    def test_india_gstin_format_valid_and_invalid(self):
        rule = TaxIdFormatRule()
        config = ValidationConfig()

        valid_data = {
            "country_of_incorporation": "India",
            "tax_id_type": "GSTIN",
            "tax_id_number": "29ABCDE1234F1Z5",
        }
        assert rule.validate(valid_data, {}, config) == []

        # Invalid GSTIN: 14 chars instead of 15
        invalid_data = dict(valid_data, tax_id_number="29ABCDE1234F1Z")
        findings = rule.validate(invalid_data, {}, config)
        assert len(findings) == 1
        assert findings[0].code == "INVALID_GSTIN_FORMAT"

    def test_india_pan_format_valid_and_invalid(self):
        rule = TaxIdFormatRule()
        config = ValidationConfig()

        valid_data = {
            "country_of_incorporation": "India",
            "tax_id_type": "PAN",
            "tax_id_number": "ABCDE1234F",
        }
        assert rule.validate(valid_data, {}, config) == []

        # Invalid PAN: wrong structure (digits where letters should be)
        invalid_data = dict(valid_data, tax_id_number="12CDE1234F")
        findings = rule.validate(invalid_data, {}, config)
        assert len(findings) == 1
        assert findings[0].code == "INVALID_PAN_FORMAT"

    def test_us_ein_format_and_prefix_validation(self):
        rule = TaxIdFormatRule()
        config = ValidationConfig()

        # Valid standard EIN
        assert rule.validate({
            "country_of_incorporation": "United States",
            "tax_id_type": "EIN",
            "tax_id_number": "12-3456789",
        }, {}, config) == []

        # Valid unhyphenated EIN
        assert rule.validate({
            "country_of_incorporation": "United States",
            "tax_id_type": "EIN",
            "tax_id_number": "943829104",
        }, {}, config) == []

        # Invalid EIN: invalid IRS prefix "00"
        findings_bad_prefix = rule.validate({
            "country_of_incorporation": "United States",
            "tax_id_type": "EIN",
            "tax_id_number": "00-1234567",
        }, {}, config)
        assert len(findings_bad_prefix) == 1
        assert findings_bad_prefix[0].code == "INVALID_EIN_PREFIX"

        # Invalid EIN: wrong length (8 digits)
        findings_bad_len = rule.validate({
            "country_of_incorporation": "United States",
            "tax_id_type": "EIN",
            "tax_id_number": "12-345678",
        }, {}, config)
        assert len(findings_bad_len) == 1
        assert findings_bad_len[0].code == "INVALID_EIN_FORMAT"

    def test_uk_vat_format_valid_and_invalid(self):
        rule = TaxIdFormatRule()
        config = ValidationConfig()

        # Valid UK VAT numbers (standard 9 digits)
        assert rule.validate({
            "country_of_incorporation": "United Kingdom",
            "tax_id_type": "VAT",
            "tax_id_number": "GB 123 4567 89",
        }, {}, config) == []

        assert rule.validate({
            "country_of_incorporation": "United Kingdom",
            "tax_id_type": "VAT",
            "tax_id_number": "987654321",
        }, {}, config) == []

        # Valid 12 digits (branch trader)
        assert rule.validate({
            "country_of_incorporation": "United Kingdom",
            "tax_id_type": "VAT",
            "tax_id_number": "GB123456789012",
        }, {}, config) == []

        # Invalid UK VAT
        findings = rule.validate({
            "country_of_incorporation": "United Kingdom",
            "tax_id_type": "VAT",
            "tax_id_number": "GB12345",
        }, {}, config)
        assert len(findings) == 1
        assert findings[0].code == "INVALID_UK_VAT_FORMAT"

    def test_unsupported_tax_type_emits_info_note(self):
        rule = TaxIdFormatRule()
        config = ValidationConfig()

        findings = rule.validate({
            "country_of_incorporation": "Australia",
            "tax_id_type": "ABN",
            "tax_id_number": "51824753556",
        }, {}, config)
        assert len(findings) == 1
        assert findings[0].severity == Severity.INFO
        assert findings[0].code == "TAX_FORMAT_UNSUPPORTED_NOTE"

    def test_india_ifsc_format_valid_and_invalid(self):
        rule = BankRoutingFormatRule()
        config = ValidationConfig()

        assert rule.validate({
            "bank_country": "India",
            "bank_routing_number": "HDFC0001234",
        }, {}, config) == []

        # Invalid: 5th character not '0'
        findings = rule.validate({
            "bank_country": "India",
            "bank_routing_number": "HDFC1001234",
        }, {}, config)
        assert len(findings) == 1
        assert findings[0].code == "INVALID_IFSC_FORMAT"

    def test_us_aba_routing_checksum_verification(self):
        rule = BankRoutingFormatRule()
        config = ValidationConfig()

        # Known valid Federal Reserve ABA routing numbers
        assert validate_aba_checksum("121000358") is True  # Silicon Valley Bank / First Citizens
        assert validate_aba_checksum("021000021") is True  # JPMorgan Chase NY
        assert validate_aba_checksum("111000025") is True  # Bank of America Dallas

        assert rule.validate({
            "bank_country": "United States",
            "bank_routing_number": "121000358",
        }, {}, config) == []

        # Invalid ABA: bad checksum (last digit modified from 8 to 9)
        assert validate_aba_checksum("121000359") is False
        findings = rule.validate({
            "bank_country": "United States",
            "bank_routing_number": "121000359",
        }, {}, config)
        assert len(findings) == 1
        assert findings[0].code == "INVALID_ABA_CHECKSUM"

    def test_swift_bic_format_valid_and_invalid(self):
        rule = BankRoutingFormatRule()
        config = ValidationConfig()

        # 8-char SWIFT
        assert rule.validate({
            "bank_country": "Germany",
            "bank_routing_number": "DEUTDEDD",
        }, {}, config) == []

        # 11-char SWIFT
        assert rule.validate({
            "bank_country": "United States",
            "bank_routing_number": "CHASUS33XXX",
        }, {}, config) == []

        # Invalid SWIFT
        findings = rule.validate({
            "bank_country": "Germany",
            "bank_routing_number": "INVALID_SWIFT_CODE_TOO_LONG",
        }, {}, config)
        assert len(findings) == 1

    def test_bank_account_structure_valid_and_dummy_rejection(self):
        rule = BankAccountStructureRule()
        config = ValidationConfig()

        # Valid account number
        assert rule.validate({"bank_account_number": "8839201948201"}, {}, config) == []
        assert rule.validate({"bank_account_number": "GB29NWBK60161331926819"}, {}, config) == []

        # Too short (< 6 chars)
        findings_short = rule.validate({"bank_account_number": "12345"}, {}, config)
        assert len(findings_short) == 1
        assert findings_short[0].code == "INVALID_ACCOUNT_LENGTH"

        # Repeated dummy sequence ("00000000")
        findings_dummy = rule.validate({"bank_account_number": "000000000"}, {}, config)
        assert len(findings_dummy) == 1
        assert findings_dummy[0].code == "DUMMY_ACCOUNT_SEQUENCE"

        # Sequential dummy sequence ("123456789")
        findings_seq = rule.validate({"bank_account_number": "123456789"}, {}, config)
        assert len(findings_seq) == 1
        assert findings_seq[0].code == "SEQUENTIAL_ACCOUNT_DUMMY"


# ==============================================================================
# 3. Consistency Rules Tests
# ==============================================================================

class TestConsistencyRules:
    """Verifies cross-field consistency checks."""

    def test_tax_type_country_mismatch_generates_warning(self):
        rule = TaxCountryCompatibilityRule()
        config = ValidationConfig()

        # GSTIN declared for US entity
        findings = rule.validate({
            "tax_id_type": "GSTIN",
            "country_of_incorporation": "United States",
        }, {}, config)
        assert len(findings) == 1
        assert findings[0].severity == Severity.WARNING
        assert findings[0].code == "TAX_TYPE_COUNTRY_MISMATCH"

        # EIN declared for Indian entity
        findings_ein = rule.validate({
            "tax_id_type": "EIN",
            "country_of_incorporation": "India",
        }, {}, config)
        assert len(findings_ein) == 1
        assert findings_ein[0].severity == Severity.WARNING

    def test_routing_and_bank_country_mismatch_generates_warning(self):
        rule = RoutingBankCountryCompatibilityRule()
        config = ValidationConfig()

        # IFSC used for UK bank
        findings = rule.validate({
            "bank_routing_number": "HDFC0001234",
            "bank_country": "United Kingdom",
        }, {}, config)
        assert len(findings) == 1
        assert findings[0].severity == Severity.WARNING
        assert findings[0].code == "ROUTING_BANK_COUNTRY_MISMATCH"

    def test_cross_border_operations_emits_info_not_error(self):
        """Cross-border incorporation vs address is a legitimate scenario and must NOT be an error or warning."""
        rule = CrossBorderRegistrationRule()
        config = ValidationConfig()

        findings = rule.validate({
            "country_of_incorporation": "Delaware, United States",
            "address_country": "United Kingdom",
        }, {}, config)
        assert len(findings) == 1
        assert findings[0].severity == Severity.INFO
        assert findings[0].code == "CROSS_BORDER_OPERATIONS_NOTE"

    def test_account_holder_name_matching_heuristics(self):
        rule = AccountHolderLegalNameMatchRule()
        config = ValidationConfig()

        # Identical or substring match -> 0 findings
        assert rule.validate({
            "legal_name": "Acme Global Solutions Inc.",
            "bank_account_holder_name": "Acme Global Solutions Inc",
        }, {}, config) == []

        # Token overlap with corporate suffixes stripped -> 0 findings
        assert rule.validate({
            "legal_name": "Apex Enterprise Technologies LLC",
            "bank_account_holder_name": "Apex Enterprise Corp",
        }, {}, config) == []

        # Trade name / DBA match -> 0 findings
        assert rule.validate({
            "legal_name": "International Business Holdings Inc.",
            "trade_name": "Acme Express",
            "bank_account_holder_name": "Acme Express Commercial",
        }, {}, config) == []

        # Complete mismatch -> WARNING
        findings = rule.validate({
            "legal_name": "Apex Enterprise Technologies LLC",
            "trade_name": None,
            "bank_account_holder_name": "John Doe Personal Holdings",
        }, {}, config)
        assert len(findings) == 1
        assert findings[0].severity == Severity.WARNING
        assert findings[0].code == "ACCOUNT_HOLDER_NAME_MISMATCH"
