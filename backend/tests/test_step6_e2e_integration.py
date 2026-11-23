"""End-to-End integration tests for Phase 2 Step 6.

Validates the complete 8-stage onboarding workflow, evidence-aware decisioning,
idempotency, retry, error tolerance, privacy protection, and API endpoints.
"""

import uuid
from typing import Tuple, Dict, Any, List
import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.models.vendor import Vendor
from app.models.document import VendorDocument
from app.models.classification import DocumentClassification
from app.models.extraction import DocumentExtraction
from app.models.decision import VendorDecision
from app.models.activity import VendorActivity
from app.models.onboarding_process import OnboardingProcessRun
from app.schemas.extraction import ExtractedField, FieldStatus, ExtractionStatus
from app.services.onboarding_orchestrator_service import onboarding_orchestrator
from app.services.decision_service import DecisionService
from app.core.security import encrypt_account_number
from app.main import app


@pytest.fixture
def db(test_db_session: Session) -> Session:
    """Fixture alias providing test_db_session."""
    return test_db_session


def seed_test_vendor(
    db: Session,
    legal_name: str = "Acme Technologies Private Limited",
    gstin: str = "27AAAAA0000A1Z5",
    cin: str = "U72200MH2020PTC123456",
    account_holder: str = "Acme Technologies Private Limited",
    account_number: str = "987123456789",
    ifsc: str = "HDFC0000123",
    status: str = "DRAFT",
    address_line1: str = "Plot 42, Sector 18, Road No. 4",
    city: str = "Gurugram",
    state: str = "Haryana",
    postal_code: str = "122001",
) -> Vendor:
    """Helper to seed a vendor with encrypted banking details."""
    v = Vendor(
        id=str(uuid.uuid4()),
        legal_name=legal_name,
        trade_name="Acme Tech",
        business_type="PRIVATE_LIMITED",
        country_of_incorporation="India",
        registration_number=cin,
        contact_name="John Doe",
        contact_email="john@acme.com",
        contact_phone="+919876543210",
        address_line1=address_line1,
        address_line2="Cyber City",
        city=city,
        state_province=state,
        postal_code=postal_code,
        address_country="India",
        tax_id_type="GSTIN",
        tax_id_number=gstin,
        bank_account_holder_name=account_holder,
        bank_name="HDFC Bank",
        bank_account_number=encrypt_account_number(account_number),
        bank_routing_number=ifsc,
        bank_country="India",
        status=status,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def seed_doc_with_extraction(
    db: Session,
    vendor_id: str,
    category: str,
    filename: str,
    fields: dict,
    extraction_status: str = "COMPLETED",
    classification_status: str = "CLASSIFIED",
    predicted_category: str = None,
    limitation_code: str = None,
    average_confidence: float = 0.95,
) -> Tuple[VendorDocument, DocumentExtraction]:
    """Helper to seed a document with classification and extraction."""
    from typing import Tuple
    doc = VendorDocument(
        id=str(uuid.uuid4()),
        vendor_id=vendor_id,
        original_filename=filename,
        sanitized_filename=filename,
        document_category=category,
        mime_type="application/pdf",
        file_extension="pdf",
        file_size_bytes=1024,
        storage_identifier=f"test/{filename}",
        sha256_checksum="a" * 64,
        upload_status="PROCESSED",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    clf = DocumentClassification(
        id=str(uuid.uuid4()),
        document_id=doc.id,
        vendor_id=vendor_id,
        predicted_category=predicted_category or category,
        status=classification_status,
        confidence_score=0.95,
        evidence={"summary": "Seed classification"},
    )
    db.add(clf)
    db.commit()
    db.refresh(clf)

    raw_fields = {}
    for k, v in fields.items():
        if isinstance(v, tuple):
            val, conf = v
        else:
            val, conf = v, 0.95
        raw_fields[k] = ExtractedField(
            field_name=k,
            value=val,
            quality_score=conf,
            confidence=conf,
            status=FieldStatus.EXTRACTED,
        ).model_dump()

    ext = DocumentExtraction(
        id=str(uuid.uuid4()),
        document_id=doc.id,
        vendor_id=vendor_id,
        document_category_used=category,
        status=extraction_status,
        extracted_fields_count=len(raw_fields),
        limitation_code=limitation_code,
        fields=raw_fields,
    )
    db.add(ext)
    db.commit()
    db.refresh(ext)
    return doc, ext


# ============================================================================
# Scenario 1: Complete Matching Submission (Digital PDF)
# ============================================================================

def test_scenario_1_complete_matching_submission(db: Session):
    """Clean vendor with matching GST, Incorporation, and Bank documents should be APPROVED."""
    v = seed_test_vendor(db)

    # 1. GST Certificate
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "gst_cert.pdf",
        {
            "gstin": v.tax_id_number,
            "legal_name": v.legal_name,
            "address": v.address_line1,
        }
    )
    # 2. Certificate of Incorporation
    seed_doc_with_extraction(
        db, v.id, "CERTIFICATE_OF_INCORPORATION", "coi.pdf",
        {
            "cin": v.registration_number,
            "company_name": v.legal_name,
        }
    )
    # 3. Bank Proof
    seed_doc_with_extraction(
        db, v.id, "BANK_PROOF", "cheque.pdf",
        {
            "account_holder_name": v.bank_account_holder_name,
            "account_number": "987123456789",
            "ifsc": v.bank_routing_number,
            "bank_name": v.bank_name,
        }
    )

    run = onboarding_orchestrator.process_vendor_onboarding(db, v.id)

    assert run.status == "COMPLETED"
    assert run.decision_status == "APPROVED"
    assert run.total_documents == 3
    assert run.successful_documents == 3
    assert run.failed_documents == 0
    assert run.stage_results["1_registration"]["status"] == "COMPLETED"
    assert run.stage_results["7_cross_verification"]["status"] == "COMPLETED"
    assert run.stage_results["8_decision"]["decision_status"] == "APPROVED"

    # Verify vendor record was updated
    db.refresh(v)
    assert v.status == "APPROVED"

    # Verify pipeline activity logged
    activity = db.query(VendorActivity).filter(
        VendorActivity.vendor_id == v.id,
        VendorActivity.event_type == "ONBOARDING_PIPELINE_EXECUTED",
    ).first()
    assert activity is not None
    assert activity.status == "APPROVED"


# ============================================================================
# Scenario 2: Scanned OCR PDF with High Confidence
# ============================================================================

def test_scenario_2_scanned_ocr_pdf_matches(db: Session):
    """Scanned PDF with clean OCR extraction should pass verification."""
    v = seed_test_vendor(db)
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "scanned_gst.pdf",
        {"gstin": (v.tax_id_number, 0.92), "legal_name": (v.legal_name, 0.90)},
        average_confidence=0.91,
    )
    seed_doc_with_extraction(
        db, v.id, "CERTIFICATE_OF_INCORPORATION", "scanned_coi.pdf",
        {"cin": (v.registration_number, 0.94), "company_name": (v.legal_name, 0.91)},
        average_confidence=0.92,
    )
    seed_doc_with_extraction(
        db, v.id, "BANK_PROOF", "scanned_cheque.pdf",
        {
            "account_holder_name": (v.bank_account_holder_name, 0.93),
            "account_number": ("987123456789", 0.95),
            "ifsc": (v.bank_routing_number, 0.91),
        },
        average_confidence=0.93,
    )

    run = onboarding_orchestrator.process_vendor_onboarding(db, v.id)
    assert run.status == "COMPLETED"
    assert run.decision_status == "APPROVED"


