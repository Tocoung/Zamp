"""Automated test suite for Phase 2 Step 2: Document Classification Engine & Explainability."""

import io
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.vendor import Vendor
from app.models.document import VendorDocument
from app.models.classification import DocumentClassification
from app.models.activity import VendorActivity
from app.classification.text_extractor import extract_document_text
from app.classification.engine import classification_engine
from app.schemas.classification import (
    ClassificationStatus,
    ClassificationLimitationCode,
    DocumentClassificationResponse,
)


def make_pdf_with_text(text: str) -> bytes:
    """Builds a minimal valid PDF with a single page containing an extractable text stream."""
    escaped_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 712 Td ({escaped_text}) Tj ET"
    stream_bytes = stream.encode("latin1")
    pdf_str = f"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length {len(stream_bytes)} >>
stream
{stream}
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000244 00000 n 
0000000350 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
433
%%EOF
"""
    return pdf_str.encode("latin1")


# Valid synthetic binary payloads with authentic magic signatures
EMPTY_PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
VALID_PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"


@pytest.fixture
def test_vendor(client: TestClient) -> dict:
    """Creates a temporary registered vendor for classification testing."""
    unique_reg = f"U72200DL2024PTC{uuid.uuid4().hex[:6].upper()}"
    payload = {
        "legal_name": "Apex Document AI Pvt Ltd",
        "trade_name": "Apex DocAI",
        "business_type": "Private Limited",
        "country_of_incorporation": "India",
        "registration_number": unique_reg,
        "contact_name": "Arjun Sharma",
        "contact_email": f"arjun.{uuid.uuid4().hex[:4]}@apexdocai.com",
        "contact_phone": "+919876543210",
        "address_line1": "Level 8, Tech CyberPark",
        "address_line2": "Sector 44",
        "city": "Gurugram",
        "state_province": "Haryana",
        "postal_code": "122002",
        "address_country": "India",
        "tax_id_type": "GSTIN",
        "tax_id_number": "06AAACA1234A1Z5",
        "bank_account_number": "123456789012",
        "bank_routing_number": "HDFC0001234",
        "bank_name": "HDFC Bank",
        "bank_account_holder_name": "Apex Document AI Pvt Ltd",
        "bank_country": "India",
    }
    response = client.post("/api/v1/vendors", json=payload)
    assert response.status_code == 201, f"Vendor creation failed: {response.text}"
    return response.json()


# ============================================================================
# 1. TEXT EXTRACTOR TESTS
# ============================================================================

def test_text_extractor_pdf_with_text():
    """Extracts text correctly from digitally-readable PDF."""
    raw = make_pdf_with_text("Certificate of Incorporation Ministry of Corporate Affairs Registrar of Companies")
    text, is_extractable, limitation = extract_document_text(raw, "application/pdf")
    assert is_extractable is True
    assert limitation is None
    assert "Certificate of Incorporation" in text
    assert "Registrar of Companies" in text


def test_text_extractor_scanned_pdf():
    """Empty or non-text PDF returns is_extractable=False and NO_EXTRACTABLE_TEXT."""
    text, is_extractable, limitation = extract_document_text(EMPTY_PDF_BYTES, "application/pdf")
    assert is_extractable is False
    assert text == ""
    assert limitation == ClassificationLimitationCode.NO_EXTRACTABLE_TEXT.value


def test_text_extractor_image_files():
    """PNG and JPEG images return is_extractable=False and IMAGE_ONLY_DOCUMENT."""
    text, is_extractable, limitation = extract_document_text(VALID_PNG_BYTES, "image/png")
    assert is_extractable is False
    assert text == ""
    assert limitation == ClassificationLimitationCode.IMAGE_ONLY_DOCUMENT.value

    text_jpg, is_ext_jpg, lim_jpg = extract_document_text(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\xff\xd9", "image/jpeg")
    assert is_ext_jpg is False
    assert lim_jpg == ClassificationLimitationCode.IMAGE_ONLY_DOCUMENT.value


def test_text_extractor_corrupt_data():
    """Corrupt bytes return is_extractable=False and NO_EXTRACTABLE_TEXT without crashing."""
    text, is_extractable, limitation = extract_document_text(b"not a valid pdf", "application/pdf")
    assert is_extractable is False
    assert text == ""
    assert limitation == ClassificationLimitationCode.NO_EXTRACTABLE_TEXT.value


# ============================================================================
# 2. CLASSIFICATION ENGINE UNIT TESTS
# ============================================================================

def test_engine_incorporation_high_confidence():
    """Clear Certificate of Incorporation text produces CLASSIFIED outcome."""
    text = (
        "GOVERNMENT OF INDIA MINISTRY OF CORPORATE AFFAIRS "
        "Central Registration Centre CERTIFICATE OF INCORPORATION "
        "Corporate Identity Number CIN U72200DL2024PTC123456 "
        "Registrar of Companies Companies Act 2013 Articles of Association"
    )
    result = classification_engine.classify(
        content=make_pdf_with_text(text),
        filename="incorporation_cert.pdf",
        mime_type="application/pdf",
    )
    assert result.predicted_category == "CERTIFICATE_OF_INCORPORATION"
    assert result.status == ClassificationStatus.CLASSIFIED
    assert result.confidence_score >= 0.70
    assert len(result.evidence["matched_headings"]) > 0


def test_engine_tax_certificate_high_confidence():
    """Clear Tax Certificate / GSTIN text produces CLASSIFIED outcome."""
    text = (
        "GOVERNMENT OF INDIA Form GST REG-06 Registration Certificate "
        "Goods and Services Tax GSTIN 09AAACA1234A1Z5 Legal Name Taxpayer "
        "Date of Liability Period of Validity Jurisdiction Central Tax"
    )
    result = classification_engine.classify(
        content=make_pdf_with_text(text),
        filename="gst_registration.pdf",
        mime_type="application/pdf",
    )
    assert result.predicted_category == "TAX_CERTIFICATE"
    assert result.status == ClassificationStatus.CLASSIFIED
    assert result.confidence_score >= 0.70
    assert "matched_headings" in result.evidence


def test_engine_bank_proof_high_confidence():
    """Clear bank statement text produces CLASSIFIED outcome."""
    text = (
        "HDFC BANK ACCOUNT STATEMENT FOR THE PERIOD "
        "Account Holder Name Apex Document AI Pvt Ltd "
        "Account Number 123456789012 IFSC Code HDFC0001234 "
        "Branch Address Opening Balance Closing Balance Transaction Details"
    )
    result = classification_engine.classify(
        content=make_pdf_with_text(text),
        filename="bank_statement.pdf",
        mime_type="application/pdf",
    )
    assert result.predicted_category == "BANK_PROOF"
    assert result.status == ClassificationStatus.CLASSIFIED
    assert result.confidence_score >= 0.70


def test_engine_address_proof_high_confidence():
    """Clear utility bill / address proof produces CLASSIFIED outcome."""
    text = (
        "ELECTRICITY BILL CONSUMER INVOICE "
        "Service Address Premises Address Level 8 Tech CyberPark Gurugram "
        "Utility Provider Energy Bill Meter Number Billing Cycle Total Amount Due"
    )
    result = classification_engine.classify(
        content=make_pdf_with_text(text),
        filename="electricity_bill.pdf",
        mime_type="application/pdf",
    )
    assert result.predicted_category == "ADDRESS_PROOF"
    assert result.status == ClassificationStatus.CLASSIFIED
    assert result.confidence_score >= 0.70


def test_engine_ambiguous_low_confidence():
    """Generic text with weak signals produces LOW_CONFIDENCE and UNKNOWN category."""
    text = (
        "This is an informal memo regarding internal project updates. "
        "The project team met yesterday to discuss general schedule alignment. "
        "No official registration or banking items are mentioned here."
    )
    result = classification_engine.classify(
        content=make_pdf_with_text(text),
        filename="project_notes.pdf",
        mime_type="application/pdf",
    )
    assert result.status == ClassificationStatus.LOW_CONFIDENCE
    assert result.predicted_category == "UNKNOWN"
    assert result.confidence_score < 0.40


def test_engine_conflicting_signals():
    """Document with conflicting headings produces LOW_CONFIDENCE with CONFLICTING_SIGNALS limitation."""
    text = (
        "CERTIFICATE OF INCORPORATION REGISTRAR OF COMPANIES "
        "ACCOUNT STATEMENT CANCELLED CHEQUE IFSC CODE "
        "Goods and Services Tax GSTIN Form GST REG-06"
    )
    result = classification_engine.classify(
        content=make_pdf_with_text(text),
        filename="mixed_scan.pdf",
        mime_type="application/pdf",
    )
    assert result.status == ClassificationStatus.LOW_CONFIDENCE
    assert result.limitation_code == ClassificationLimitationCode.CONFLICTING_SIGNALS.value


def test_engine_insufficient_text():
    """Unextractable document produces INSUFFICIENT_TEXT and zero confidence."""
    result = classification_engine.classify(
        content=EMPTY_PDF_BYTES,
        filename="empty.pdf",
        mime_type="application/pdf",
    )
    assert result.status == ClassificationStatus.INSUFFICIENT_TEXT
    assert result.predicted_category == "UNKNOWN"
    assert result.confidence_score == 0.0
    assert result.limitation_code == ClassificationLimitationCode.NO_EXTRACTABLE_TEXT.value


def test_engine_filename_only_never_confident():
    """Matching filename alone can NEVER elevate an empty document to CLASSIFIED."""
    result = classification_engine.classify(
        content=EMPTY_PDF_BYTES,
        filename="tax_certificate_gst.pdf",
        mime_type="application/pdf",
    )
    assert result.status == ClassificationStatus.INSUFFICIENT_TEXT
    assert result.predicted_category == "UNKNOWN"
    assert result.confidence_score == 0.0


# ============================================================================
# 3. ENDPOINT & LIFECYCLE INTEGRATION TESTS
# ============================================================================

def test_classify_endpoint_success(client: TestClient, test_vendor: dict):
    """POST /classify correctly classifies an uploaded PDF and records explainable evidence."""
    vendor_id = test_vendor["id"]
    pdf_content = make_pdf_with_text(
        "GOVERNMENT OF INDIA Form GST REG-06 Registration Certificate "
        "Goods and Services Tax GSTIN 06AAACA1234A1Z5 Legal Name Apex Document AI"
    )

    # 1. Upload document (deliberately declared as OTHER to test declared vs predicted)
    upload_res = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("tax_doc.pdf", pdf_content, "application/pdf")},
        data={"document_category": "OTHER"},
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["id"]

    # 2. Trigger classification
    classify_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/classify")
    assert classify_res.status_code == 200
    cls_data = classify_res.json()

    assert cls_data["document_id"] == doc_id
    assert cls_data["vendor_id"] == vendor_id
    assert cls_data["declared_category"] == "OTHER"
    assert cls_data["predicted_category"] == "TAX_CERTIFICATE"
    assert cls_data["status"] == ClassificationStatus.CLASSIFIED.value
    assert cls_data["confidence_score"] >= 0.70
    assert "matched_headings" in cls_data["evidence"]

    # 3. Retrieve latest classification via GET
    get_res = client.get(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/classification")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == cls_data["id"]

    # 4. Check document list includes latest_classification
    docs_res = client.get(f"/api/v1/vendors/{vendor_id}/documents")
    assert docs_res.status_code == 200
    matched = [d for d in docs_res.json()["items"] if d["id"] == doc_id][0]
    assert matched["latest_classification"] is not None
    assert matched["latest_classification"]["predicted_category"] == "TAX_CERTIFICATE"


def test_classify_endpoint_image_document(client: TestClient, test_vendor: dict):
    """Classifying a PNG image returns INSUFFICIENT_TEXT with IMAGE_ONLY_DOCUMENT limitation."""
    vendor_id = test_vendor["id"]
    upload_res = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("voided_cheque.png", VALID_PNG_BYTES, "image/png")},
        data={"document_category": "BANK_PROOF"},
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["id"]

    classify_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/classify")
    assert classify_res.status_code == 200
    cls_data = classify_res.json()

    assert cls_data["status"] == ClassificationStatus.INSUFFICIENT_TEXT.value
    assert cls_data["predicted_category"] == "UNKNOWN"
    assert cls_data["confidence_score"] == 0.0
    assert cls_data["limitation_code"] == ClassificationLimitationCode.IMAGE_ONLY_DOCUMENT.value


def test_classification_history_and_reclassification(client: TestClient, test_vendor: dict):
    """Re-classifying a document stores a versioned history log without mutating previous records."""
    vendor_id = test_vendor["id"]
    pdf_content = make_pdf_with_text(
        "GOVERNMENT OF INDIA Form GST REG-06 Registration Certificate "
        "Goods and Services Tax GSTIN 06AAACA1234A1Z5"
    )

    upload_res = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("tax_record.pdf", pdf_content, "application/pdf")},
    )
    doc_id = upload_res.json()["id"]

    # Run 1
    res1 = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/classify")
    assert res1.status_code == 200
    id1 = res1.json()["id"]

    # Run 2
    res2 = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/classify")
    assert res2.status_code == 200
    id2 = res2.json()["id"]
    assert id1 != id2

    # History endpoint
    hist_res = client.get(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/classification-history")
    assert hist_res.status_code == 200
    hist_data = hist_res.json()
    assert hist_data["total"] >= 2
    history_ids = [item["id"] for item in hist_data["items"]]
    assert id2 in history_ids
    assert id1 in history_ids


def test_vendor_decision_status_not_mutated_by_classification(client: TestClient, test_vendor: dict):
    """Document classification must NEVER mutate or touch vendor compliance decision status."""
    vendor_id = test_vendor["id"]

    # 1. Run a formal decision to set an established vendor status
    decision_res = client.post(f"/api/v1/vendors/{vendor_id}/decide")
    assert decision_res.status_code == 200
    established_status = decision_res.json()["status"]
    assert established_status in ("APPROVED", "PENDING", "REJECTED")

    v_before = client.get(f"/api/v1/vendors/{vendor_id}").json()
    assert v_before["status"] == established_status

    # 2. Upload and classify an ambiguous document
    ambiguous_pdf = make_pdf_with_text("Some random ambiguous notes without clear regulatory headings")
    upload_res = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("notes.pdf", ambiguous_pdf, "application/pdf")},
    )
    doc_id = upload_res.json()["id"]

    cls_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/classify")
    assert cls_res.status_code == 200
    assert cls_res.json()["status"] == ClassificationStatus.LOW_CONFIDENCE.value

    # 3. Verify vendor status is still strictly unmutated
    v_after = client.get(f"/api/v1/vendors/{vendor_id}").json()
    assert v_after["status"] == established_status


def test_cross_vendor_isolation(client: TestClient, test_vendor: dict):
    """Attempting to classify or view document under another vendor returns 404."""
    vendor_a_id = test_vendor["id"]

    # Create Vendor B
    unique_reg = f"U72200MH2024PTC{uuid.uuid4().hex[:6].upper()}"
    res_b = client.post("/api/v1/vendors", json={
        "legal_name": "Beta Cross Test Corp",
        "trade_name": "Beta Cross",
        "business_type": "Private Limited",
        "country_of_incorporation": "India",
        "registration_number": unique_reg,
        "contact_name": "Maya Sen",
        "contact_email": f"maya.{uuid.uuid4().hex[:4]}@betacross.com",
        "contact_phone": "+919876543211",
        "address_line1": "Marine Lines",
        "city": "Mumbai",
        "state_province": "Maharashtra",
        "postal_code": "400020",
        "address_country": "India",
        "tax_id_type": "GSTIN",
        "tax_id_number": "27AAACA1234A1Z5",
        "bank_account_number": "987654321098",
        "bank_routing_number": "ICIC0001234",
        "bank_name": "ICICI Bank",
        "bank_account_holder_name": "Beta Cross Test Corp",
        "bank_country": "India",
    })
    vendor_b_id = res_b.json()["id"]

    # Upload to Vendor A
    pdf_content = make_pdf_with_text("Certificate of Incorporation Ministry of Corporate Affairs")
    upload_res = client.post(
        f"/api/v1/vendors/{vendor_a_id}/documents",
        files={"file": ("coi.pdf", pdf_content, "application/pdf")},
    )
    doc_a_id = upload_res.json()["id"]

    # Try classifying Vendor A's document via Vendor B's URL
    forbidden_classify = client.post(f"/api/v1/vendors/{vendor_b_id}/documents/{doc_a_id}/classify")
    assert forbidden_classify.status_code == 404

    # Try fetching classification via Vendor B's URL
    forbidden_get = client.get(f"/api/v1/vendors/{vendor_b_id}/documents/{doc_a_id}/classification")
    assert forbidden_get.status_code == 404


# ============================================================================
# 5. STEP 2.1 PRIVACY, FILENAME HANDLING, AND CONFIDENCE HARDENING TESTS
# ============================================================================

def test_sensitive_identifiers_never_leaked_in_evidence_or_activities_or_logs(
    client: TestClient,
    test_vendor: dict,
    test_db_session: Session,
    caplog: pytest.LogCaptureFixture,
):
    """Synthetic identifiers (bank acct, PAN, GSTIN, email, name) must never appear in

    evidence, DB records, activity descriptions, or application logs.
    """
    import logging
    vendor_id = test_vendor["id"]

    secret_account = "9988776655443322"
    secret_gstin = "27ABCDE1234F1Z5"
    secret_pan = "ABCDE1234F"
    secret_email = "confidential.cfo@secret-vendor-domain.org"
    secret_person = "Cornelius Fudge"
    sensitive_filename = f"bank_statement_{secret_account}_{secret_pan}.pdf"

    pdf_text = (
        f"HDFC BANK ACCOUNT STATEMENT FOR THE PERIOD "
        f"Account Holder Name Apex Document AI Pvt Ltd "
        f"Account Number {secret_account} PAN {secret_pan} GSTIN {secret_gstin} "
        f"Contact {secret_email} Authorized Signatory {secret_person} "
        f"IFSC Code HDFC0001234 Opening Balance Closing Balance Transaction Details"
    )
    pdf_bytes = make_pdf_with_text(pdf_text)

    with caplog.at_level(logging.DEBUG):
        # 1. Upload document with sensitive filename
        upload_res = client.post(
            f"/api/v1/vendors/{vendor_id}/documents",
            files={"file": (sensitive_filename, pdf_bytes, "application/pdf")},
            data={"document_category": "BANK_PROOF"},
        )
        assert upload_res.status_code == 201
        doc_id = upload_res.json()["id"]

        # 2. Trigger classification
        classify_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/classify")
        assert classify_res.status_code == 200
        cls_json = classify_res.json()

    # 3. Verify response evidence contains NONE of the sensitive identifiers
    import json
    evidence_str = json.dumps(cls_json.get("evidence", {}))
    for secret in (secret_account, secret_gstin, secret_pan, secret_email, secret_person):
        assert secret not in evidence_str, f"Sensitive identifier '{secret}' leaked into response evidence!"

    # 4. Verify persisted DB classification record contains NONE of the sensitive identifiers
    db_record = test_db_session.get(DocumentClassification, cls_json["id"])
    assert db_record is not None
    db_evidence_str = json.dumps(db_record.evidence or {})
    for secret in (secret_account, secret_gstin, secret_pan, secret_email, secret_person):
        assert secret not in db_evidence_str, f"Sensitive identifier '{secret}' leaked into DB evidence!"

    # 5. Verify vendor activity descriptions contain NONE of the sensitive identifiers
    activities = test_db_session.query(VendorActivity).filter(VendorActivity.vendor_id == vendor_id).all()
    for act in activities:
        for secret in (secret_account, secret_gstin, secret_pan, secret_email, secret_person):
            assert secret not in (act.description or ""), f"Sensitive identifier '{secret}' leaked into activity: {act.description}"

    # 6. Verify application logs contain NONE of the sensitive identifiers or raw extracted text
    app_log_messages = " ".join([rec.getMessage() for rec in caplog.records if rec.name == "zamp_app"])
    for secret in (secret_account, secret_gstin, secret_pan, secret_email, secret_person):
        assert secret not in app_log_messages, f"Sensitive identifier '{secret}' leaked into application logs!"


def test_filename_signal_cannot_produce_classified_status_alone():
    """A document with generic text but an explicit filename must NEVER produce CLASSIFIED status."""
    generic_text = (
        "Internal project memo regarding weekly engineering sync. "
        "The team discussed milestone dates and backlog grooming items. "
        "No formal entity registrations or tax items exist here."
    )
    result = classification_engine.classify(
        content=make_pdf_with_text(generic_text),
        filename="certificate_of_incorporation_master.pdf",
        mime_type="application/pdf",
    )
    assert result.status == ClassificationStatus.LOW_CONFIDENCE
    assert result.predicted_category == "UNKNOWN"
    assert result.confidence_score == 0.0


def test_image_document_remains_insufficient_text_regardless_of_filename():
    """An image-only document must remain INSUFFICIENT_TEXT with score 0.0 regardless of filename."""
    result = classification_engine.classify(
        content=VALID_PNG_BYTES,
        filename="bank_account_statement_proof.png",
        mime_type="image/png",
    )
    assert result.status == ClassificationStatus.INSUFFICIENT_TEXT
    assert result.predicted_category == "UNKNOWN"
    assert result.confidence_score == 0.0
    assert result.limitation_code == ClassificationLimitationCode.IMAGE_ONLY_DOCUMENT.value


def test_generic_filename_does_not_affect_strong_content_result():
    """A generic filename (e.g., 'scan_001.pdf') does not penalize strong content signals."""
    tax_text = (
        "GOVERNMENT OF INDIA Form GST REG-06 Registration Certificate "
        "Goods and Services Tax GSTIN 09AAACA1234A1Z5 Legal Name Taxpayer "
        "Date of Liability Period of Validity Jurisdiction Central Tax"
    )
    result = classification_engine.classify(
        content=make_pdf_with_text(tax_text),
        filename="scan_001.pdf",
        mime_type="application/pdf",
    )
    assert result.predicted_category == "TAX_CERTIFICATE"
    assert result.status == ClassificationStatus.CLASSIFIED
    assert result.confidence_score >= 0.70


def test_filename_with_sensitive_numbers_not_copied_into_evidence():
    """Filename containing sensitive tax/account numbers does not copy numbers into evidence."""
    tax_text = (
        "GOVERNMENT OF INDIA Form GST REG-06 Registration Certificate "
        "Goods and Services Tax GSTIN 09AAACA1234A1Z5 Legal Name Taxpayer"
    )
    sensitive_filename = "gst_cert_09AAACA1234A1Z5_9988776655.pdf"
    result = classification_engine.classify(
        content=make_pdf_with_text(tax_text),
        filename=sensitive_filename,
        mime_type="application/pdf",
    )
    import json
    ev_str = json.dumps(result.evidence)
    assert "09AAACA1234A1Z5" not in ev_str
    assert "9988776655" not in ev_str
    # Secondary signals should only contain the clean token 'gst'
    assert result.evidence.get("secondary_filename_signals") == ["gst"]


def test_confidence_presentation_semantics(client: TestClient, test_vendor: dict):
    """Confidence score is numeric float and activity log reflects rule-based match score phrasing."""
    vendor_id = test_vendor["id"]
    pdf_text = (
        "ELECTRICITY BILL CONSUMER INVOICE Service Address Premises Address Level 8 Tech CyberPark Gurugram "
        "Utility Provider Energy Bill Meter Number Billing Cycle Total Amount Due"
    )
    upload_res = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("utility_bill.pdf", make_pdf_with_text(pdf_text), "application/pdf")},
        data={"document_category": "ADDRESS_PROOF"},
    )
    doc_id = upload_res.json()["id"]

    cls_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/classify")
    assert cls_res.status_code == 200
    cls_data = cls_res.json()

    assert isinstance(cls_data["confidence_score"], float)
    assert 0.0 <= cls_data["confidence_score"] <= 1.0

    # Check vendor activity log phrasing
    act_res = client.get(f"/api/v1/vendors/{vendor_id}/activities")
    assert act_res.status_code == 200
    activities = act_res.json()["items"]
    classified_activities = [a for a in activities if a["event_type"] == "DOCUMENT_CLASSIFIED"]
    assert len(classified_activities) > 0
    desc = classified_activities[0]["description"]
    assert "rule-based match score" in desc
    assert "% confidence" not in desc

