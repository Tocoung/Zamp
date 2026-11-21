"""Pydantic schemas for vendor intake and serialization."""

import re
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def mask_bank_account(account_number: Optional[str]) -> str:
    """Masks a bank account number to hide all but the last 4 characters.
    
    Example:
        '123456789012' -> '••••••••9012'
        '1234' -> '••••1234'
        '12' -> '••••'
    """
    if not account_number:
        return "••••"
    cleaned = account_number.strip()
    if len(cleaned) <= 4:
        return "••••" + cleaned
    masked_prefix = "•" * (len(cleaned) - 4)
    # Cap prefix to 8 dots for cleaner uniform display
    if len(masked_prefix) > 8:
        masked_prefix = "••••••••"
    return f"{masked_prefix}{cleaned[-4:]}"


class VendorBase(BaseModel):
    """Base fields for vendor representation."""
    legal_name: str = Field(..., min_length=2, max_length=255, examples=["Acme Logistics Inc."])
    trade_name: Optional[str] = Field(None, max_length=255, examples=["Acme Global"])
    business_type: str = Field(..., max_length=50, examples=["Private Limited"])
    country_of_incorporation: str = Field(..., min_length=2, max_length=100, examples=["United States"])
    registration_number: str = Field(..., min_length=2, max_length=100, examples=["REG-2024-98765"])

    contact_name: str = Field(..., min_length=2, max_length=255, examples=["Jane Doe"])
    contact_email: str = Field(..., min_length=5, max_length=255, examples=["jane.doe@acme.com"])
    contact_phone: str = Field(..., min_length=5, max_length=50, examples=["+1 (555) 234-5678"])

    address_line1: str = Field(..., min_length=3, max_length=255, examples=["123 Enterprise Blvd"])
    address_line2: Optional[str] = Field(None, max_length=255, examples=["Suite 400"])
    city: str = Field(..., min_length=1, max_length=100, examples=["Austin"])
    state_province: str = Field(..., min_length=1, max_length=100, examples=["Texas"])
    postal_code: str = Field(..., min_length=2, max_length=20, examples=["78701"])
    address_country: str = Field(..., min_length=2, max_length=100, examples=["United States"])

    tax_id_type: str = Field(..., min_length=2, max_length=50, examples=["EIN"])
    tax_id_number: str = Field(..., min_length=2, max_length=100, examples=["12-3456789"])

    bank_account_holder_name: str = Field(..., min_length=2, max_length=255, examples=["Acme Logistics Inc."])
    bank_name: str = Field(..., min_length=2, max_length=255, examples=["JPMorgan Chase"])
    bank_routing_number: str = Field(..., min_length=3, max_length=50, examples=["021000021"])
    bank_country: str = Field(..., min_length=2, max_length=100, examples=["United States"])

    @field_validator("contact_email")
    @classmethod
    def validate_contact_email(cls, v: str) -> str:
        if isinstance(v, str):
            v_stripped = v.strip()
            if not EMAIL_REGEX.match(v_stripped):
                raise ValueError("Invalid contact email format")
            return v_stripped.lower()
        raise ValueError("Contact email must be a valid string")

    @field_validator(
        "legal_name", "business_type", "country_of_incorporation", "registration_number",
        "contact_name", "contact_phone", "address_line1", "city", "state_province",
        "postal_code", "address_country", "tax_id_type", "tax_id_number",
        "bank_account_holder_name", "bank_name", "bank_routing_number", "bank_country",
        mode="before",
    )
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        if isinstance(v, str):
            v_stripped = v.strip()
            if not v_stripped:
                raise ValueError("Field cannot be empty or whitespace only")
            return v_stripped
        return v


class VendorCreate(VendorBase):
    """Schema for vendor registration intake."""
    bank_account_number: str = Field(..., min_length=4, max_length=100, examples=["987654321098"])

    @field_validator("bank_account_number", mode="before")
    @classmethod
    def clean_account_number(cls, v: str) -> str:
        if isinstance(v, str):
            v_stripped = v.strip()
            if not v_stripped:
                raise ValueError("Bank account number cannot be empty")
            return v_stripped
        return v


