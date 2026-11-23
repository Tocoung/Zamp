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
# Scenario 11: Database Persistence Across Session Expiration
# ============================================================================

def test_scenario_11_database_persistence_across_session_expiration(db: Session):
    """Process runs, stage results, and decisions persist cleanly across DB session reload (database persistence test)."""
    v = seed_test_vendor(db)
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "gst.pdf",
        {"gstin": v.tax_id_number, "legal_name": v.legal_name},
    )

    run = onboarding_orchestrator.process_vendor_onboarding(db, v.id)
    run_id = run.id

    # Commit and close session to simulate fresh database connection reload
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


# ============================================================================
# Section 1: Classification Eligibility Tests
# ============================================================================

def test_classification_eligibility_declared_tax_predicted_unknown(db: Session):
    """Declared TAX_CERTIFICATE with predicted UNKNOWN does not satisfy mandatory requirement."""
    v = seed_test_vendor(db)
    # Declared TAX_CERTIFICATE, but classifier returned UNKNOWN
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "unclear_tax.pdf",
        {"raw_text": "Sample text without tax keywords"},
        classification_status="LOW_CONFIDENCE",
        predicted_category="UNKNOWN",
    )
    # Valid COI and Bank Proof
    seed_doc_with_extraction(
        db, v.id, "CERTIFICATE_OF_INCORPORATION", "coi.pdf",
        {"cin": v.registration_number, "company_name": v.legal_name},
    )
    seed_doc_with_extraction(
        db, v.id, "BANK_PROOF", "bank.pdf",
        {"account_number": "987123456789", "ifsc": v.bank_routing_number},
    )

    run = onboarding_orchestrator.process_vendor_onboarding(db, v.id)

    # Must report MISSING_TAX_DOCUMENT because inconclusive classification cannot satisfy requirement
    assert run.decision_status == "PENDING"
    assert "MISSING_TAX_DOCUMENT" in run.decision_reasons
    # Document breakdown must flag that the document was ineligible for verification
    tax_item = next(d for d in run.document_breakdown if d.file_name == "unclear_tax.pdf")
    assert tax_item.eligible_for_verification is False
    assert tax_item.declared_category == "TAX_CERTIFICATE"
    assert tax_item.predicted_category == "UNKNOWN"
    assert tax_item.ineligible_reason_code == "LOW_CONFIDENCE_DOCUMENT_EVIDENCE"


def test_classification_eligibility_declared_bank_predicted_other(db: Session):
    """Declared BANK_PROOF with predicted OTHER does not satisfy mandatory bank requirement."""
    v = seed_test_vendor(db)
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "gst.pdf",
        {"gstin": v.tax_id_number, "legal_name": v.legal_name},
    )
    seed_doc_with_extraction(
        db, v.id, "CERTIFICATE_OF_INCORPORATION", "coi.pdf",
        {"cin": v.registration_number, "company_name": v.legal_name},
    )
    # Declared BANK_PROOF, but classified as OTHER
    seed_doc_with_extraction(
        db, v.id, "BANK_PROOF", "invoice_misc.pdf",
        {"amount": "1000"},
        classification_status="CLASSIFIED",
        predicted_category="OTHER",
    )

    run = onboarding_orchestrator.process_vendor_onboarding(db, v.id)

    assert run.decision_status == "PENDING"
    assert "MISSING_BANK_DOCUMENT" in run.decision_reasons
    bank_item = next(d for d in run.document_breakdown if d.file_name == "invoice_misc.pdf")
    assert bank_item.eligible_for_verification is False
    assert bank_item.ineligible_reason_code == "UNSUPPORTED_DOCUMENT_EVIDENCE"


def test_classification_eligibility_confident_matching(db: Session):
    """Confident matching classification qualifies document for verification and satisfies requirement."""
    v = seed_test_vendor(db)
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "valid_gst.pdf",
        {"gstin": v.tax_id_number, "legal_name": v.legal_name},
        classification_status="CLASSIFIED",
        predicted_category="TAX_CERTIFICATE",
    )
    seed_doc_with_extraction(
        db, v.id, "CERTIFICATE_OF_INCORPORATION", "valid_coi.pdf",
        {"cin": v.registration_number, "company_name": v.legal_name},
        classification_status="CLASSIFIED",
        predicted_category="CERTIFICATE_OF_INCORPORATION",
    )
    seed_doc_with_extraction(
        db, v.id, "BANK_PROOF", "valid_bank.pdf",
        {"account_number": "987123456789", "ifsc": v.bank_routing_number},
        classification_status="CLASSIFIED",
        predicted_category="BANK_PROOF",
    )

    run = onboarding_orchestrator.process_vendor_onboarding(db, v.id)

    assert run.status == "COMPLETED"
    assert run.decision_status == "APPROVED"
    assert run.total_documents == 3
    assert run.successful_documents == 3
    for d in run.document_breakdown:
        assert d.eligible_for_verification is True
        assert d.ineligible_reason_code is None


