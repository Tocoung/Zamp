"""Automated verification suite for the 6 specific user scenarios in Phase 2 Step 4."""

import uuid
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont
import io

from app.schemas.extraction import FieldStatus, ExtractionStatus
from tests.test_extraction import make_pdf_with_text, make_scanned_pdf


def create_vendor_helper(client: TestClient, name: str = "Apex Test Vendor Ltd", gstin: str = "29ABCDE1234F1Z5") -> dict:
    unique_reg = f"U72200DL2024PTC{uuid.uuid4().hex[:6].upper()}"
    payload = {
        "legal_name": name,
        "trade_name": "Apex Test",
        "business_type": "Private Limited",
        "country_of_incorporation": "India",
        "registration_number": unique_reg,
        "contact_name": "Rohan Verma",
        "contact_email": f"rohan.{uuid.uuid4().hex[:4]}@apextest.com",
        "contact_phone": "+919876543210",
        "address_line1": "Tower B, Sector 62",
        "city": "Noida",
        "state_province": "Uttar Pradesh",
        "postal_code": "201301",
        "address_country": "India",
        "tax_id_type": "GSTIN",
        "tax_id_number": gstin,
        "bank_account_number": "987654321012",
        "bank_routing_number": "HDFC0001234",
        "bank_name": "HDFC Bank",
        "bank_account_holder_name": name,
        "bank_country": "India",
    }
    response = client.post("/api/v1/vendors", json=payload)
    assert response.status_code == 201
    return response.json()


def test_scenario_1_high_confidence_clear_gstin(client: TestClient):
    """1. High-confidence field: extract a clear GSTIN from a synthetic digital PDF.
    Check its quality explanation and source page.
    """
    vendor = create_vendor_helper(client, name="Apex High Confidence Solutions Pvt Ltd")
    vendor_id = vendor["id"]

    pdf_content = """GOVERNMENT OF INDIA Form GST REG-06 Registration Certificate
Registration Number (GSTIN): 29ABCDE1234F1Z5
Legal Name: Apex High Confidence Solutions Pvt Ltd
Date of Registration: 15/04/2023
Principal Place of Business: 123 Tech Park, Bengaluru 560066"""
    pdf_bytes = make_pdf_with_text(pdf_content)

    upload_res = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("high_conf_gst.pdf", pdf_bytes, "application/pdf")},
        data={"document_category": "TAX_CERTIFICATE"},
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["id"]

    ext_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/extract")
    assert ext_res.status_code == 200
    data = ext_res.json()
    fields = data["fields"]
    gstin_field = fields["gstin"]

    # Assertions for Scenario 1
    assert gstin_field["status"] == FieldStatus.EXTRACTED.value
    assert gstin_field["value"] == "29ABCDE1234F1Z5"
    assert gstin_field["quality_score"] >= 0.75
    assert gstin_field["source"]["page_number"] == 1
    assert "29ABCDE1234F1Z5" in gstin_field["source"]["evidence_snippet"]
    assert gstin_field["source"]["extraction_method"] == "DIGITAL_TEXT"
    assert "High evidence quality" in gstin_field["quality_explanation"]
    assert gstin_field["quality_breakdown"]["source_quality"] >= 0.90
    assert gstin_field["quality_breakdown"]["format_validity"] == 1.0


