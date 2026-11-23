"""Regression tests for Phase 2 Step 5.1: Verification Engine Correctness, Evidence Eligibility & Privacy Hardening."""

import json
import uuid
from typing import Dict, Tuple
import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.vendor import Vendor
from app.models.document import VendorDocument
from app.models.classification import DocumentClassification
from app.models.extraction import DocumentExtraction
from app.models.verification import VerificationRun, VerificationFinding
from app.models.decision import VendorDecision
from app.schemas.extraction import ExtractedField, FieldStatus
from app.schemas.verification import (
    FindingResult,
    FindingSeverity,
    VerificationRunStatus,
)
from app.services.verification_service import VerificationService
from app.core.security import encrypt_account_number


@pytest.fixture
def db(test_db_session: Session) -> Session:
    """Fixture alias providing test_db_session as db."""
    return test_db_session


def create_step5_vendor(
    db: Session,
    legal_name: str = "Acme Technologies Private Limited",
    gstin: str = "27AABCU9603R1ZM",
    cin: str = "U72900MH2021PTC368421",
    account_holder: str = "Acme Technologies Private Limited",
    account_number: str = "98765432101234",
    ifsc: str = "HDFC0001234",
    status: str = "APPROVED",
) -> Vendor:
    """Creates a vendor with encrypted banking details for Step 5.1 testing."""
    v = Vendor(
        id=str(uuid.uuid4()),
        legal_name=legal_name,
        trade_name="Acme Tech",
        business_type="PRIVATE_LIMITED",
        country_of_incorporation="IN",
        registration_number=cin,
        contact_name="Alice Smith",
        contact_email="alice@acme.com",
        contact_phone="+919876543210",
        address_line1="Plot 42, Sector 18, Road No. 4",
        address_line2="Cyber City",
        city="Gurugram",
        state_province="Haryana",
        postal_code="122001",
        address_country="IN",
        tax_id_type="GSTIN",
        tax_id_number=gstin,
        bank_account_holder_name=account_holder,
        bank_account_number=encrypt_account_number(account_number),
        bank_name="HDFC Bank",
        bank_routing_number=ifsc,
        bank_country="IN",
        status=status,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def seed_doc_with_pipeline(
    db: Session,
    vendor_id: str,
    declared_category: str,
    filename: str,
    fields: Dict[str, dict],
    predicted_category: str = None,
    classification_status: str = "CLASSIFIED",
    classification_confidence: float = 0.95,
    extraction_status: str = "COMPLETED",
    extraction_limitation: str = None,
    created_at: datetime = None,
) -> Tuple[VendorDocument, DocumentClassification, DocumentExtraction]:
    """Seeds a document with its classification and extraction records."""
    ts = created_at or datetime.now(timezone.utc)
    doc = VendorDocument(
        id=str(uuid.uuid4()),
        vendor_id=vendor_id,
        original_filename=filename,
        sanitized_filename=filename,
        document_category=declared_category,
        mime_type="application/pdf",
        file_extension="pdf",
        file_size_bytes=2048,
        storage_identifier=f"test/{filename}",
        sha256_checksum="a" * 64,
        upload_status="PROCESSED",
        created_at=ts,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    clf = DocumentClassification(
        id=str(uuid.uuid4()),
        document_id=doc.id,
        vendor_id=vendor_id,
        predicted_category=predicted_category or declared_category,
        status=classification_status,
        confidence_score=classification_confidence,
        evidence={"summary": f"Classified {filename}"},
        created_at=ts,
    )
    db.add(clf)
    db.commit()
    db.refresh(clf)

    ext = DocumentExtraction(
        id=str(uuid.uuid4()),
        document_id=doc.id,
        vendor_id=vendor_id,
        document_category_used=declared_category,
        status=extraction_status,
        fields=fields,
        extracted_fields_count=len(fields),
        limitation_code=extraction_limitation,
        extraction_engine_version="2.1.0",
        created_at=ts,
    )
    db.add(ext)
    db.commit()
    db.refresh(ext)

    return doc, clf, ext


class TestStep51MultipleDocuments:
    """Tests Section 1: Multiple documents of the same category, retention, and intra-category conflict detection."""

    def test_two_matching_gst_certificates(self, db: Session):
        """1. Two matching GST certificates: both agree with profile and with each other -> all MATCH."""
        vendor = create_step5_vendor(db, gstin="27AABCU9603R1ZM")
        fields = {
            "gstin": {"field_name": "gstin", "extracted_value": "27AABCU9603R1ZM", "status": "EXTRACTED", "confidence": 0.95},
            "legal_entity_name": {"field_name": "legal_entity_name", "extracted_value": "Acme Technologies Private Limited", "status": "EXTRACTED", "confidence": 0.95},
        }

        doc1, _, _ = seed_doc_with_pipeline(db, vendor.id, "TAX_CERTIFICATE", "gst_1.pdf", fields)
        doc2, _, _ = seed_doc_with_pipeline(db, vendor.id, "TAX_CERTIFICATE", "gst_2.pdf", fields)

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        gstin_findings = [f for f in res.findings if "gstin" in f.field_name]
        assert len(gstin_findings) >= 3  # Doc1 vs profile, Doc2 vs profile, Doc1 vs Doc2 intra-check
        assert all(f.result == FindingResult.MATCH for f in gstin_findings)

        # Confirm intra-check finding exists
        intra_finding = next(f for f in gstin_findings if f.field_name == "gstin_intra_conflict")
        assert intra_finding.result == FindingResult.MATCH
        assert len(intra_finding.evidence_sources) == 2
        doc_ids = {s.document_id for s in intra_finding.evidence_sources}
        assert doc1.id in doc_ids and doc2.id in doc_ids

    def test_two_conflicting_gst_certificates(self, db: Session):
        """2. Two GST certificates containing conflicting GSTIN values -> intra-category conflict flagged."""
        vendor = create_step5_vendor(db, gstin="27AABCU9603R1ZM")
        fields1 = {
            "gstin": {"field_name": "gstin", "extracted_value": "27AABCU9603R1ZM", "status": "EXTRACTED", "confidence": 0.95},
        }
        fields2 = {
            "gstin": {"field_name": "gstin", "extracted_value": "29BBBBB1111B2Z6", "status": "EXTRACTED", "confidence": 0.95},
        }

        doc1, _, _ = seed_doc_with_pipeline(db, vendor.id, "TAX_CERTIFICATE", "gst_valid.pdf", fields1)
        doc2, _, _ = seed_doc_with_pipeline(db, vendor.id, "TAX_CERTIFICATE", "gst_conflicting.pdf", fields2)

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        intra = next(f for f in res.findings if f.field_name == "gstin_intra_conflict")
        assert intra.result == FindingResult.CONFIRMED_DISCREPANCY
        assert intra.severity == FindingSeverity.CRITICAL
        assert "Conflicting GST certificates detected" in intra.explanation
        assert doc1.id in {s.document_id for s in intra.evidence_sources}
        assert doc2.id in {s.document_id for s in intra.evidence_sources}

    def test_newer_corrected_document_alongside_older_conflicting_document(self, db: Session):
        """3. A newer corrected document alongside an older conflicting document: older conflict must NOT be erased."""
        vendor = create_step5_vendor(db, gstin="27AABCU9603R1ZM")
        # Older doc with wrong GSTIN
        t_old = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        doc_old, _, _ = seed_doc_with_pipeline(
            db, vendor.id, "TAX_CERTIFICATE", "gst_old_wrong.pdf",
            {"gstin": {"field_name": "gstin", "extracted_value": "99WRONG0000W1Z1", "status": "EXTRACTED", "confidence": 0.95}},
            created_at=t_old,
        )
        # Newer doc with correct GSTIN
        t_new = datetime(2026, 1, 2, 10, 0, 0, tzinfo=timezone.utc)
        doc_new, _, _ = seed_doc_with_pipeline(
            db, vendor.id, "TAX_CERTIFICATE", "gst_new_corrected.pdf",
            {"gstin": {"field_name": "gstin", "extracted_value": "27AABCU9603R1ZM", "status": "EXTRACTED", "confidence": 0.95}},
            created_at=t_new,
        )

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        # Both documents must be represented!
        old_finding = next(f for f in res.findings if any(s.document_id == doc_old.id for s in f.evidence_sources if s.source_type.value == "EXTRACTED_DOCUMENT_FIELD"))
        new_finding = next(f for f in res.findings if any(s.document_id == doc_new.id for s in f.evidence_sources if s.source_type.value == "EXTRACTED_DOCUMENT_FIELD"))

        assert old_finding.result == FindingResult.CONFIRMED_DISCREPANCY
        assert new_finding.result == FindingResult.MATCH

        # The run must NOT be marked cleanly COMPLETED; it must require human review
        assert res.confirmed_discrepancies > 0
        assert res.status == VerificationRunStatus.NEEDS_REVIEW

    def test_multiple_bank_proofs_conflicting(self, db: Session):
        """4. Multiple bank proofs with conflicting account-holder and account number information."""
        vendor = create_step5_vendor(db, account_number="98765432101234", account_holder="Acme Technologies Private Limited")
        b1_fields = {
            "account_number": {"field_name": "account_number", "extracted_value": "98765432101234", "status": "EXTRACTED", "confidence": 0.95},
            "account_holder_name": {"field_name": "account_holder_name", "extracted_value": "Acme Technologies Private Limited", "status": "EXTRACTED", "confidence": 0.95},
        }
        b2_fields = {
            "account_number": {"field_name": "account_number", "extracted_value": "11112222333344", "status": "EXTRACTED", "confidence": 0.95},
            "account_holder_name": {"field_name": "account_holder_name", "extracted_value": "Global Syndicate Ltd", "status": "EXTRACTED", "confidence": 0.95},
        }

        seed_doc_with_pipeline(db, vendor.id, "BANK_PROOF", "cheque.pdf", b1_fields)
        seed_doc_with_pipeline(db, vendor.id, "BANK_PROOF", "bank_statement.pdf", b2_fields)

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        acc_intra = next(f for f in res.findings if f.field_name == "bank_account_intra_conflict")
        assert acc_intra.result == FindingResult.CONFIRMED_DISCREPANCY
        assert "Conflicting bank proofs detected" in acc_intra.explanation

        holder_intra = next(f for f in res.findings if f.field_name == "account_holder_intra_conflict")
        assert holder_intra.result == FindingResult.POTENTIAL_DISCREPANCY
        assert "Conflicting account-holder information" in holder_intra.explanation

    def test_repeated_verification_runs_preserve_distinct_records(self, db: Session):
        """5. Repeated verification runs preserve distinct results without overwriting previous runs."""
        vendor = create_step5_vendor(db)
        seed_doc_with_pipeline(
            db, vendor.id, "TAX_CERTIFICATE", "tax.pdf",
            {"gstin": {"field_name": "gstin", "extracted_value": "27AABCU9603R1ZM", "status": "EXTRACTED", "confidence": 0.95}},
        )

        run1 = VerificationService.run_verification_for_vendor(db, vendor.id)
        run2 = VerificationService.run_verification_for_vendor(db, vendor.id)

        assert run1.id != run2.id
        runs_in_db = list(db.scalars(select(VerificationRun).where(VerificationRun.vendor_id == vendor.id)).all())
        assert len(runs_in_db) >= 2


class TestStep51ClassificationEligibility:
    """Tests Section 2: Classification-aware evidence eligibility and classification conflict detection."""

    def test_classification_conflict_declared_vs_predicted(self, db: Session):
        """6. Declared as TAX_CERTIFICATE but classified as BANK_PROOF -> reported as classification conflict."""
        vendor = create_step5_vendor(db)
        # Declared TAX_CERTIFICATE, but classifier predicted BANK_PROOF
        doc, clf, ext = seed_doc_with_pipeline(
            db, vendor.id,
            declared_category="TAX_CERTIFICATE",
            filename="misleading_tax.pdf",
            fields={"gstin": {"field_name": "gstin", "extracted_value": "27AABCU9603R1ZM", "status": "EXTRACTED", "confidence": 0.95}},
            predicted_category="BANK_PROOF",
            classification_status="CLASSIFIED",
            classification_confidence=0.92,
        )

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        conflict_finding = next((f for f in res.findings if f.field_name == "document_classification"), None)
        assert conflict_finding is not None
        assert conflict_finding.result == FindingResult.POTENTIAL_DISCREPANCY
        assert conflict_finding.severity == FindingSeverity.WARNING
        assert "Classification conflict detected" in conflict_finding.explanation
        assert "Declared as 'TAX_CERTIFICATE' but classified as 'BANK_PROOF'" in conflict_finding.explanation
        assert conflict_finding.evidence_sources[0].classification_id == clf.id

        # Declared category in DB must remain unchanged
        db_doc = db.scalar(select(VendorDocument).where(VendorDocument.id == doc.id))
        assert db_doc.document_category == "TAX_CERTIFICATE"

    def test_unknown_classification_ineligible(self, db: Session):
        """7. Document with UNKNOWN classification must not be used as confirmed evidence."""
        vendor = create_step5_vendor(db)
        seed_doc_with_pipeline(
            db, vendor.id,
            declared_category="TAX_CERTIFICATE",
            filename="blurred_doc.pdf",
            fields={"gstin": {"field_name": "gstin", "extracted_value": "27AABCU9603R1ZM", "status": "EXTRACTED", "confidence": 0.95}},
            predicted_category="UNKNOWN",
            classification_status="UNKNOWN",
            classification_confidence=0.0,
        )

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        clf_finding = next(f for f in res.findings if f.field_name == "document_classification")
        assert clf_finding.result == FindingResult.INSUFFICIENT_EVIDENCE
        assert "inconclusive" in clf_finding.explanation.lower()

        # Tax identifier rule must report missing or ineligible evidence, NOT claim a verified match!
        gstin_finding = next(f for f in res.findings if f.field_name == "gstin")
        assert gstin_finding.result == FindingResult.INSUFFICIENT_EVIDENCE


class TestStep51ExtractionEligibility:
    """Tests Section 3: Extraction eligibility, failed runs, and stale results."""

    def test_failed_extraction_run_generates_insufficient_evidence(self, db: Session):
        """9. Failed extraction run must generate an explicit insufficient-evidence finding."""
        vendor = create_step5_vendor(db)
        seed_doc_with_pipeline(
            db, vendor.id,
            declared_category="TAX_CERTIFICATE",
            filename="corrupted_ocr.pdf",
            fields={},
            extraction_status="FAILED",
            extraction_limitation="OCR_ENGINE_CRASH",
        )

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        ext_finding = next(f for f in res.findings if f.field_name == "document_extraction")
        assert ext_finding.result == FindingResult.INSUFFICIENT_EVIDENCE
        assert "extraction failed" in ext_finding.explanation.lower()

    def test_insufficient_text_extraction(self, db: Session):
        """10. Extraction with INSUFFICIENT_TEXT generates appropriate finding."""
        vendor = create_step5_vendor(db)
        seed_doc_with_pipeline(
            db, vendor.id,
            declared_category="TAX_CERTIFICATE",
            filename="blank_scan.pdf",
            fields={},
            extraction_status="INSUFFICIENT_TEXT",
            extraction_limitation="NO_EXTRACTABLE_TEXT",
        )

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        ext_finding = next(f for f in res.findings if f.field_name == "document_extraction")
        assert ext_finding.result == FindingResult.INSUFFICIENT_EVIDENCE
        assert "insufficient readable text" in ext_finding.explanation.lower()

    def test_latest_extraction_selected(self, db: Session):
        """12. If multiple extractions exist for a document, the latest is selected."""
        vendor = create_step5_vendor(db)
        doc = VendorDocument(
            id=str(uuid.uuid4()),
            vendor_id=vendor.id,
            original_filename="gst_multi_extract.pdf",
            sanitized_filename="gst_multi_extract.pdf",
            document_category="TAX_CERTIFICATE",
            mime_type="application/pdf",
            file_extension="pdf",
            file_size_bytes=1024,
            storage_identifier="test/multi.pdf",
            sha256_checksum="b" * 64,
            upload_status="PROCESSED",
        )
        db.add(doc)
        db.commit()

        # Classification
        clf = DocumentClassification(
            id=str(uuid.uuid4()),
            document_id=doc.id,
            vendor_id=vendor.id,
            predicted_category="TAX_CERTIFICATE",
            status="CLASSIFIED",
            confidence_score=0.95,
        )
        db.add(clf)

        # Earlier extraction
        ext1 = DocumentExtraction(
            id=str(uuid.uuid4()),
            document_id=doc.id,
            vendor_id=vendor.id,
            document_category_used="TAX_CERTIFICATE",
            status="COMPLETED",
            fields={"gstin": {"field_name": "gstin", "extracted_value": "OLD_GSTIN_1111", "status": "EXTRACTED", "confidence": 0.8}},
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        # Later extraction with updated correct value
        ext2 = DocumentExtraction(
            id=str(uuid.uuid4()),
            document_id=doc.id,
            vendor_id=vendor.id,
            document_category_used="TAX_CERTIFICATE",
            status="COMPLETED",
            fields={"gstin": {"field_name": "gstin", "extracted_value": "27AABCU9603R1ZM", "status": "EXTRACTED", "confidence": 0.95}},
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        db.add_all([ext1, ext2])
        db.commit()

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        gstin_finding = next(f for f in res.findings if f.field_name == "gstin")
        assert gstin_finding.result == FindingResult.MATCH
        doc_ev = next(s for s in gstin_finding.evidence_sources if s.source_type.value == "EXTRACTED_DOCUMENT_FIELD")
        assert doc_ev.extraction_id == ext2.id

    def test_cross_vendor_isolation(self, db: Session):
        """14. Extractions and documents belonging to vendor A must never bleed into vendor B."""
        vendor_a = create_step5_vendor(db, gstin="27AABCU9603R1ZM")
        vendor_b = create_step5_vendor(db, gstin="29BBBBB1111B2Z6")

        # Document and extraction for vendor A
        seed_doc_with_pipeline(
            db, vendor_a.id, "TAX_CERTIFICATE", "vendor_a_tax.pdf",
            {"gstin": {"field_name": "gstin", "extracted_value": "27AABCU9603R1ZM", "status": "EXTRACTED", "confidence": 0.95}},
        )

        # Run verification for vendor B (who has uploaded NO documents)
        res_b = VerificationService.run_verification_for_vendor(db, vendor_b.id)
        assert res_b.missing_documents >= 1
        gstin_b = next(f for f in res_b.findings if f.field_name == "gstin")
        assert gstin_b.result == FindingResult.MISSING_DOCUMENT
        # Confirm vendor B findings contain 0 references to vendor A's document
        for f in res_b.findings:
            for s in f.evidence_sources:
                assert s.document_name != "vendor_a_tax.pdf"


class TestStep51PrivacyHardening:
    """Tests Section 4: Strict zero-leakage masking across all API responses, summaries, and activity."""

    def test_zero_raw_identifiers_in_serialized_verification(self, db: Session):
        """15. Verifies complete serialization of API responses, summaries, and activities does NOT leak raw identifiers."""
        raw_gstin = "27AABCU9603R1ZM"
        raw_account = "98765432101234"
        raw_cin = "U72900MH2021PTC368421"

        vendor = create_step5_vendor(
            db,
            gstin=raw_gstin,
            cin=raw_cin,
            account_number=raw_account,
        )

        seed_doc_with_pipeline(
            db, vendor.id, "TAX_CERTIFICATE", "tax.pdf",
            {"gstin": {"field_name": "gstin", "extracted_value": "27XXXXX9999X1Z1", "status": "EXTRACTED", "confidence": 0.95}},
        )
        seed_doc_with_pipeline(
            db, vendor.id, "BANK_PROOF", "bank.pdf",
            {"account_number": {"field_name": "account_number", "extracted_value": "11112222333344", "status": "EXTRACTED", "confidence": 0.95}},
        )

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        res_json = res.model_dump_json()

        # Assert raw sensitive identifiers NEVER appear in the serialized JSON
        assert raw_gstin not in res_json
        assert raw_account not in res_json
        assert raw_cin not in res_json
        assert "27XXXXX9999X1Z1" not in res_json
        assert "11112222333344" not in res_json

        # Assert proper masking is present
        assert "27•••••••••1ZM" in res_json or "27••••" in res_json
        assert "••••••••1234" in res_json

        # Check DB findings table
        db_findings = list(db.scalars(select(VerificationFinding).where(VerificationFinding.verification_run_id == res.id)).all())
        for df in db_findings:
            assert raw_gstin not in (df.explanation or "")
            assert raw_account not in (df.explanation or "")
            assert raw_gstin not in (df.comparison_summary or "")
            assert raw_account not in (df.comparison_summary or "")
            if df.evidence_sources:
                sources_str = json.dumps(df.evidence_sources)
                assert raw_gstin not in sources_str
                assert raw_account not in sources_str

    def test_sanitized_snippet_masks_embedded_identifiers(self, db: Session):
        """16. Ensure sanitized snippets do not reintroduce raw sensitive identifiers."""
        raw_gstin = "27AABCU9603R1ZM"
        raw_account = "98765432101234"
        raw_cin = "U72900MH2021PTC368421"

        vendor = create_step5_vendor(db)
        fields = {
            "gstin": {
                "field_name": "gstin",
                "extracted_value": raw_gstin,
                "status": "EXTRACTED",
                "confidence": 0.95,
                "source": {
                    "page_number": 1,
                    "extraction_method": "DIGITAL_TEXT",
                    "evidence_snippet": f"Taxpayer GSTIN: {raw_gstin}, Bank Acc: {raw_account}, CIN: {raw_cin}",
                },
            }
        }

        seed_doc_with_pipeline(db, vendor.id, "TAX_CERTIFICATE", "snippet_test.pdf", fields)
        res = VerificationService.run_verification_for_vendor(db, vendor.id)

        finding = next(f for f in res.findings if f.field_name == "gstin")
        doc_ev = next(s for s in finding.evidence_sources if s.source_type.value == "EXTRACTED_DOCUMENT_FIELD")
        snippet = doc_ev.sanitized_snippet
        assert snippet is not None
        assert raw_gstin not in snippet
        assert raw_account not in snippet
        assert raw_cin not in snippet
        assert "27••••" in snippet
        assert "••••••••1234" in snippet


class TestStep51FuzzyMatchingAndDecisionSafety:
    """Tests Section 5 & 7: Conservative fuzzy matching and decision safety."""

    def test_no_automatic_rejection_due_to_uncertainty(self, db: Session):
        """19. Low-confidence OCR, unreadable fields, or missing docs must NEVER set vendor status to REJECTED."""
        vendor = create_step5_vendor(db, status="APPROVED")
        # Missing all docs
        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        db.refresh(vendor)
        assert vendor.status != "REJECTED"
        assert vendor.status in ("APPROVED", "PENDING")

        # Now upload unreadable doc
        seed_doc_with_pipeline(
            db, vendor.id, "TAX_CERTIFICATE", "unreadable.pdf",
            {"gstin": {"field_name": "gstin", "extracted_value": None, "status": "UNREADABLE", "confidence": 0.2}},
        )
        res2 = VerificationService.run_verification_for_vendor(db, vendor.id)
        db.refresh(vendor)
        assert vendor.status != "REJECTED"

    def test_no_duplicate_decision_records(self, db: Session):
        """20. Verification execution must not create spurious duplicate decision records."""
        vendor = create_step5_vendor(db)
        dec_before = len(list(db.scalars(select(VendorDecision).where(VendorDecision.vendor_id == vendor.id)).all()))

        VerificationService.run_verification_for_vendor(db, vendor.id)
        VerificationService.run_verification_for_vendor(db, vendor.id)

        dec_after = len(list(db.scalars(select(VendorDecision).where(VendorDecision.vendor_id == vendor.id)).all()))
        assert dec_after == dec_before