def test_classification_eligibility_conflicting_categories(db: Session):
    """Declared category conflicting with predicted category generates DOCUMENT_CLASSIFICATION_MISMATCH."""
    v = seed_test_vendor(db)
    # Declared as TAX_CERTIFICATE, but classified as BANK_PROOF
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "cheque_as_tax.pdf",
        {"account_number": "987123456789"},
        classification_status="CLASSIFIED",
        predicted_category="BANK_PROOF",
    )

    run = onboarding_orchestrator.process_vendor_onboarding(db, v.id)

    assert run.decision_status == "PENDING"
    assert "DOCUMENT_CLASSIFICATION_MISMATCH" in run.decision_reasons
    doc_item = run.document_breakdown[0]
    assert doc_item.eligible_for_verification is False
    assert doc_item.ineligible_reason_code == "DOCUMENT_CLASSIFICATION_MISMATCH"


def test_classification_eligibility_failure(db: Session):
    """Failed classification execution is safely handled and marked ineligible without crash."""
    v = seed_test_vendor(db)
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "unparseable.pdf",
        {},
        classification_status="FAILED",
        predicted_category=None,
    )

    run = onboarding_orchestrator.process_vendor_onboarding(db, v.id)

    assert run.decision_status == "PENDING"
    doc_item = run.document_breakdown[0]
    assert doc_item.eligible_for_verification is False
    assert doc_item.classification_status == "FAILED"


# ============================================================================
# Section 2: Consistent Evidence-Eligibility Boundary Tests
# ============================================================================

def test_evidence_boundary_ineligible_doc_cannot_create_false_matches_or_discrepancies(db: Session):
    """Ineligible documents (classification conflict or failed extraction) cannot contribute evidence."""
    v = seed_test_vendor(db)

    # Document declared as TAX_CERTIFICATE but content has conflicting classification (BANK_PROOF)
    # and has a deliberately wrong tax number
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "invalid_tax_doc.pdf",
        {"gstin": "WRONG_GSTIN_12345"},
        classification_status="CLASSIFIED",
        predicted_category="BANK_PROOF",
    )

    run = onboarding_orchestrator.process_vendor_onboarding(db, v.id)

    # It must NOT create a confirmed GSTIN discrepancy against vendor profile,
    # because the document was ineligible for tax evidence!
    cross_verif = run.stage_results.get("7_cross_verification", {})
    assert cross_verif.get("confirmed_discrepancies", 0) == 0
    # It routes to PENDING because of missing valid tax document and classification mismatch
    assert run.decision_status == "PENDING"


# ============================================================================
# Section 3: Retry & Idempotency Correctness Tests
# ============================================================================

def test_idempotency_successful_run_cached_no_duplicate_decisions(db: Session):
    """Unchanged successful inputs reuse the cached run and create zero new decisions."""
    v = seed_test_vendor(db)
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "gst.pdf",
        {"gstin": v.tax_id_number, "legal_name": v.legal_name},
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
    assert run1.status == "COMPLETED"
    d_count_1 = db.query(VendorDecision).filter(VendorDecision.vendor_id == v.id).count()

    # Repeat without force
    run2 = onboarding_orchestrator.process_vendor_onboarding(db, v.id, force_reprocess=False)
    d_count_2 = db.query(VendorDecision).filter(VendorDecision.vendor_id == v.id).count()

    assert run1.id == run2.id
    assert d_count_1 == d_count_2


def test_retry_partial_failure_not_cached(db: Session):
    """A PARTIAL_FAILURE run is NOT cached; retrying without force executes a fresh run."""
    v = seed_test_vendor(db)
    # Seed with an extraction failure
    doc, ext = seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "gst.pdf",
        {},
        extraction_status="FAILED",
        limitation_code="CORRUPTED_DOCUMENT",
    )

    run1 = onboarding_orchestrator.process_vendor_onboarding(db, v.id)
    assert run1.status == "PARTIAL_FAILURE"

    # Now simulate recovery by updating extraction record to completed
    ext.status = "COMPLETED"
    ext.limitation_code = None
    ext.fields = {
        "gstin": {"field_name": "gstin", "value": v.tax_id_number, "confidence": 0.95, "status": "EXTRACTED"},
        "legal_name": {"field_name": "legal_name", "value": v.legal_name, "confidence": 0.95, "status": "EXTRACTED"},
    }
    db.commit()

    # Retry without force_reprocess: MUST re-execute because run1 was PARTIAL_FAILURE
    run2 = onboarding_orchestrator.process_vendor_onboarding(db, v.id, force_reprocess=False)
    assert run2.id != run1.id
    assert run2.status == "COMPLETED"


