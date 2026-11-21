"""Integration tests for vendor decision API endpoints, persistence, and explainability."""

from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.vendor import Vendor
from app.models.decision import VendorDecision


@pytest.fixture
def valid_vendor_payload() -> dict:
    """Standard complete, valid Indian vendor payload."""
    return {
        "legal_name": "Tata Consultancy Services Ltd",
        "trade_name": "TCS",
        "business_type": "Public Limited",
        "country_of_incorporation": "India",
        "registration_number": "L22210MH1995PLC084781",
        "contact_name": "Ratan Tata",
        "contact_email": "procurement@tcs.com",
        "contact_phone": "+919876543210",
        "address_line1": "TCS House, Raveline Street, Fort",
        "address_line2": "Off D.N. Road",
        "city": "Mumbai",
        "state_province": "Maharashtra",
        "postal_code": "400001",
        "address_country": "India",
        "tax_id_type": "GSTIN",
        "tax_id_number": "27AAACT2727Q1ZW",
        "bank_account_holder_name": "Tata Consultancy Services Ltd",
        "bank_name": "HDFC Bank",
        "bank_account_number": "50200012345678",
        "bank_routing_number": "HDFC0000060",
        "bank_country": "India",
    }


class TestDecisionAPIEndpoints:
    """Tests for /api/v1/vendors/{vendor_id}/decide, /decision, and /decision-history."""

    def test_compute_decision_for_valid_vendor_approves_and_persists(
        self, client: TestClient, test_db_session: Session, valid_vendor_payload: dict
    ):
        """Valid vendor submission evaluates to APPROVED and updates DB status transactionally."""
        # 1. Create vendor
        create_resp = client.post("/api/v1/vendors", json=valid_vendor_payload)
        assert create_resp.status_code == 201
        vendor_id = create_resp.json()["id"]
        assert create_resp.json()["status"] == "SUBMITTED"

        # 2. Run decision
        decide_resp = client.post(f"/api/v1/vendors/{vendor_id}/decide")
        assert decide_resp.status_code == 200
        decision_data = decide_resp.json()

        assert decision_data["status"] == "APPROVED"
        assert decision_data["vendor_id"] == vendor_id
        assert decision_data["decision_version"] == "1.0.0"
        assert "DETERMINISTIC_RULES_PASSED" in decision_data["reason_codes"]
        assert len(decision_data["reasons"]) >= 1
        assert any(rec["action"] == "PROCEED_WITH_ONBOARDING" for rec in decision_data["recommendations"])

        # 3. Verify vendor status in DB was updated to APPROVED
        vendor_in_db = test_db_session.get(Vendor, vendor_id)
        assert vendor_in_db is not None
        assert vendor_in_db.status == "APPROVED"

        # 4. Verify VendorDecision record was persisted
        decisions_in_db = test_db_session.query(VendorDecision).filter_by(vendor_id=vendor_id).all()
        assert len(decisions_in_db) == 1
        assert decisions_in_db[0].status == "APPROVED"
        assert decisions_in_db[0].decision_version == "1.0.0"

    def test_compute_decision_for_warning_evaluates_to_pending(
        self, client: TestClient, test_db_session: Session, valid_vendor_payload: dict
    ):
        """Vendor with a name mismatch warning evaluates to PENDING."""
        payload = dict(valid_vendor_payload)
        payload["bank_account_holder_name"] = "Completely Unrelated Operations LLC"

        create_resp = client.post("/api/v1/vendors", json=payload)
        assert create_resp.status_code == 201
        vendor_id = create_resp.json()["id"]

        decide_resp = client.post(f"/api/v1/vendors/{vendor_id}/decide")
        assert decide_resp.status_code == 200
        decision_data = decide_resp.json()

        assert decision_data["status"] == "PENDING"
        assert "ACCOUNT_HOLDER_NAME_MISMATCH" in decision_data["reason_codes"]
        assert any(r["title"] == "Bank Account Holder Name Requires Review" for r in decision_data["reasons"])
        assert any(rec["action"] == "VERIFY_ACCOUNT_HOLDER" for rec in decision_data["recommendations"])

        vendor_in_db = test_db_session.get(Vendor, vendor_id)
        assert vendor_in_db.status == "PENDING"

    def test_compute_decision_for_blocking_error_evaluates_to_rejected(
        self, client: TestClient, test_db_session: Session, valid_vendor_payload: dict
    ):
        """Vendor with invalid tax syntax evaluates to REJECTED."""
        payload = dict(valid_vendor_payload)
        payload["tax_id_number"] = "MALFORMED_GSTIN"

        create_resp = client.post("/api/v1/vendors", json=payload)
        assert create_resp.status_code == 201
        vendor_id = create_resp.json()["id"]

        decide_resp = client.post(f"/api/v1/vendors/{vendor_id}/decide")
        assert decide_resp.status_code == 200
        decision_data = decide_resp.json()

        assert decision_data["status"] == "REJECTED"
        assert "INVALID_GSTIN_FORMAT" in decision_data["reason_codes"]
        assert any(r["severity"] == "ERROR" for r in decision_data["reasons"])
        assert any(rec["action"] == "VERIFY_TAX_REGISTRATION" for rec in decision_data["recommendations"])

        vendor_in_db = test_db_session.get(Vendor, vendor_id)
        assert vendor_in_db.status == "REJECTED"

    def test_reevaluation_appends_to_history_and_updates_status(
        self, client: TestClient, test_db_session: Session, valid_vendor_payload: dict
    ):
        """Re-evaluating a vendor appends a new decision record and preserves complete audit history."""
        # 1. Start with vendor having mismatch -> PENDING
        payload = dict(valid_vendor_payload)
        payload["bank_account_holder_name"] = "Unrelated Entity Ltd"
        create_resp = client.post("/api/v1/vendors", json=payload)
        vendor_id = create_resp.json()["id"]

        # Run first decision
        resp1 = client.post(f"/api/v1/vendors/{vendor_id}/decide")
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "PENDING"

        # Correct the account holder name in the database directly to simulate vendor correction
        vendor = test_db_session.get(Vendor, vendor_id)
        vendor.bank_account_holder_name = "Tata Consultancy Services Ltd"
        test_db_session.commit()

        # Re-evaluate
        resp2 = client.post(f"/api/v1/vendors/{vendor_id}/decide")
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "APPROVED"

        # Check history endpoint has 2 records
        history_resp = client.get(f"/api/v1/vendors/{vendor_id}/decision-history")
        assert history_resp.status_code == 200
        history_data = history_resp.json()

        assert history_data["total"] == 2
        assert len(history_data["items"]) == 2
        # Deterministically ordered: latest (APPROVED) first, older (PENDING) second
        assert history_data["items"][0]["status"] == "APPROVED"
        assert history_data["items"][1]["status"] == "PENDING"

        # Vendor status reflects the latest decision
        vendor_refreshed = test_db_session.get(Vendor, vendor_id)
        assert vendor_refreshed.status == "APPROVED"

    def test_get_latest_decision_endpoint(
        self, client: TestClient, valid_vendor_payload: dict
    ):
        """GET /decision returns 404 before decision is run, and returns latest decision after."""
        create_resp = client.post("/api/v1/vendors", json=valid_vendor_payload)
        vendor_id = create_resp.json()["id"]

        # Before running decision -> 404
        get_before = client.get(f"/api/v1/vendors/{vendor_id}/decision")
        assert get_before.status_code == 404
        assert "No decision" in get_before.json()["detail"]

        # Run decision
        client.post(f"/api/v1/vendors/{vendor_id}/decide")

        # After running decision -> 200
        get_after = client.get(f"/api/v1/vendors/{vendor_id}/decision")
        assert get_after.status_code == 200
        assert get_after.json()["status"] == "APPROVED"
        assert get_after.json()["vendor_id"] == vendor_id

    def test_unknown_vendor_returns_404(self, client: TestClient):
        """All decision endpoints must return 404 for non-existent vendor IDs."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        assert client.post(f"/api/v1/vendors/{fake_id}/decide").status_code == 404
        assert client.get(f"/api/v1/vendors/{fake_id}/decision").status_code == 404
        assert client.get(f"/api/v1/vendors/{fake_id}/decision-history").status_code == 404

    def test_get_and_validate_endpoints_do_not_mutate_vendor_status(
        self, client: TestClient, test_db_session: Session, valid_vendor_payload: dict
    ):
        """Ordinary GET /vendors/{id} and POST /validate must never mutate vendor status."""
        create_resp = client.post("/api/v1/vendors", json=valid_vendor_payload)
        vendor_id = create_resp.json()["id"]

        # Call GET
        get_resp = client.get(f"/api/v1/vendors/{vendor_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "SUBMITTED"

        # Call validate
        val_resp = client.post(f"/api/v1/vendors/{vendor_id}/validate")
        assert val_resp.status_code == 200

        # Verify DB still has SUBMITTED
        vendor_in_db = test_db_session.get(Vendor, vendor_id)
        assert vendor_in_db.status == "SUBMITTED"

    def test_transactional_rollback_on_persistence_failure(
        self, client: TestClient, test_db_session: Session, valid_vendor_payload: dict
    ):
        """If database commit fails during decision execution, vendor status is not mutated."""
        create_resp = client.post("/api/v1/vendors", json=valid_vendor_payload)
        vendor_id = create_resp.json()["id"]

        with patch.object(Session, "commit", side_effect=RuntimeError("Simulated DB lock")):
            resp = client.post(f"/api/v1/vendors/{vendor_id}/decide")
            assert resp.status_code == 500

        # Ensure vendor status remains SUBMITTED
        vendor_in_db = test_db_session.get(Vendor, vendor_id)
        assert vendor_in_db.status == "SUBMITTED"
        # Ensure no decision record committed
        decisions = test_db_session.query(VendorDecision).filter_by(vendor_id=vendor_id).all()
        assert len(decisions) == 0

    def test_no_sensitive_banking_numbers_in_decision_payloads(
        self, client: TestClient, valid_vendor_payload: dict
    ):
        """Decision responses must never leak raw banking numbers or ciphertexts."""
        create_resp = client.post("/api/v1/vendors", json=valid_vendor_payload)
        vendor_id = create_resp.json()["id"]

        decide_resp = client.post(f"/api/v1/vendors/{vendor_id}/decide")
        resp_text = decide_resp.text

        # Raw bank account number must never be in response text
        assert "50200012345678" not in resp_text
        # Ciphertext format gAAAAA... must never be in response text
        assert "gAAAAA" not in resp_text
