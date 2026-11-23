"""Integration tests for verification API endpoints: POST run, GET latest, GET history, GET run_id."""

import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.vendor import Vendor
from app.models.document import VendorDocument
from app.models.extraction import DocumentExtraction
from app.core.security import encrypt_account_number


@pytest.fixture
def sample_vendor(test_db_session: Session) -> Vendor:
    """Creates a sample vendor for verification testing."""
    v = Vendor(
        id=str(uuid.uuid4()),
        legal_name="Reliance Industries Limited",
        trade_name="RIL",
        business_type="PUBLIC_LIMITED",
        country_of_incorporation="IN",
        registration_number="L17110MH1973PLC019786",
        contact_name="Mukesh Ambani",
        contact_email="procurement@ril.com",
        contact_phone="+919876543210",
        address_line1="Maker Chambers IV, 3rd Floor, 222 Nariman Point",
        city="Mumbai",
        state_province="Maharashtra",
        postal_code="400021",
        address_country="IN",
        tax_id_type="GSTIN",
        tax_id_number="27AAACR1234A1Z5",
        bank_account_holder_name="Reliance Industries Limited",
        bank_name="State Bank of India",
        bank_account_number=encrypt_account_number("98765432101234"),
        bank_routing_number="SBIN0000300",
        bank_country="IN",
        status="SUBMITTED",
    )
    test_db_session.add(v)
    test_db_session.commit()
    test_db_session.refresh(v)
    return v


class TestVerificationAPIEndpoints:
    """Tests for /api/v1/vendors/{vendor_id}/verification endpoints."""

    def test_run_verification_endpoint(self, client: TestClient, sample_vendor: Vendor):
        """POST /api/v1/vendors/{vendor_id}/verification executes and returns 201 Created."""
        resp = client.post(f"/api/v1/vendors/{sample_vendor.id}/verification")
        assert resp.status_code == 201
        data = resp.json()
        assert data["vendor_id"] == sample_vendor.id
        assert "status" in data
        assert "total_comparisons" in data
        assert "findings" in data
        assert len(data["findings"]) >= 12

        # Verify no sensitive bank account plaintext is returned
        raw_json_str = resp.text
        assert "98765432101234" not in raw_json_str
        assert "••••••••1234" in raw_json_str

    def test_get_latest_verification_endpoint(self, client: TestClient, sample_vendor: Vendor):
        """GET /api/v1/vendors/{vendor_id}/verification/latest returns 200 OK after execution."""
        # 1. Run verification
        post_resp = client.post(f"/api/v1/vendors/{sample_vendor.id}/verification")
        assert post_resp.status_code == 201
        run_id = post_resp.json()["id"]

        # 2. Get latest
        get_resp = client.get(f"/api/v1/vendors/{sample_vendor.id}/verification/latest")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["id"] == run_id
        assert data["vendor_id"] == sample_vendor.id
        assert len(data["findings"]) >= 12

    def test_get_verification_history_endpoint(self, client: TestClient, sample_vendor: Vendor):
        """GET /api/v1/vendors/{vendor_id}/verification/history returns paginated history."""
        # Run twice
        client.post(f"/api/v1/vendors/{sample_vendor.id}/verification")
        client.post(f"/api/v1/vendors/{sample_vendor.id}/verification")

        resp = client.get(f"/api/v1/vendors/{sample_vendor.id}/verification/history?page=1&page_size=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        assert data["page"] == 1
        assert len(data["items"]) >= 2
        assert "findings" not in data["items"][0]  # History items are lightweight summaries

    def test_get_specific_verification_run_endpoint(self, client: TestClient, sample_vendor: Vendor):
        """GET /api/v1/vendors/{vendor_id}/verification/{run_id} returns 200 OK."""
        post_resp = client.post(f"/api/v1/vendors/{sample_vendor.id}/verification")
        run_id = post_resp.json()["id"]

        resp = client.get(f"/api/v1/vendors/{sample_vendor.id}/verification/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == run_id
        assert data["vendor_id"] == sample_vendor.id

    def test_404_for_unknown_vendor(self, client: TestClient):
        """Endpoints return 404 for unknown vendor ID."""
        fake_id = str(uuid.uuid4())
        assert client.post(f"/api/v1/vendors/{fake_id}/verification").status_code == 404
        assert client.get(f"/api/v1/vendors/{fake_id}/verification/latest").status_code == 404
        assert client.get(f"/api/v1/vendors/{fake_id}/verification/history").status_code == 404
        assert client.get(f"/api/v1/vendors/{fake_id}/verification/fake_run").status_code == 404

    def test_404_when_no_verification_run_exists(self, client: TestClient, sample_vendor: Vendor):
        """GET latest returns 404 when no verification run exists yet."""
        # Create fresh vendor with no runs
        resp = client.get(f"/api/v1/vendors/{sample_vendor.id}/verification/latest")
        assert resp.status_code == 404
        assert "No verification run has been executed" in resp.json()["detail"]