def test_scenario_2_low_confidence_distorted_scan(client: TestClient):
    """2. Low-confidence field: use a blurred or deliberately distorted synthetic scan.
    Confirm the field becomes NEEDS_REVIEW or UNREADABLE, rather than being presented as reliable.
    """
    vendor = create_vendor_helper(client, name="Apex Distorted Scan Pvt Ltd")
    vendor_id = vendor["id"]

    # Scanned PDF with OCR character distortion (starts with letter 'O' instead of digit '0')
    scanned_lines = [
        "GOVERNMENT OF INDIA - TAX CERTIFICATE",
        "Registration Certificate under GST",
        "Registration Number: O9AAACA1234A1Z5",
        "Legal Name: Apex Distorted Scan Pvt Ltd",
        "Date of Registration: 2022-11-10",
        "Principal Place of Business: Plot 88, Sector 62, Noida 201301",
    ]
    scanned_bytes = make_scanned_pdf(scanned_lines)

    upload_res = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("distorted_scan.pdf", scanned_bytes, "application/pdf")},
        data={"document_category": "TAX_CERTIFICATE"},
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["id"]

    ext_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/extract")
    assert ext_res.status_code == 200
    data = ext_res.json()
    gstin_field = data["fields"]["gstin"]

    # Assertions for Scenario 2: Confirm field becomes NEEDS_REVIEW or UNREADABLE, rather than being presented as reliable
    assert gstin_field["status"] in (FieldStatus.NEEDS_REVIEW.value, FieldStatus.UNREADABLE.value)
    assert gstin_field["normalization_notes"] is not None
    assert "repaired" in gstin_field["normalization_notes"].lower() or "O->0" in gstin_field["normalization_notes"]
    assert "review" in gstin_field["quality_explanation"].lower()


def test_scenario_3_ambiguous_date_no_silent_guess(client: TestClient):
    """3. Ambiguous date: use a document containing 03/04/2024.
    Confirm the system does not silently guess the date interpretation.
    """
    vendor = create_vendor_helper(client, name="Apex Ambiguous Date Solutions Pvt Ltd")
    vendor_id = vendor["id"]

    pdf_content = """Form GST REG-06 - Registration Certificate
Registration Number: 29ABCDE1234F1Z5
Legal Name: Apex Ambiguous Date Solutions Pvt Ltd
Date of Registration: 03/04/2024
Principal Place of Business: MG Road, Bengaluru 560001"""
    pdf_bytes = make_pdf_with_text(pdf_content)

    upload_res = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("ambiguous_date.pdf", pdf_bytes, "application/pdf")},
        data={"document_category": "TAX_CERTIFICATE"},
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["id"]

    ext_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/extract")
    assert ext_res.status_code == 200
    data = ext_res.json()
    date_field = data["fields"]["registration_date"]

    # Assertions for Scenario 3: Confirm system does not silently guess the date interpretation
    assert date_field["status"] == FieldStatus.NEEDS_REVIEW.value
    assert date_field["normalization_notes"] is not None
    assert "Ambiguous date format '03/04/2024'" in date_field["normalization_notes"]
    assert "requires operator verification" in date_field["normalization_notes"]


def test_scenario_4_missing_versus_unreadable(client: TestClient):
    """4. Missing versus unreadable: compare a document where a field is absent
    with one where the field label is visible but its value is blurred/empty.
    """
    vendor = create_vendor_helper(client, name="Apex Contrast Systems Ltd")
    vendor_id = vendor["id"]

    # 4A. Absent field: Registration date and address completely omitted from document
    absent_content = """Form GST REG-06 - Registration Certificate
Registration Number: 27AABCT1334E1ZP
Legal Name: Apex Contrast Systems Ltd"""
    absent_bytes = make_pdf_with_text(absent_content)

    res_a = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("absent_field.pdf", absent_bytes, "application/pdf")},
        data={"document_category": "TAX_CERTIFICATE"},
    )
    doc_a_id = res_a.json()["id"]
    ext_a = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_a_id}/extract").json()
    missing_date = ext_a["fields"]["registration_date"]

    # 4B. Unreadable field: Field label is present, but value is dashed / obscured
    unreadable_content = """Form GST REG-06 - Registration Certificate
Registration Number: 27AABCT1334E1ZP
Legal Name: Apex Contrast Systems Ltd
Date of Registration: ----------------
Principal Place of Business: ...................."""
    unreadable_bytes = make_pdf_with_text(unreadable_content)

    res_b = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("unreadable_field.pdf", unreadable_bytes, "application/pdf")},
        data={"document_category": "TAX_CERTIFICATE"},
    )
    doc_b_id = res_b.json()["id"]
    ext_b = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_b_id}/extract").json()
    unreadable_date = ext_b["fields"]["registration_date"]

    # Assertions for Scenario 4: Clear architectural distinction
    # Missing: value is None, source is None (no fabricated page)
    assert missing_date["status"] == FieldStatus.MISSING.value
    assert missing_date["value"] is None
    assert missing_date["source"] is None

    # Unreadable: value is None, but source IS preserved with page number and evidence
    assert unreadable_date["status"] == FieldStatus.UNREADABLE.value
    assert unreadable_date["value"] is None
    assert unreadable_date["source"] is not None
    assert unreadable_date["source"]["page_number"] == 1
    assert "Date of Registration" in unreadable_date["source"]["evidence_snippet"]


