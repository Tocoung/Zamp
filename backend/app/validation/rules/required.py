"""Mandatory required-field validation rules."""

from typing import Any, Dict, List
from app.validation.models import Severity, ValidationFinding
from app.validation.config import ValidationConfig
from app.validation.rules.base import ValidationRule

REQUIRED_FIELDS_METADATA = [
    # Identity & Company
    ("legal_name", "COMPANY_LEGAL_NAME_REQUIRED", "Legal company name is required.", "Provide the registered legal entity name."),
    ("business_type", "COMPANY_BUSINESS_TYPE_REQUIRED", "Business type is required.", "Select an appropriate entity classification (e.g. Private Limited, LLC)."),
    ("country_of_incorporation", "COMPANY_INCORPORATION_COUNTRY_REQUIRED", "Country of incorporation is required.", "Provide the legal jurisdiction where the business was incorporated."),
    ("registration_number", "COMPANY_REGISTRATION_NUMBER_REQUIRED", "Company registration number is required.", "Enter the statutory company incorporation or commercial registry number."),
    
    # Contact
    ("contact_name", "CONTACT_NAME_REQUIRED", "Primary contact name is required.", "Provide the full name of an authorized company representative."),
    ("contact_email", "CONTACT_EMAIL_REQUIRED", "Business contact email is required.", "Provide an active company email address for operational communications."),
    ("contact_phone", "CONTACT_PHONE_REQUIRED", "Contact phone number is required.", "Provide a telephone number including country dialing prefix."),
    
    # Address
    ("address_line1", "ADDRESS_LINE1_REQUIRED", "Registered address line 1 is required.", "Enter the primary street address or building number."),
    ("city", "ADDRESS_CITY_REQUIRED", "City is required.", "Provide the registered municipal city or town."),
    ("state_province", "ADDRESS_STATE_PROVINCE_REQUIRED", "State or province is required.", "Provide the administrative state, province, or region."),
    ("postal_code", "ADDRESS_POSTAL_CODE_REQUIRED", "Postal code is required.", "Enter the postal or ZIP code."),
    ("address_country", "ADDRESS_COUNTRY_REQUIRED", "Address country is required.", "Provide the country corresponding to the registered physical address."),
    
    # Tax
    ("tax_id_type", "TAX_ID_TYPE_REQUIRED", "Tax identification type is required.", "Specify the tax identifier scheme (e.g. EIN, GSTIN, PAN, VAT)."),
    ("tax_id_number", "TAX_ID_NUMBER_REQUIRED", "Tax identification number is required.", "Enter the official tax registration or identification number."),
    
    # Banking
    ("bank_account_holder_name", "BANK_ACCOUNT_HOLDER_REQUIRED", "Bank account holder name is required.", "Enter the exact account holder name as registered with the financial institution."),
    ("bank_name", "BANK_NAME_REQUIRED", "Bank name is required.", "Provide the full commercial or institutional name of the bank."),
    ("bank_account_number", "BANK_ACCOUNT_NUMBER_REQUIRED", "Bank account number is required.", "Provide the primary bank account number or IBAN."),
    ("bank_routing_number", "BANK_ROUTING_NUMBER_REQUIRED", "Bank routing identifier is required.", "Provide the appropriate routing transit code (e.g. ABA, IFSC, SWIFT/BIC)."),
    ("bank_country", "BANK_COUNTRY_REQUIRED", "Bank country is required.", "Select the country where the bank account is domiciled."),
]


class FieldRequiredRule(ValidationRule):
    """Checks whether a specific mandatory field is populated and non-whitespace."""

    def __init__(self, field_name: str, rule_id: str, message: str, suggestion: str):
        super().__init__(
            rule_id=rule_id,
            name=f"Required Field: {field_name}",
            description=f"Ensures that {field_name} is provided and not empty or whitespace-only.",
            default_severity=Severity.ERROR,
            target_fields=[field_name],
            category="required",
        )
        self.field_name = field_name
        self.custom_message = message
        self.custom_suggestion = suggestion

    def validate(
        self,
        data: Dict[str, Any],
        context: Dict[str, Any],
        config: ValidationConfig,
    ) -> List[ValidationFinding]:
        val = data.get(self.field_name)

        if val is None or (isinstance(val, str) and not val.strip()):
            return [
                self.create_finding(
                    field=self.field_name,
                    code="REQUIRED_FIELD_MISSING",
                    message=self.custom_message,
                    suggestion=self.custom_suggestion,
                    config=config,
                )
            ]
        return []


def get_required_field_rules() -> List[FieldRequiredRule]:
    """Instantiates and returns all mandatory field rules."""
    return [
        FieldRequiredRule(
            field_name=field,
            rule_id=rule_id,
            message=msg,
            suggestion=sugg,
        )
        for field, rule_id, msg, sugg in REQUIRED_FIELDS_METADATA
    ]
