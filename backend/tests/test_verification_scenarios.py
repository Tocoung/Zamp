"""End-to-end verification scenarios covering all 13 required test cases."""

import uuid
from typing import Tuple
import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.vendor import Vendor
from app.models.document import VendorDocument
from app.models.extraction import DocumentExtraction
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


def create_test_vendor(
    db: Session,
    legal_name: str = "Acme Technologies Private Limited",
    gstin: str = "27AAAAA0000A1Z5",
    cin: str = "U72200MH2020PTC123456",
    account_holder: str = "Acme Technologies Private Limited",
    account_number: str = "123456789012",
    ifsc: str = "HDFC0000123",
    status: str = "APPROVED",
    address_line1: str = "Plot 42, Sector 18, Road No. 4",
    city: str = "Gurugram",
    state: str = "Haryana",
    postal_code: str = "122001",
) -> Vendor:
    """Helper to seed a vendor with encrypted bank account."""
    v = Vendor(
        id=str(uuid.uuid4()),
        legal_name=legal_name,
        trade_name="Acme Tech",
        business_type="PRIVATE_LIMITED",
        country_of_incorporation="IN",
        registration_number=cin,
        contact_name="John Doe",
        contact_email="john@acme.com",
        contact_phone="+919876543210",
        address_line1=address_line1,
        address_line2="Cyber City",
        city=city,
        state_province=state,
        postal_code=postal_code,
        address_country="IN",
        tax_id_type="GSTIN",
        tax_id_number=gstin,
        bank_account_holder_name=account_holder,
        bank_name="HDFC Bank",
        bank_account_number=encrypt_account_number(account_number),
        bank_routing_number=ifsc,
        bank_country="IN",
        status=status,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def create_test_doc_and_extraction(
    db: Session,
    vendor_id: str,
    category: str,
    filename: str,
    fields: dict,
    extraction_status: str = "COMPLETED",
) -> Tuple:
    """Helper to seed a VendorDocument and corresponding DocumentExtraction."""
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
        sha256_checksum="0" * 64,
        upload_status="PROCESSED",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    ext = DocumentExtraction(
        id=str(uuid.uuid4()),
        document_id=doc.id,
        vendor_id=vendor_id,
        document_category_used=category,
        status=extraction_status,
        fields=fields,
        extracted_fields_count=len(fields),
        extraction_engine_version="2.0.0",
    )
    db.add(ext)
    db.commit()
    db.refresh(ext)
    return doc, ext


class TestVerificationScenarios:
    """Implements all 13 required cross-document verification scenarios."""

    def test_scenario_01_completely_matching_vendor(self, db: Session):
        """1. Completely matching vendor: all documents match profile perfectly -> all MATCH, run status COMPLETED."""
        vendor = create_test_vendor(db)

        # Tax certificate
        create_test_doc_and_extraction(
            db, vendor.id, "TAX_CERTIFICATE", "gst_cert.pdf",
            {
                "gstin": {"field_name": "gstin", "extracted_value": "27AAAAA0000A1Z5", "status": "EXTRACTED", "confidence": 0.95, "method": "DIGITAL_TEXT", "page_number": 1},
                "legal_entity_name": {"field_name": "legal_entity_name", "extracted_value": "Acme Technologies Private Limited", "status": "EXTRACTED", "confidence": 0.95, "method": "DIGITAL_TEXT", "page_number": 1},
                "registered_address": {"field_name": "registered_address", "extracted_value": "Plot 42 Sector 18 Road No 4 Cyber City Gurugram Haryana 122001", "status": "EXTRACTED", "confidence": 0.92, "method": "DIGITAL_TEXT", "page_number": 1},
                "registration_date": {"field_name": "registration_date", "extracted_value": "2020-01-15", "status": "EXTRACTED", "confidence": 0.95, "method": "DIGITAL_TEXT", "page_number": 1},
            }
        )

        # Bank proof
        create_test_doc_and_extraction(
            db, vendor.id, "BANK_PROOF", "bank_statement.pdf",
            {
                "account_holder_name": {"field_name": "account_holder_name", "extracted_value": "Acme Technologies Private Limited", "status": "EXTRACTED", "confidence": 0.95, "method": "DIGITAL_TEXT", "page_number": 1},
                "account_number": {"field_name": "account_number", "extracted_value": "123456789012", "status": "EXTRACTED", "confidence": 0.98, "method": "DIGITAL_TEXT", "page_number": 1},
                "ifsc_code": {"field_name": "ifsc_code", "extracted_value": "HDFC0000123", "status": "EXTRACTED", "confidence": 0.95, "method": "DIGITAL_TEXT", "page_number": 1},
            }
        )

        # Certificate of Incorporation
        create_test_doc_and_extraction(
            db, vendor.id, "CERTIFICATE_OF_INCORPORATION", "coi.pdf",
            {
                "company_name": {"field_name": "company_name", "extracted_value": "Acme Technologies Private Limited", "status": "EXTRACTED", "confidence": 0.95, "method": "DIGITAL_TEXT", "page_number": 1},
                "cin_or_reg_number": {"field_name": "cin_or_reg_number", "extracted_value": "U72200MH2020PTC123456", "status": "EXTRACTED", "confidence": 0.95, "method": "DIGITAL_TEXT", "page_number": 1},
                "incorporation_date": {"field_name": "incorporation_date", "extracted_value": "2020-01-15", "status": "EXTRACTED", "confidence": 0.95, "method": "DIGITAL_TEXT", "page_number": 1},
            }
        )

        # Address proof
        create_test_doc_and_extraction(
            db, vendor.id, "ADDRESS_PROOF", "utility_bill.pdf",
            {
                "full_address": {"field_name": "full_address", "extracted_value": "Plot 42, Sector 18, Road No. 4, Cyber City, Gurugram, Haryana - 122001", "status": "EXTRACTED", "confidence": 0.92, "method": "DIGITAL_TEXT", "page_number": 1},
            }
        )

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        assert res.status == VerificationRunStatus.COMPLETED
        assert res.confirmed_discrepancies == 0
        assert res.potential_discrepancies == 0
        assert res.missing_documents == 0
        assert res.matches >= 10

    def test_scenario_02_gstin_mismatch(self, db: Session):
        """2. GSTIN mismatch: profile GSTIN != GST cert GSTIN -> CONFIRMED_DISCREPANCY, severity CRITICAL."""
        vendor = create_test_vendor(db, gstin="27AAAAA0000A1Z5")

        create_test_doc_and_extraction(
            db, vendor.id, "TAX_CERTIFICATE", "gst_cert.pdf",
            {
                "gstin": {"field_name": "gstin", "extracted_value": "29BBBBB1111B2Z6", "status": "EXTRACTED", "confidence": 0.95, "method": "DIGITAL_TEXT", "page_number": 1},
            }
        )

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        gstin_finding = next(f for f in res.findings if f.field_name == "gstin")
        assert gstin_finding.result == FindingResult.CONFIRMED_DISCREPANCY
        assert gstin_finding.severity == FindingSeverity.CRITICAL

    def test_scenario_03_legal_name_mismatch(self, db: Session):
        """3. Legal name mismatch: profile name != Certificate of Incorporation name -> CONFIRMED_DISCREPANCY, severity CRITICAL."""
        vendor = create_test_vendor(db, legal_name="Acme Technologies Private Limited")

        create_test_doc_and_extraction(
            db, vendor.id, "CERTIFICATE_OF_INCORPORATION", "coi.pdf",
            {
                "company_name": {"field_name": "company_name", "extracted_value": "Zenith Enterprises Global Ltd", "status": "EXTRACTED", "confidence": 0.95, "method": "DIGITAL_TEXT", "page_number": 1},
            }
        )

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        finding = next(f for f in res.findings if f.field_name == "legal_entity_name" and "Incorporation" in f.explanation and "Vendor Profile" in f.explanation)
        assert finding.result == FindingResult.CONFIRMED_DISCREPANCY
        assert finding.severity == FindingSeverity.CRITICAL

    def test_scenario_04_minor_name_variation(self, db: Session):
        """4. Minor name variation: Acme Technologies Private Limited vs Acme Technologies Pvt. Ltd. -> MATCH (similarity >= 0.90), severity INFO."""
        vendor = create_test_vendor(db, legal_name="Acme Technologies Private Limited")

        create_test_doc_and_extraction(
            db, vendor.id, "TAX_CERTIFICATE", "gst_cert.pdf",
            {
                "gstin": {"field_name": "gstin", "extracted_value": vendor.tax_id_number, "status": "EXTRACTED", "confidence": 0.95, "method": "DIGITAL_TEXT", "page_number": 1},
                "legal_entity_name": {"field_name": "legal_entity_name", "extracted_value": "Acme Technologies Pvt. Ltd.", "status": "EXTRACTED", "confidence": 0.95, "method": "DIGITAL_TEXT", "page_number": 1},
            }
        )

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        finding = next(f for f in res.findings if f.field_name == "legal_entity_name" and "Tax Certificate" in f.explanation and "Vendor Profile" in f.explanation)
        assert finding.result == FindingResult.MATCH
        assert finding.similarity_score >= 0.90
        assert finding.severity == FindingSeverity.INFO

    def test_scenario_05_cross_document_mismatch(self, db: Session):
        """5. Cross-document mismatch: GST cert name != Certificate of Incorporation name -> CONFIRMED_DISCREPANCY."""
        vendor = create_test_vendor(db)

        create_test_doc_and_extraction(
            db, vendor.id, "TAX_CERTIFICATE", "gst_cert.pdf",
            {
                "legal_entity_name": {"field_name": "legal_entity_name", "extracted_value": "Alpha Logistics Pvt Ltd", "status": "EXTRACTED", "confidence": 0.95, "method": "DIGITAL_TEXT", "page_number": 1},
            }
        )
        create_test_doc_and_extraction(
            db, vendor.id, "CERTIFICATE_OF_INCORPORATION", "coi.pdf",
            {
                "company_name": {"field_name": "company_name", "extracted_value": "Beta Holdings India Pvt Ltd", "status": "EXTRACTED", "confidence": 0.95, "method": "DIGITAL_TEXT", "page_number": 1},
            }
        )

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        finding = next(f for f in res.findings if f.field_name == "legal_entity_name" and "Tax Certificate" in f.explanation and "Incorporation" in f.explanation)
        assert finding.result == FindingResult.CONFIRMED_DISCREPANCY

    def test_scenario_06_bank_account_holder_mismatch(self, db: Session):
        """6. Bank account holder mismatch: profile account holder != bank statement name -> CONFIRMED_DISCREPANCY."""
        vendor = create_test_vendor(db, account_holder="Acme Technologies Private Limited")

        create_test_doc_and_extraction(
            db, vendor.id, "BANK_PROOF", "bank_statement.pdf",
            {
                "account_holder_name": {"field_name": "account_holder_name", "extracted_value": "Random Third Party Solutions", "status": "EXTRACTED", "confidence": 0.95, "method": "DIGITAL_TEXT", "page_number": 1},
            }
        )

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        finding = next(f for f in res.findings if f.field_name == "account_holder_name")
        assert finding.result == FindingResult.CONFIRMED_DISCREPANCY

    def test_scenario_07_bank_account_number_masked(self, db: Session):
        """7. Bank account number masked: verification result displays masked account number, never plain."""
        plain_acc = "98765432109876"
        vendor = create_test_vendor(db, account_number=plain_acc)

        create_test_doc_and_extraction(
            db, vendor.id, "BANK_PROOF", "bank_statement.pdf",
            {
                "account_number": {"field_name": "account_number", "extracted_value": plain_acc, "status": "EXTRACTED", "confidence": 0.95, "method": "DIGITAL_TEXT", "page_number": 1},
            }
        )

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        finding = next(f for f in res.findings if f.field_name == "bank_account_number")
        assert finding.result == FindingResult.MATCH

        # Check evidence sources and comparison summary
        for src in finding.evidence_sources:
            if src.value_display:
                assert plain_acc not in src.value_display
                assert "••••••••9876" in src.value_display
        assert plain_acc not in (finding.comparison_summary or "")
        assert "••••••••9876" in (finding.comparison_summary or "")

    def test_scenario_08_address_mismatch(self, db: Session):
        """8. Address mismatch: profile address in Mumbai, GST cert address in Delhi -> CONFIRMED_DISCREPANCY."""
        vendor = create_test_vendor(db, address_line1="12 Nariman Point", city="Mumbai", state="Maharashtra", postal_code="400021")

        create_test_doc_and_extraction(
            db, vendor.id, "TAX_CERTIFICATE", "gst_cert.pdf",
            {
                "registered_address": {"field_name": "registered_address", "extracted_value": "Connaught Place, Central Delhi, Delhi - 110001", "status": "EXTRACTED", "confidence": 0.95, "method": "DIGITAL_TEXT", "page_number": 1},
            }
        )

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        finding = next(f for f in res.findings if f.field_name == "registered_address" and "Tax Certificate" in f.explanation)
        assert finding.result == FindingResult.CONFIRMED_DISCREPANCY
        assert finding.severity == FindingSeverity.WARNING

    def test_scenario_09_address_minor_variation(self, db: Session):
        """9. Address minor variation: Road vs Rd, different whitespace -> MATCH or high similarity."""
        vendor = create_test_vendor(db, address_line1="Plot 42, Sector 18, Road No. 4", city="Gurugram", state="Haryana", postal_code="122001")

        create_test_doc_and_extraction(
            db, vendor.id, "TAX_CERTIFICATE", "gst_cert.pdf",
            {
                "registered_address": {"field_name": "registered_address", "extracted_value": "Plot 42, Sec 18, Rd 4, Cyber City, Gurugram, HR - 122001", "status": "EXTRACTED", "confidence": 0.95, "method": "DIGITAL_TEXT", "page_number": 1},
            }
        )

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        finding = next(f for f in res.findings if f.field_name == "registered_address" and "Tax Certificate" in f.explanation)
        assert finding.result == FindingResult.MATCH
        assert (finding.similarity_score or 0) >= 0.75

    def test_scenario_10_missing_document(self, db: Session):
        """10. Missing document: tax certificate uploaded, bank proof missing -> MISSING_DOCUMENT for bank rules, run status INCOMPLETE."""
        vendor = create_test_vendor(db)

        # Upload only TAX_CERTIFICATE
        create_test_doc_and_extraction(
            db, vendor.id, "TAX_CERTIFICATE", "gst_cert.pdf",
            {
                "gstin": {"field_name": "gstin", "extracted_value": vendor.tax_id_number, "status": "EXTRACTED", "confidence": 0.95, "method": "DIGITAL_TEXT", "page_number": 1},
            }
        )

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        bank_finding = next(f for f in res.findings if f.field_name == "bank_account_number")
        assert bank_finding.result == FindingResult.MISSING_DOCUMENT
        assert res.missing_documents > 0
        assert res.status in (VerificationRunStatus.INCOMPLETE, VerificationRunStatus.NEEDS_REVIEW)

    def test_scenario_11_unreadable_document(self, db: Session):
        """11. Unreadable document: extraction produced UNREADABLE -> INSUFFICIENT_EVIDENCE."""
        vendor = create_test_vendor(db)

        create_test_doc_and_extraction(
            db, vendor.id, "TAX_CERTIFICATE", "unreadable_gst.pdf",
            {
                "gstin": {"field_name": "gstin", "extracted_value": None, "status": "UNREADABLE", "confidence": 0.20, "method": "OCR", "page_number": 1},
            }
        )

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        finding = next(f for f in res.findings if f.field_name == "gstin")
        assert finding.result == FindingResult.INSUFFICIENT_EVIDENCE
        assert finding.severity == FindingSeverity.INFO

    def test_scenario_12_low_confidence_extraction(self, db: Session):
        """12. Low-confidence extraction: extraction confidence 0.55 -> POTENTIAL_DISCREPANCY (never CONFIRMED_DISCREPANCY), severity WARNING (never CRITICAL)."""
        vendor = create_test_vendor(db, gstin="27AAAAA0000A1Z5")

        create_test_doc_and_extraction(
            db, vendor.id, "TAX_CERTIFICATE", "noisy_gst.pdf",
            {
                # Conflicting value, but low confidence (0.55 < 0.70)
                "gstin": {"field_name": "gstin", "extracted_value": "29BBBBB1111B2Z6", "status": "NEEDS_REVIEW", "confidence": 0.55, "method": "OCR", "page_number": 1},
            }
        )

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        finding = next(f for f in res.findings if f.field_name == "gstin")
        assert finding.result == FindingResult.POTENTIAL_DISCREPANCY
        assert finding.result != FindingResult.CONFIRMED_DISCREPANCY
        assert finding.severity == FindingSeverity.WARNING
        assert finding.severity != FindingSeverity.CRITICAL

    def test_scenario_13_status_impact(self, db: Session):
        """13. Status impact: vendor was APPROVED, verification finds discrepancy -> vendor status transitions to PENDING (never REJECTED)."""
        vendor = create_test_vendor(db, status="APPROVED", gstin="27AAAAA0000A1Z5")
        assert vendor.status == "APPROVED"

        # Confirmed mismatch in GSTIN
        create_test_doc_and_extraction(
            db, vendor.id, "TAX_CERTIFICATE", "mismatched_gst.pdf",
            {
                "gstin": {"field_name": "gstin", "extracted_value": "99ZZZZZ9999Z9Z9", "status": "EXTRACTED", "confidence": 0.95, "method": "DIGITAL_TEXT", "page_number": 1},
            }
        )

        res = VerificationService.run_verification_for_vendor(db, vendor.id)
        assert res.confirmed_discrepancies > 0

        # Refresh vendor from DB
        db.refresh(vendor)
        assert vendor.status == "PENDING"
        assert vendor.status != "REJECTED"