def test_retry_failed_run_not_cached(db: Session):
    """A FAILED run does not block retry and re-executes cleanly."""
    v = seed_test_vendor(db)
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "gst.pdf",
        {"gstin": v.tax_id_number, "legal_name": v.legal_name},
    )

    # Manually insert a FAILED process run
    failed_run = OnboardingProcessRun(
        vendor_id=v.id,
        status="FAILED",
        trigger_source="MANUAL",
        documents_snapshot={},
        stage_results={},
        document_breakdown=[],
        findings_summary={},
        error_message="Simulated technical crash",
    )
    db.add(failed_run)
    db.commit()

    # Retry without force_reprocess must execute freshly and not return the failed run
    run = onboarding_orchestrator.process_vendor_onboarding(db, v.id, force_reprocess=False)
    assert run.id != failed_run.id
    assert run.status == "COMPLETED"


def test_cache_invalidation_document_checksum_changed(db: Session):
    """Changing document checksum invalidates cache and triggers new execution."""
    v = seed_test_vendor(db)
    doc, ext = seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "gst.pdf",
        {"gstin": v.tax_id_number, "legal_name": v.legal_name},
    )

    run1 = onboarding_orchestrator.process_vendor_onboarding(db, v.id)
    assert run1.status == "COMPLETED"

    # Mutate checksum on document (simulating re-upload)
    doc.sha256_checksum = "b" * 64
    db.commit()

    run2 = onboarding_orchestrator.process_vendor_onboarding(db, v.id, force_reprocess=False)
    assert run2.id != run1.id


def test_cache_invalidation_document_category_changed(db: Session):
    """Changing document category invalidates cache and triggers new execution."""
    v = seed_test_vendor(db)
    doc, ext = seed_doc_with_extraction(
        db, v.id, "OTHER", "doc.pdf",
        {"note": "general text"},
    )

    run1 = onboarding_orchestrator.process_vendor_onboarding(db, v.id)

    # Update category
    doc.document_category = "TAX_CERTIFICATE"
    db.commit()

    run2 = onboarding_orchestrator.process_vendor_onboarding(db, v.id, force_reprocess=False)
    assert run2.id != run1.id


def test_cache_invalidation_profile_field_changed(db: Session):
    """Modifying vendor profile fields invalidates cache."""
    v = seed_test_vendor(db)
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "gst.pdf",
        {"gstin": v.tax_id_number, "legal_name": v.legal_name},
    )

    run1 = onboarding_orchestrator.process_vendor_onboarding(db, v.id)

    # Update profile
    v.legal_name = "Acme Global Solutions Private Limited"
    v.updated_at = datetime.now(timezone.utc)
    db.commit()

    run2 = onboarding_orchestrator.process_vendor_onboarding(db, v.id, force_reprocess=False)
    assert run2.id != run1.id


def test_force_reprocess_creates_new_traceable_run(db: Session):
    """Explicit force_reprocess always generates a new run with trigger_source REPROCESS."""
    v = seed_test_vendor(db)
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "gst.pdf",
        {"gstin": v.tax_id_number, "legal_name": v.legal_name},
    )

    run1 = onboarding_orchestrator.process_vendor_onboarding(db, v.id)
    run2 = onboarding_orchestrator.process_vendor_onboarding(db, v.id, force_reprocess=True)

    assert run2.id != run1.id
    assert run2.trigger_source == "REPROCESS"


# ============================================================================
# Section 4: Database Model Registration & Foreign Key Resolution
# ============================================================================

def test_database_model_registration_onboarding_process_run():
    """Verifies OnboardingProcessRun table, columns, and foreign keys are explicitly registered in Base.metadata."""
    from app.db.base import Base
    from app.models.onboarding_process import OnboardingProcessRun

    table = Base.metadata.tables.get("onboarding_process_runs")
    assert table is not None, "Table 'onboarding_process_runs' must be registered in Base.metadata"

    # Verify column existence
    col_names = {c.name for c in table.columns}
    required_cols = {
        "id", "vendor_id", "status", "trigger_source", "total_documents",
        "successful_documents", "failed_documents", "verification_run_id",
        "decision_id", "stage_results", "document_breakdown", "documents_snapshot",
        "findings_summary", "error_message", "created_at", "completed_at",
    }
    assert required_cols.issubset(col_names)

    # Verify foreign keys
    fks = {fk.target_fullname for fk in table.foreign_keys}
    assert "vendors.id" in fks
    assert "vendor_verifications.id" in fks
    assert "vendor_decisions.id" in fks