# ============================================================================
# Scenario 3: Multiple Documents of the Same Type
# ============================================================================

def test_scenario_3_multiple_documents_same_type(db: Session):
    """Multiple documents of the same category are all retained and evaluated deterministically."""
    v = seed_test_vendor(db)

    # Two bank proofs
    seed_doc_with_extraction(
        db, v.id, "BANK_PROOF", "bank_statement.pdf",
        {"account_number": "987123456789", "ifsc": v.bank_routing_number},
    )
    seed_doc_with_extraction(
        db, v.id, "BANK_PROOF", "cancelled_cheque.pdf",
        {"account_number": "987123456789", "ifsc": v.bank_routing_number},
    )
    # Plus required docs
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "gst.pdf",
        {"gstin": v.tax_id_number, "legal_name": v.legal_name},
    )
    seed_doc_with_extraction(
        db, v.id, "CERTIFICATE_OF_INCORPORATION", "coi.pdf",
        {"cin": v.registration_number, "company_name": v.legal_name},
    )

    run = onboarding_orchestrator.process_vendor_onboarding(db, v.id)
    assert run.status == "COMPLETED"
    assert run.total_documents == 4
    assert len(run.document_breakdown) == 4


# ============================================================================
# Scenario 4: Missing Required Documents
# ============================================================================

