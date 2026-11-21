"""Integration tests for vendor validation API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.vendor import Vendor
from app.services.vendor_service import vendor_service
from app.schemas.vendor import VendorCreate


def get_sample_valid_vendor_payload():
    return {
        "legal_name": "Apex Global Logistics Inc.",
        "trade_name": "Apex Express",
        "business_type": "Private Limited",
        "country_of_incorporation": "United States",
        "registration_number": "US-DEL-2024-91024",
        "contact_name": "Sarah Jenkins",
        "contact_email": "sarah.jenkins@apexgl.com",
        "contact_phone": "+1 (555) 392-8172",
        "address_line1": "100 Enterprise Way",
        "address_line2": "Suite 450",
        "city": "San Jose",
        "state_province": "California",
        "postal_code": "95110",
        "address_country": "United States",
        "tax_id_type": "EIN",
        "tax_id_number": "94-3829104",
        "bank_account_holder_name": "Apex Global Logistics Inc.",
        "bank_name": "Silicon Valley Commercial Bank",
        "bank_account_number": "8839201948201",
        "bank_routing_number": "121000358",
        "bank_country": "United States",
    }


class TestValidationAPIEndpoints:
    """Verifies POST /api/v1/vendors/validate and POST /api/v1/vendors/{vendor_id}/validate."""

    def test_validate_unsaved_vendor_payload_success(self, client: TestClient):
        """Valid vendor submission payload returns 200 OK with valid=True and status=PASSED."""
        payload = get_sample_valid_vendor_payload()
        response = client.post("/api/v1/vendors/validate", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["status"] in ("PASSED", "PASSED_WITH_WARNINGS")
        assert data["summary"]["failed"] == 0
        assert "validation_id" in data
        assert "validated_at" in data
        assert data["ruleset_version"] == "1.0.0"

    def test_validate_partial_or_invalid_payload_returns_structured_findings(self, client: TestClient):
        """Partially completed payload reports all missing required fields without failing request with 422."""
        partial_payload = {
            "legal_name": "Incomplete Vendor Inc.",
            "contact_email": "not-an-email",
            # All other mandatory fields missing
        }
        response = client.post("/api/v1/vendors/validate", json=partial_payload)

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["status"] == "FAILED"
        assert data["summary"]["failed"] > 0

        # Verify findings list includes missing fields and invalid email
        finding_fields = [f["field"] for f in data["findings"]]
        assert "contact_email" in finding_fields
        assert "bank_account_number" in finding_fields
        assert "tax_id_number" in finding_fields

    def test_validate_existing_vendor_record(self, client: TestClient, test_db_session: Session):
        """Validates a persisted vendor record; decrypts banking info safely in memory."""
        payload = get_sample_valid_vendor_payload()
        created_vendor = vendor_service.create_vendor(test_db_session, VendorCreate(**payload))

        response = client.post(f"/api/v1/vendors/{created_vendor.id}/validate")
        assert response.status_code == 200
        data = response.json()

        assert data["vendor_id"] == created_vendor.id
        assert data["valid"] is True
        assert data["summary"]["failed"] == 0

        # CRITICAL SECURITY CHECK: Raw account number and ciphertext must not appear anywhere in result JSON
        raw_account = payload["bank_account_number"]
        response_str = response.text
        assert raw_account not in response_str
        assert "enc:v1:" not in response_str

        # Confirm vendor status was NOT modified
        refreshed_vendor = test_db_session.get(Vendor, created_vendor.id)
        assert refreshed_vendor.status == "SUBMITTED"

    def test_validate_non_existent_vendor_returns_404(self, client: TestClient):
        """Validation of non-existent vendor ID returns 404 Not Found."""
        response = client.post("/api/v1/vendors/non-existent-uuid-999/validate")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_existing_vendor_endpoints_remain_functional(self, client: TestClient, test_db_session: Session):
        """Existing vendor endpoints (GET /vendors, POST /vendors, GET /vendors/{id}) remain 100% backward compatible."""
        # Test creation
        payload = get_sample_valid_vendor_payload()
        payload["registration_number"] = "REG-REGRESSION-CHECK-01"
        create_res = client.post("/api/v1/vendors", json=payload)
        assert create_res.status_code == 201
        created_id = create_res.json()["id"]

        # Test listing
        list_res = client.get("/api/v1/vendors?page=1&page_size=10")
        assert list_res.status_code == 200
        assert list_res.json()["total"] >= 1

        # Test single retrieval
        get_res = client.get(f"/api/v1/vendors/{created_id}")
        assert get_res.status_code == 200
        assert get_res.json()["id"] == created_id
        assert get_res.json()["bank_account_number_masked"].startswith("••••")