# ============================================================================
# Section 6: Document Lifecycle & Supersession Tests
# ============================================================================

def test_multiple_active_documents_both_evaluated(db: Session):
    """Multiple active documents of the same category without supersession are both evaluated."""
    v = seed_test_vendor(db)
    # First GST
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "gst_v1.pdf",
        {"gstin": v.tax_id_number, "legal_name": v.legal_name},
    )
    # Second GST with contradictory GSTIN
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "gst_v2.pdf",
        {"gstin": "06AAAAA9999A1Z1", "legal_name": v.legal_name},
    )

    run = onboarding_orchestrator.process_vendor_onboarding(db, v.id)

    assert run.total_documents == 2
    assert len(run.document_breakdown) == 2
    # Because both remain active and conflict, vendor routes to PENDING for review
    assert run.decision_status == "PENDING"
    assert "DOCUMENT_VERIFICATION_DISCREPANCY" in run.decision_reasons


def test_superseded_document_lifecycle(db: Session):
    """A document marked upload_status='SUPERSEDED' is excluded from active onboarding evaluation."""
    v = seed_test_vendor(db)
    # Valid active GST
    seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "gst_active.pdf",
        {"gstin": v.tax_id_number, "legal_name": v.legal_name},
    )
    # Superseded older conflicting GST
    old_doc, old_ext = seed_doc_with_extraction(
        db, v.id, "TAX_CERTIFICATE", "gst_superseded.pdf",
        {"gstin": "WRONG_GSTIN_OLD", "legal_name": v.legal_name},
    )
    old_doc.upload_status = "SUPERSEDED"
    db.commit()

    run = onboarding_orchestrator.process_vendor_onboarding(db, v.id)

    # Only active document should be evaluated
    assert run.total_documents == 1
    assert run.document_breakdown[0].file_name == "gst_active.pdf"
    # Old document does not contaminate the active run
    assert not any(d.file_name == "gst_superseded.pdf" for d in run.document_breakdown)


# ============================================================================
# Section 8: Error Sanitization & Zero-Leakage Privacy Tests
# ============================================================================

def test_error_sanitization_zero_internal_path_leakage(db: Session):
    """Critical exception in pipeline must sanitize error message without leaking paths or secrets."""
    v = seed_test_vendor(db)

    # Force a failure by providing an invalid vendor ID directly to an internal stage
    from unittest.mock import patch

    with patch.object(onboarding_orchestrator.classification_service, "classify_vendor_document", side_effect=ValueError("Sensitive database /var/lib/secret/key.pem internal error")):
        # Seed doc to trigger classification
        seed_doc_with_extraction(
            db, v.id, "TAX_CERTIFICATE", "doc.pdf",
            {"gstin": v.tax_id_number},
        )
        # Should catch gracefully and record safe error
        run = onboarding_orchestrator.process_vendor_onboarding(db, v.id, force_reprocess=True)

        assert run.status in ("PARTIAL_FAILURE", "COMPLETED", "FAILED")
        run_str = str(run.model_dump())
        assert "/var/lib/secret/key.pem" not in run_str, "Sensitive file path leaked in run response!"


# ============================================================================
# Section 7: Synthetic File Intake & Actual Pipeline Processing Test
# ============================================================================

def test_synthetic_file_intake_and_orchestrator_pipeline(db: Session):
    """Tests the full orchestrator path starting from actual synthetic file upload."""
    from app.services.document_service import document_service

    v = seed_test_vendor(db)

    # Synthetic text file payload representing a statutory tax certificate
    tax_content = b"%PDF-1.4\n1 0 obj\n<< /Title (GST Certificate) >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"

    doc = document_service.upload_vendor_document(
        db=db,
        vendor_id=v.id,
        filename="synthetic_gst.pdf",
        declared_content_type="application/pdf",
        content=tax_content,
        category="TAX_CERTIFICATE",
    )
    assert doc.id is not None
    assert doc.upload_status == "UPLOADED"

    # Execute onboarding process with actual uploaded file
    run = onboarding_orchestrator.process_vendor_onboarding(db, v.id, force_reprocess=True)

    assert run.vendor_id == v.id
    assert run.total_documents >= 1
    assert len(run.document_breakdown) >= 1
    assert run.document_breakdown[0].document_id == str(doc.id)
    assert run.stage_results["2_document_intake"]["status"] == "COMPLETED"