def test_scenario_4_missing_required_documents(db: Session):
    """Missing required documents should route to PENDING with explainable reason codes, NEVER REJECTED."""
    v = seed_test_vendor(db)

    # Only upload GST certificate, missing COI and Bank Proof
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "gst.pdf",
        {"gstin": v.tax_id_number, "legal_name": v.legal_name},
    )

    run = onboarding_orchestrator.process_vendor_onboarding(db, v.id)

    assert run.decision_status == "PENDING"
    assert "MISSING_INCORPORATION_DOCUMENT" in run.decision_reasons or "MISSING_BANK_DOCUMENT" in run.decision_reasons
    # Verify vendor not rejected
    db.refresh(v)
    assert v.status == "PENDING"


# ============================================================================
# Scenario 5: Corrupted or Unsupported Document
# ============================================================================

def test_scenario_5_corrupted_document_handling(db: Session):
    """Corrupted document fails gracefully; other valid documents continue processing."""
    v = seed_test_vendor(db)

    # Valid GST certificate
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "valid_gst.pdf",
        {"gstin": v.tax_id_number, "legal_name": v.legal_name},
    )
    # Corrupted document
    seed_doc_with_extraction(
        db, v.id, "BANK_PROOF", "corrupted.pdf",
        {},
        extraction_status="FAILED",
        limitation_code="CORRUPTED_DOCUMENT",
    )

    run = onboarding_orchestrator.process_vendor_onboarding(db, v.id)

    assert run.status == "PARTIAL_FAILURE"
    assert run.total_documents == 2
    assert run.failed_documents >= 1
    # Should be PENDING due to missing/corrupted bank proof, NEVER rejected
    assert run.decision_status == "PENDING"
    assert "CORRUPTED_DOCUMENT_EVIDENCE" in run.decision_reasons


# ============================================================================
# Scenario 6: Incorrect Document Classification
# ============================================================================

def test_scenario_6_unconfirmed_classification_handling(db: Session):
    """Document classified as UNKNOWN or OTHER is flagged and not used as valid evidence."""
    v = seed_test_vendor(db)

    seed_doc_with_extraction(
        db, v.id, "OTHER", "random_notes.pdf",
        {"note": "Just a general note"},
        classification_status="CLASSIFIED",
        predicted_category="UNKNOWN",
    )

    run = onboarding_orchestrator.process_vendor_onboarding(db, v.id)

    assert run.decision_status == "PENDING"


# ============================================================================
# Scenario 7: Empty or Unreadable Document
# ============================================================================

def test_scenario_7_insufficient_text_document(db: Session):
    """Empty or unreadable document marked INSUFFICIENT_TEXT requires review."""
    v = seed_test_vendor(db)

    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "blank_page.pdf",
        {},
        extraction_status="INSUFFICIENT_TEXT",
        limitation_code="INSUFFICIENT_READABLE_TEXT",
    )

    run = onboarding_orchestrator.process_vendor_onboarding(db, v.id)

    assert run.decision_status == "PENDING"
    assert "UNREADABLE_DOCUMENT_EVIDENCE" in run.decision_reasons


