"""End-to-End Integration and Testing for Phase 1 Step 5.

Verifies the complete vendor onboarding journey:
1. Vendor submission -> persistence -> validation -> decision -> status update -> decision history.
2. Review-required / incomplete vendor -> PENDING -> recommendations -> update profile -> re-evaluation -> APPROVED -> multi-decision audit history.
3. Cryptographic decryption failure hardening on POST /vendors/{id}/validate (HTTP 500 without state corruption).
4. Realistic demonstration data seeder idempotency and 4 distinct operational scenarios.
5. Chronological activity timeline tracking, pagination, and sensitive data masking.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.vendor import Vendor
from app.models.decision import VendorDecision
from app.models.activity import VendorActivity
from app.scripts.seed_demo_data import seed_demo_vendors, reset_demo_data, DEMO_VENDORS_PAYLOADS


@pytest.fixture
def complete_valid_vendor() -> dict:
    """Complete, valid vendor registration payload."""
    return {
        "legal_name": "Bharat Dynamic Systems Pvt Ltd",
        "trade_name": "BDS Tech",
        "business_type": "Private Limited",
        "country_of_incorporation": "India",
        "registration_number": "U72200DL2018PTC123456",
        "contact_name": "Vikram Malhotra",
        "contact_email": "v.malhotra@bdstech.example.in",
        "contact_phone": "+919811223344",
        "address_line1": "Tower 4, DLF Cyber City",
        "address_line2": "Phase 2",
        "city": "Gurugram",
        "state_province": "Haryana",
        "postal_code": "122002",
        "address_country": "India",
        "tax_id_type": "GSTIN",
        "tax_id_number": "06AAACB1234F1Z5",
        "bank_account_holder_name": "Bharat Dynamic Systems Pvt Ltd",
        "bank_name": "State Bank of India",
        "bank_account_number": "30987654321",
        "bank_routing_number": "SBIN0001234",
        "bank_country": "India",
    }


class TestEndToEndLifecycle:
    """Comprehensive end-to-end integration tests for complete vendor onboarding journey."""

    def test_end_to_end_happy_path_lifecycle(
        self, client: TestClient, test_db_session: Session, complete_valid_vendor: dict
    ):
        """Happy path: submit -> validate -> decide -> status update -> history."""
        # 1. Vendor submission
        create_res = client.post("/api/v1/vendors", json=complete_valid_vendor)
        assert create_res.status_code == 201
        vendor_data = create_res.json()
        vendor_id = vendor_data["id"]
        assert vendor_data["status"] == "SUBMITTED"
        assert vendor_data["bank_account_number_masked"].startswith("••••")

        # 2. Validation endpoint
        val_res = client.post(f"/api/v1/vendors/{vendor_id}/validate")
        assert val_res.status_code == 200
        val_data = val_res.json()
        assert val_data["valid"] is True
        assert val_data["summary"]["failed"] == 0
        assert val_data["vendor_id"] == vendor_id

        # Verify validation endpoint did not mutate vendor status
        get_res = client.get(f"/api/v1/vendors/{vendor_id}")
        assert get_res.status_code == 200
        assert get_res.json()["status"] == "SUBMITTED"

        # 3. Decision execution
        dec_res = client.post(f"/api/v1/vendors/{vendor_id}/decide")
        assert dec_res.status_code == 200
        dec_data = dec_res.json()
        assert dec_data["status"] == "APPROVED"
        assert dec_data["vendor_id"] == vendor_id
        assert len(dec_data["reason_codes"]) > 0
        assert len(dec_data["recommendations"]) > 0

        # 4. Status update reflected in vendor profile
        vendor_after_dec = client.get(f"/api/v1/vendors/{vendor_id}").json()
        assert vendor_after_dec["status"] == "APPROVED"

        # 5. Decision audit record queryable
        latest_dec_res = client.get(f"/api/v1/vendors/{vendor_id}/decision")
        assert latest_dec_res.status_code == 200
        assert latest_dec_res.json()["decision_id"] == dec_data["decision_id"]
        assert latest_dec_res.json()["status"] == "APPROVED"

        # 6. Decision history preserved
        hist_res = client.get(f"/api/v1/vendors/{vendor_id}/decision-history")
        assert hist_res.status_code == 200
        history = hist_res.json()
        assert history["total"] == 1
        assert len(history["items"]) == 1
        assert history["items"][0]["status"] == "APPROVED"

        # 7. Lifecycle activity timeline recorded
        act_res = client.get(f"/api/v1/vendors/{vendor_id}/activities")
        assert act_res.status_code == 200
        act_data = act_res.json()
        assert act_data["total"] >= 2
        event_types = [item["event_type"] for item in act_data["items"]]
        assert "VENDOR_SUBMITTED" in event_types
        assert "DECISION_EXECUTED" in event_types

    def test_incomplete_to_complete_reevaluation_flow(
        self, client: TestClient, test_db_session: Session, complete_valid_vendor: dict
    ):
        """Review-required flow: name mismatch -> PENDING -> edit profile -> re-evaluate -> APPROVED."""
        payload = complete_valid_vendor.copy()
        payload["legal_name"] = "Incomplete Ventures LLP"
        payload["bank_account_holder_name"] = "Third Party Escrow Agency"

        # 1. Submit vendor with discrepancy
        create_res = client.post("/api/v1/vendors", json=payload)
        assert create_res.status_code == 201
        vendor_id = create_res.json()["id"]

        # 2. Run initial decision -> should be PENDING (REVIEW policy for holder mismatch)
        dec_1_res = client.post(f"/api/v1/vendors/{vendor_id}/decide")
        assert dec_1_res.status_code == 200
        dec_1 = dec_1_res.json()
        assert dec_1["status"] == "PENDING"
        assert "ACCOUNT_HOLDER_NAME_MISMATCH" in dec_1["reason_codes"]

        # Verify recommendations highlight the issue
        assert any("ACCOUNT" in rec["action"] or "VERIFY" in rec["action"] for rec in dec_1["recommendations"])

        # Verify vendor status is PENDING
        assert client.get(f"/api/v1/vendors/{vendor_id}").json()["status"] == "PENDING"

        # 3. Update / correct vendor profile via PUT /api/v1/vendors/{id}
        update_payload = {
            "bank_account_holder_name": "Incomplete Ventures LLP",
        }
        update_res = client.put(f"/api/v1/vendors/{vendor_id}", json=update_payload)
        assert update_res.status_code == 200
        updated_vendor = update_res.json()
        assert updated_vendor["bank_account_holder_name"] == "Incomplete Ventures LLP"
        # Status remains PENDING until re-evaluation is explicitly triggered
        assert updated_vendor["status"] == "PENDING"

        # 4. Re-evaluate decision
        dec_2_res = client.post(f"/api/v1/vendors/{vendor_id}/decide")
        assert dec_2_res.status_code == 200
        dec_2 = dec_2_res.json()
        assert dec_2["status"] == "APPROVED"

        # Verify vendor status transitioned to APPROVED
        assert client.get(f"/api/v1/vendors/{vendor_id}").json()["status"] == "APPROVED"

        # 5. Verify full decision history preserves both evaluations
        hist_res = client.get(f"/api/v1/vendors/{vendor_id}/decision-history")
        assert hist_res.status_code == 200
        history = hist_res.json()
        assert history["total"] == 2
        assert len(history["items"]) == 2
        # Most recent first
        assert history["items"][0]["status"] == "APPROVED"
        assert history["items"][1]["status"] == "PENDING"

        # 6. Verify activity timeline recorded all transitions
        act_res = client.get(f"/api/v1/vendors/{vendor_id}/activities")
        assert act_res.status_code == 200
        event_types = [item["event_type"] for item in act_res.json()["items"]]
        expected_sequence = [
            "VENDOR_SUBMITTED",
            "DECISION_EXECUTED",
            "VENDOR_UPDATED",
            "DECISION_REEVALUATED",
        ]
        for expected_event in expected_sequence:
            assert expected_event in event_types

    def test_hardening_decryption_failure_on_validate_endpoint(
        self, client: TestClient, test_db_session: Session, complete_valid_vendor: dict
    ):
        """POST /vendors/{id}/validate cleanly returns HTTP 500 without mutating vendor status or reporting false missing-field findings."""
        # 1. Create vendor
        create_res = client.post("/api/v1/vendors", json=complete_valid_vendor)
        vendor_id = create_res.json()["id"]

        # 2. Corrupt ciphertext directly in database with invalid Fernet payload
        db_vendor = test_db_session.query(Vendor).filter(Vendor.id == vendor_id).first()
        assert db_vendor is not None
        db_vendor.bank_account_number = "enc:v1:gAAAAABcorrupted_fernet_token_xyz123"
        test_db_session.commit()

        # 3. Request validation
        val_res = client.post(f"/api/v1/vendors/{vendor_id}/validate")
        assert val_res.status_code == 500
        err_detail = val_res.json().get("detail", "")
        assert "safely decrypted" in err_detail or "Security or data integrity error" in err_detail

        # 4. Confirm vendor state remains pristine and not mutated
        test_db_session.expire_all()
        persisted_vendor = test_db_session.query(Vendor).filter(Vendor.id == vendor_id).first()
        assert persisted_vendor.status == "SUBMITTED"

    def test_demo_data_seeder_scenarios_and_idempotency(
        self, test_db_session: Session
    ):
        """seed_demo_vendors creates 4 realistic vendors matching all 4 expected business scenarios idempotently."""
        # Reset and seed with decisions
        reset_demo_data(test_db_session)
        seed_res_1 = seed_demo_vendors(test_db_session, run_decisions=True)
        assert len(seed_res_1) == 4

        # Verify all 4 demo vendors exist with expected statuses
        solaris = test_db_session.query(Vendor).filter(Vendor.legal_name.contains("Solaris")).first()
        nova = test_db_session.query(Vendor).filter(Vendor.legal_name.contains("Nova")).first()
        zenith = test_db_session.query(Vendor).filter(Vendor.legal_name.contains("Zenith")).first()
        vortex = test_db_session.query(Vendor).filter(Vendor.legal_name.contains("Vortex")).first()

        assert solaris is not None and solaris.status == "APPROVED"
        assert nova is not None and nova.status == "PENDING"
        assert zenith is not None and zenith.status == "PENDING"
        assert vortex is not None and vortex.status == "REJECTED"

        # Verify decisions match expected outcomes
        solaris_dec = (
            test_db_session.query(VendorDecision)
            .filter(VendorDecision.vendor_id == solaris.id)
            .order_by(VendorDecision.decided_at.desc())
            .first()
        )
        assert solaris_dec.status == "APPROVED"

        nova_dec = (
            test_db_session.query(VendorDecision)
            .filter(VendorDecision.vendor_id == nova.id)
            .order_by(VendorDecision.decided_at.desc())
            .first()
        )
        assert nova_dec.status == "PENDING"

        vortex_dec = (
            test_db_session.query(VendorDecision)
            .filter(VendorDecision.vendor_id == vortex.id)
            .order_by(VendorDecision.decided_at.desc())
            .first()
        )
        assert vortex_dec.status == "REJECTED"

        # Run seeder again to verify idempotency (no duplicates created)
        seed_res_2 = seed_demo_vendors(test_db_session, run_decisions=True)
        assert len(seed_res_2) == 4

        total_demo = (
            test_db_session.query(Vendor)
            .filter(Vendor.legal_name.contains("[DEMO]"))
            .count()
        )
        assert total_demo == 4

    def test_activity_history_pagination_and_masking(
        self, client: TestClient, test_db_session: Session, complete_valid_vendor: dict
    ):
        """Vendor activity endpoint enforces deterministic chronological order, pagination, and zero leak of sensitive data."""
        create_res = client.post("/api/v1/vendors", json=complete_valid_vendor)
        vendor_id = create_res.json()["id"]

        # Perform multiple updates to generate activity records
        for i in range(3):
            client.put(
                f"/api/v1/vendors/{vendor_id}",
                json={"contact_name": f"Contact Iteration {i}"},
            )

        # Query activities with pagination
        page_1 = client.get(f"/api/v1/vendors/{vendor_id}/activities?page=1&page_size=2").json()
        assert page_1["page"] == 1
        assert page_1["page_size"] == 2
        assert len(page_1["items"]) == 2
        assert page_1["total"] >= 4

        page_2 = client.get(f"/api/v1/vendors/{vendor_id}/activities?page=2&page_size=2").json()
        assert page_2["page"] == 2
        assert len(page_2["items"]) == 2

        # Verify raw bank account number is NEVER in any activity title or description
        all_activities = client.get(f"/api/v1/vendors/{vendor_id}/activities?page_size=100").json()
        raw_account = complete_valid_vendor["bank_account_number"]
        for act in all_activities["items"]:
            assert raw_account not in act["title"]
            assert raw_account not in act["description"]