class VendorUpdate(BaseModel):
    """Schema for updating an existing vendor record with optional fields."""
    legal_name: Optional[str] = Field(None, max_length=255)
    trade_name: Optional[str] = Field(None, max_length=255)
    business_type: Optional[str] = Field(None, max_length=50)
    country_of_incorporation: Optional[str] = Field(None, max_length=100)
    registration_number: Optional[str] = Field(None, max_length=100)

    contact_name: Optional[str] = Field(None, max_length=255)
    contact_email: Optional[str] = Field(None, max_length=255)
    contact_phone: Optional[str] = Field(None, max_length=50)

    address_line1: Optional[str] = Field(None, max_length=255)
    address_line2: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state_province: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    address_country: Optional[str] = Field(None, max_length=100)

    tax_id_type: Optional[str] = Field(None, max_length=50)
    tax_id_number: Optional[str] = Field(None, max_length=100)

    bank_account_holder_name: Optional[str] = Field(None, max_length=255)
    bank_name: Optional[str] = Field(None, max_length=255)
    bank_routing_number: Optional[str] = Field(None, max_length=50)
    bank_country: Optional[str] = Field(None, max_length=100)
    bank_account_number: Optional[str] = Field(None, max_length=100)

    model_config = ConfigDict(extra="ignore")


class VendorResponse(BaseModel):
    """Full vendor record response with masked banking account number."""
    id: str = Field(..., examples=["123e4567-e89b-12d3-a456-426614174000"])
    legal_name: Optional[str] = None
    trade_name: Optional[str] = None
    business_type: Optional[str] = None
    country_of_incorporation: Optional[str] = None
    registration_number: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state_province: Optional[str] = None
    postal_code: Optional[str] = None
    address_country: Optional[str] = None
    tax_id_type: Optional[str] = None
    tax_id_number: Optional[str] = None
    bank_account_holder_name: Optional[str] = None
    bank_name: Optional[str] = None
    bank_routing_number: Optional[str] = None
    bank_country: Optional[str] = None
    status: str = Field(..., examples=["SUBMITTED"])
    bank_account_number_masked: str = Field(..., examples=["••••••••1098"])
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_model(cls, vendor) -> "VendorResponse":
        """Factory to construct response with sanitized/masked banking info."""
        from app.core.security import decrypt_account_number
        plain_account = decrypt_account_number(vendor.bank_account_number, allow_legacy_plaintext=True)
        return cls(
            id=vendor.id,
            legal_name=vendor.legal_name,
            trade_name=vendor.trade_name,
            business_type=vendor.business_type,
            country_of_incorporation=vendor.country_of_incorporation,
            registration_number=vendor.registration_number,
            contact_name=vendor.contact_name,
            contact_email=vendor.contact_email,
            contact_phone=vendor.contact_phone,
            address_line1=vendor.address_line1,
            address_line2=vendor.address_line2,
            city=vendor.city,
            state_province=vendor.state_province,
            postal_code=vendor.postal_code,
            address_country=vendor.address_country,
            tax_id_type=vendor.tax_id_type,
            tax_id_number=vendor.tax_id_number,
            bank_account_holder_name=vendor.bank_account_holder_name,
            bank_name=vendor.bank_name,
            bank_routing_number=vendor.bank_routing_number,
            bank_country=vendor.bank_country,
            bank_account_number_masked=mask_bank_account(plain_account),
            status=vendor.status,
            created_at=vendor.created_at,
            updated_at=vendor.updated_at,
        )


class VendorSummary(BaseModel):
    """Compact summary schema for vendor directory listings."""
    id: str = Field(..., examples=["123e4567-e89b-12d3-a456-426614174000"])
    legal_name: str = Field(..., examples=["Acme Logistics Inc."])
    trade_name: Optional[str] = Field(None, examples=["Acme Global"])
    business_type: str = Field(..., examples=["Private Limited"])
    country_of_incorporation: str = Field(..., examples=["United States"])
    contact_email: str = Field(..., examples=["jane.doe@acme.com"])
    status: str = Field(..., examples=["SUBMITTED"])
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VendorPagination(BaseModel):
    """Paginated collection of vendor summary items."""
    items: List[VendorSummary]
    total: int = Field(..., examples=[42])
    page: int = Field(..., examples=[1])
    page_size: int = Field(..., examples=[10])
    total_pages: int = Field(..., examples=[5])