# ============================================================================
# Scenario 8: Low-Confidence Extraction
# ============================================================================

def test_scenario_8_low_confidence_extraction(db: Session):
    """Low-confidence OCR extraction flags potential discrepancy / review, NEVER auto-rejection."""
    v = seed_test_vendor(db)

    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "blurry_gst.pdf",
        {"gstin": (v.tax_id_number, 0.35), "legal_name": (v.legal_name, 0.30)},
        average_confidence=0.32,
    )

    run = onboarding_orchestrator.process_vendor_onboarding(db, v.id)

    assert run.decision_status == "PENDING"
    db.refresh(v)
    assert v.status == "PENDING"


# ============================================================================
# Scenario 9: Conflicting Information Across Documents
# ============================================================================

def test_scenario_9_conflicting_information_discrepancy(db: Session):
    """Confirmed mismatch between documents routes to PENDING with explainable discrepancy code."""
    v = seed_test_vendor(db)

    # GST with wrong GSTIN
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "gst_conflict.pdf",
        {"gstin": "07AAAAA1111A1Z9", "legal_name": v.legal_name},
    )
    # COI with correct name
    seed_doc_with_extraction(
        db, v.id, "CERTIFICATE_OF_INCORPORATION", "coi.pdf",
        {"cin": v.registration_number, "company_name": v.legal_name},
    )
    # Bank Proof with correct account
    seed_doc_with_extraction(
        db, v.id, "BANK_PROOF", "bank.pdf",
        {"account_number": "987123456789", "ifsc": v.bank_routing_number},
    )

    run = onboarding_orchestrator.process_vendor_onboarding(db, v.id)

    assert run.decision_status == "PENDING"
    assert "DOCUMENT_VERIFICATION_DISCREPANCY" in run.decision_reasons
    db.refresh(v)
    assert v.status == "PENDING"


# ============================================================================
# Scenario 10: Corrected Document Re-upload
# ============================================================================

def test_scenario_10_corrected_document_reupload(db: Session):
    """Re-uploading a corrected document reprocesses and updates decision while preserving history."""
    v = seed_test_vendor(db)

    # Initial run with conflicting GSTIN
    doc1, ext1 = seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "gst_wrong.pdf",
        {"gstin": "07AAAAA1111A1Z9", "legal_name": v.legal_name},
    )
    seed_doc_with_extraction(
        db, v.id, "CERTIFICATE_OF_INCORPORATION", "coi.pdf",
        {"cin": v.registration_number, "company_name": v.legal_name},
    )
    seed_doc_with_extraction(
        db, v.id, "BANK_PROOF", "bank.pdf",
        {"account_number": "987123456789", "ifsc": v.bank_routing_number},
    )

    run1 = onboarding_orchestrator.process_vendor_onboarding(db, v.id)
    assert run1.decision_status == "PENDING"

    # Now upload corrected GST certificate
    doc2, ext2 = seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "gst_corrected.pdf",
        {"gstin": v.tax_id_number, "legal_name": v.legal_name},
    )

    run2 = onboarding_orchestrator.process_vendor_onboarding(db, v.id, force_reprocess=True)
    assert run2.id != run1.id

    # Verify both runs exist in history
    history = onboarding_orchestrator.get_history(db, v.id)
    assert history.total_runs == 2
    assert history.runs[0].id == run2.id
    assert history.runs[1].id == run1.id


# ============================================================================
# Scenario 11: Persistence Across Backend Restart
# ============================================================================

def test_scenario_11_persistence_across_restart(db: Session):
    """All process runs, stage results, and decisions persist cleanly in database."""
    v = seed_test_vendor(db)
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "gst.pdf",
        {"gstin": v.tax_id_number, "legal_name": v.legal_name},
    )

    run = onboarding_orchestrator.process_vendor_onboarding(db, v.id)
    run_id = run.id

    # Commit and close session to simulate restart
    db.commit()
    db.expire_all()

    # Query afresh from DB
    persisted_run = db.get(OnboardingProcessRun, run_id)
    assert persisted_run is not None
    assert persisted_run.vendor_id == v.id
    assert persisted_run.status in ("COMPLETED", "PARTIAL_FAILURE")
    assert persisted_run.stage_results is not None
    assert "1_registration" in persisted_run.stage_results