def test_scenario_5_evidence_inspection_page_preview(client: TestClient):
    """5. Evidence inspection: open the original page from the extraction result
    and verify it corresponds to the cited page.
    """
    vendor = create_vendor_helper(client, name="Apex Evidence Verification Ltd")
    vendor_id = vendor["id"]

    pdf_content = """GOVERNMENT OF INDIA Form GST REG-06 Registration Certificate
Registration Number (GSTIN): 29ABCDE1234F1Z5
Legal Name: Apex Evidence Verification Ltd"""
    pdf_bytes = make_pdf_with_text(pdf_content)

    upload_res = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("evidence_doc.pdf", pdf_bytes, "application/pdf")},
        data={"document_category": "TAX_CERTIFICATE"},
    )
    doc_id = upload_res.json()["id"]

    ext_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/extract")
    data = ext_res.json()
    gstin_field = data["fields"]["gstin"]
    cited_page = gstin_field["source"]["page_number"]
    assert cited_page == 1

    # Request the original page preview
    preview_res = client.get(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/pages/{cited_page}/preview")
    assert preview_res.status_code == 200
    assert preview_res.headers["content-type"] == "image/png"
    assert preview_res.headers["x-current-page"] == str(cited_page)
    assert preview_res.headers["x-total-pages"] == "1"
    assert preview_res.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_scenario_6_no_overwrite_vendor_profile(client: TestClient):
    """6. No overwrite: compare the vendor's submitted profile before and after extraction.
    Confirm the values and decision status remain unchanged.
    """
    initial_legal_name = "Original Submitted Entity Name Pvt Ltd"
    initial_tax_id = "07AAAAA0000A1Z5"
    vendor = create_vendor_helper(client, name=initial_legal_name, gstin=initial_tax_id)
    vendor_id = vendor["id"]

    # Verify profile before extraction
    profile_before = client.get(f"/api/v1/vendors/{vendor_id}").json()
    assert profile_before["status"] == "SUBMITTED"
    assert profile_before["legal_name"] == initial_legal_name
    assert profile_before["tax_id_number"] == initial_tax_id

    # Upload document with conflicting / different details
    conflicting_pdf = make_pdf_with_text("""GOVERNMENT OF INDIA Form GST REG-06
Registration Number (GSTIN): 29DIFFERENT999Z0
Legal Name: Completely Different Third-Party Entity Ltd""")

    upload_res = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("conflicting_tax_cert.pdf", conflicting_pdf, "application/pdf")},
        data={"document_category": "TAX_CERTIFICATE"},
    )
    doc_id = upload_res.json()["id"]

    # Run extraction
    ext_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/extract")
    assert ext_res.status_code == 200

    # Verify profile after extraction
    profile_after = client.get(f"/api/v1/vendors/{vendor_id}").json()

    # Confirm 100% data integrity: values and status are untouched
    assert profile_after["status"] == profile_before["status"] == "SUBMITTED"
    assert profile_after["legal_name"] == profile_before["legal_name"] == initial_legal_name
    assert profile_after["tax_id_number"] == profile_before["tax_id_number"] == initial_tax_id
    assert profile_after["registration_number"] == profile_before["registration_number"]
    assert profile_after["contact_email"] == profile_before["contact_email"]
