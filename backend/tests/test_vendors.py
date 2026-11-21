"""Automated test suite for Vendor registration, retrieval, pagination, and data masking."""

import uuid
from typing import Dict, Any
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.vendor import Vendor
from app.schemas.vendor import mask_bank_account


def get_sample_vendor_payload(overrides: Dict[str, Any] = None) -> Dict[str, Any]:
    """Helper to generate a complete, valid vendor registration payload."""
    data = {
        "legal_name": "Apex Global Solutions Inc.",
        "trade_name": "Apex Global",
        "business_type": "Private Limited",
        "country_of_incorporation": "United States",
        "registration_number": f"REG-{uuid.uuid4().hex[:8].upper()}",
        "contact_name": "Eleanor Vance",
        "contact_email": f"eleanor.{uuid.uuid4().hex[:6]}@apexsolutions.com",
        "contact_phone": "+1 (555) 019-2834",
        "address_line1": "742 Evergreen Terrace",
        "address_line2": "Building B, Suite 300",
        "city": "Springfield",
        "state_province": "Oregon",
        "postal_code": "97477",
        "address_country": "United States",
        "tax_id_type": "EIN",
        "tax_id_number": "12-3456789",
        "bank_account_holder_name": "Apex Global Solutions Inc.",
        "bank_name": "Silicon Valley Commercial Bank",
        "bank_account_number": "9876543210987654",
        "bank_routing_number": "121000358",
        "bank_country": "United States",
    }
    if overrides:
        data.update(overrides)
    return data


class TestVendorSubmission:
    """Tests covering vendor creation endpoint (POST /api/v1/vendors)."""

    def test_create_vendor_success(self, client: TestClient):
        """Valid vendor registration returns 201 Created with initial SUBMITTED status and masked bank info."""
        payload = get_sample_vendor_payload()
        response = client.post("/api/v1/vendors", json=payload)

        assert response.status_code == 201
        data = response.json()

        assert "id" in data
        assert len(data["id"]) == 36  # Valid UUID4 string
        assert data["status"] == "SUBMITTED"
        assert data["legal_name"] == payload["legal_name"]
        assert data["trade_name"] == payload["trade_name"]
        assert data["business_type"] == payload["business_type"]
        assert data["country_of_incorporation"] == payload["country_of_incorporation"]
        assert data["registration_number"] == payload["registration_number"]
        assert data["contact_email"] == payload["contact_email"]
        assert data["city"] == payload["city"]
        assert data["tax_id_type"] == payload["tax_id_type"]
        assert data["bank_name"] == payload["bank_name"]

        # Critical security check: raw bank account number is NEVER returned in response
        assert "bank_account_number" not in data
        assert data["bank_account_number_masked"] == "••••••••7654"
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_vendor_missing_required_fields(self, client: TestClient):
        """Missing required fields returns 422 Unprocessable Entity with clear error details."""
        incomplete_payload = {
            "legal_name": "Incomplete Vendor Inc.",
            # Missing contact, address, tax, banking info
        }
        response = client.post("/api/v1/vendors", json=incomplete_payload)
        assert response.status_code == 422
        errors = response.json().get("detail", [])
        missing_fields = {err["loc"][-1] for err in errors if "loc" in err}
        assert "contact_email" in missing_fields
        assert "bank_account_number" in missing_fields
        assert "tax_id_number" in missing_fields

    def test_create_vendor_invalid_email_format(self, client: TestClient):
        """Invalid email returns 422."""
        payload = get_sample_vendor_payload({"contact_email": "not-an-email"})
        response = client.post("/api/v1/vendors", json=payload)
        assert response.status_code == 422

    def test_create_vendor_empty_or_whitespace_fields(self, client: TestClient):
        """Whitespace-only fields are rejected by validators with 422."""
        payload = get_sample_vendor_payload({"legal_name": "   "})
        response = client.post("/api/v1/vendors", json=payload)
        assert response.status_code == 422


class TestVendorRetrieval:
    """Tests covering vendor retrieval (GET /api/v1/vendors/{vendor_id})."""

    def test_get_vendor_by_id_success(self, client: TestClient):
        """Can retrieve previously created vendor by ID with masked banking info."""
        payload = get_sample_vendor_payload({"bank_account_number": "112233445566"})
        create_res = client.post("/api/v1/vendors", json=payload)
        assert create_res.status_code == 201
        created_vendor = create_res.json()
        vendor_id = created_vendor["id"]

        get_res = client.get(f"/api/v1/vendors/{vendor_id}")
        assert get_res.status_code == 200
        fetched_vendor = get_res.json()

        assert fetched_vendor["id"] == vendor_id
        assert fetched_vendor["legal_name"] == payload["legal_name"]
        assert fetched_vendor["status"] == "SUBMITTED"
        assert fetched_vendor["bank_account_number_masked"] == "••••••••5566"
        assert "bank_account_number" not in fetched_vendor

    def test_get_vendor_non_existent_id(self, client: TestClient):
        """Unknown vendor ID returns 404 with structured error message."""
        non_existent_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/vendors/{non_existent_id}")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestVendorListingAndPagination:
    """Tests covering vendor pagination (GET /api/v1/vendors)."""

    def test_list_vendors_pagination_structure(self, client: TestClient):
        """Endpoint returns paginated list with total, page, page_size, total_pages, and summary items."""
        # Create at least 3 distinct vendors
        for i in range(3):
            client.post("/api/v1/vendors", json=get_sample_vendor_payload({
                "legal_name": f"Pagination Test Co {i + 1}",
                "contact_email": f"pagination{i + 1}_{uuid.uuid4().hex[:4]}@example.com",
            }))

        response = client.get("/api/v1/vendors?page=1&page_size=2")
        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "total_pages" in data

        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["items"]) <= 2
        assert data["total"] >= 3
        assert data["total_pages"] >= 2

        # Check summary item fields: sensitive banking fields must NOT be present
        first_item = data["items"][0]
        assert "legal_name" in first_item
        assert "status" in first_item
        assert "bank_account_number" not in first_item
        assert "bank_account_number_masked" not in first_item  # Summaries exclude banking completely


class TestDataMaskingUtility:
    """Unit tests for the bank account masking algorithm."""

    def test_standard_account_numbers(self):
        assert mask_bank_account("123456789012") == "••••••••9012"
        assert mask_bank_account("987654321") == "•••••4321"

    def test_short_account_numbers(self):
        assert mask_bank_account("1234") == "••••1234"
        assert mask_bank_account("12") == "••••12"
        assert mask_bank_account("") == "••••"
        assert mask_bank_account(None) == "••••"


class TestDatabasePersistenceAndIsolation:
    """Verifies that vendor data is actually written to the DB and dev DB is not polluted."""

    def test_vendor_persisted_in_database(self, client: TestClient, test_db_session: Session):
        """Directly inspect database session to verify persistence."""
        unique_reg = f"PERSIST-{uuid.uuid4().hex[:8]}"
        payload = get_sample_vendor_payload({"registration_number": unique_reg})
        res = client.post("/api/v1/vendors", json=payload)
        assert res.status_code == 201
        created_id = res.json()["id"]

        # Query isolated database engine directly
        stmt = select(Vendor).where(Vendor.id == created_id)
        db_record = test_db_session.scalar(stmt)

        assert db_record is not None
        assert db_record.id == created_id
        assert db_record.registration_number == unique_reg
        assert db_record.status == "SUBMITTED"
        # Bank account is stored raw in DB for internal banking integrations
        assert db_record.bank_account_number == payload["bank_account_number"]