# ============================================================================
# Scenario 12: Zero-Leakage Privacy & Security Audit
# ============================================================================

def test_scenario_12_privacy_zero_leakage(db: Session):
    """Raw sensitive bank account numbers never leak into responses, findings, summaries, or activities."""
    secret_account = "987654321098"
    v = seed_test_vendor(db, account_number=secret_account)

    seed_doc_with_extraction(
        db, v.id, "BANK_PROOF", "cheque.pdf",
        {"account_number": secret_account, "ifsc": v.bank_routing_number},
    )

    run = onboarding_orchestrator.process_vendor_onboarding(db, v.id)

    # Check response serializations
    run_dict = run.model_dump()
    run_str = str(run_dict)
    assert secret_account not in run_str, "Raw bank account leaked in OnboardingProcessRun response!"

    # Check DB activities
    activities = db.query(VendorActivity).filter(VendorActivity.vendor_id == v.id).all()
    for act in activities:
        assert secret_account not in (act.description or ""), "Raw account leaked in activity description!"


# ============================================================================
# Scenario 13: Idempotency & Retry
# ============================================================================

def test_scenario_13_idempotency_and_retry(db: Session):
    """Processing an unchanged vendor twice returns cached run without creating duplicate decisions."""
    v = seed_test_vendor(db)
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "gst.pdf",
        {"gstin": v.tax_id_number, "legal_name": v.legal_name},
    )

    # First execution
    run1 = onboarding_orchestrator.process_vendor_onboarding(db, v.id)
    decisions_count_1 = db.query(VendorDecision).filter(VendorDecision.vendor_id == v.id).count()

    # Second execution without changes
    run2 = onboarding_orchestrator.process_vendor_onboarding(db, v.id, force_reprocess=False)
    decisions_count_2 = db.query(VendorDecision).filter(VendorDecision.vendor_id == v.id).count()

    # Must be the exact same run and zero duplicate decision records created
    assert run1.id == run2.id
    assert decisions_count_1 == decisions_count_2

    # Force reprocess should create a new run
    run3 = onboarding_orchestrator.process_vendor_onboarding(db, v.id, force_reprocess=True)
    assert run3.id != run1.id
    assert run3.trigger_source == "REPROCESS"


# ============================================================================
# Scenario 14: API Endpoints (POST /process-onboarding, GET /latest, GET /history)
# ============================================================================

def test_scenario_14_api_endpoints(db: Session, client: TestClient):
    """FastAPI endpoints for onboarding orchestration operate correctly."""
    v = seed_test_vendor(db)
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "gst.pdf",
        {"gstin": v.tax_id_number, "legal_name": v.legal_name},
    )

    # 1. POST /process-onboarding
    res = client.post(f"/api/v1/vendors/{v.id}/process-onboarding")
    assert res.status_code == 200
    data = res.json()
    assert data["vendor_id"] == v.id
    assert "stage_results" in data
    assert "document_breakdown" in data

    # 2. GET /onboarding-process/latest
    latest_res = client.get(f"/api/v1/vendors/{v.id}/onboarding-process/latest")
    assert latest_res.status_code == 200
    latest_data = latest_res.json()
    assert latest_data["id"] == data["id"]

    # 3. GET /onboarding-process/history
    history_res = client.get(f"/api/v1/vendors/{v.id}/onboarding-process/history")
    assert history_res.status_code == 200
    history_data = history_res.json()
    assert history_data["total_runs"] >= 1
    assert len(history_data["runs"]) >= 1

    # 4. 404 for unknown vendor
    fake_id = str(uuid.uuid4())
    not_found_res = client.post(f"/api/v1/vendors/{fake_id}/process-onboarding")
    assert not_found_res.status_code == 404
