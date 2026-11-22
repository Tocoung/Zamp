"""Automated verification suite for the 4 specific user scenarios in Phase 2 Step 4.1.

Scenarios:
1. Upload one synthetic scanned PDF with two differently clear fields on the same page.
   Confirm their field-quality assessments can differ.
2. Preview a normal PNG and confirm it opens correctly.
3. Try an oversized or malformed synthetic image and confirm the preview is rejected safely.
4. Test an impossible date such as 31/04/2024; confirm it is not normalized into a valid date.
"""

import io
import uuid
import pytest
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from app.schemas.extraction import FieldStatus
from app.extraction.normalization import normalize_date


def create_vendor_helper(client: TestClient, name: str = "Apex Scenarios Vendor Ltd") -> dict:
    unique_reg = f"U72200DL2024PTC{uuid.uuid4().hex[:6].upper()}"
    payload = {
        "legal_name": name,
        "trade_name": "Apex Scenarios",
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
        "tax_id_number": "29ABCDE1234F1Z5",
        "bank_account_number": "987654321012",
        "bank_routing_number": "HDFC0001234",
        "bank_name": "HDFC Bank",
        "bank_account_holder_name": name,
        "bank_country": "India",
    }
    response = client.post("/api/v1/vendors", json=payload)
    assert response.status_code == 201
    return response.json()


def test_scenario_1_differing_field_qualities_on_same_page(client: TestClient):
    """Scenario 1: Upload one synthetic scanned PDF with two differently clear fields
    on the same page. Confirm their field-quality assessments can differ.
    """
    vendor = create_vendor_helper(client, name="Apex Quality Contrast Solutions Ltd")
    vendor_id = vendor["id"]

    # Generate a single-page rasterized PDF (scanned document)
    # Field 1 (Legal Name): crisp high contrast black on white
    # Field 2 (GSTIN): slightly lighter gray text
    img = Image.new("RGB", (1200, 1600), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((100, 100), "GOVERNMENT OF INDIA", fill="black")
    draw.text((100, 150), "Form GST REG-06 - Registration Certificate", fill="black")
    draw.text((100, 300), "Registration Number: 29ABCDE1234F1Z5", fill="black")
    draw.text((100, 400), "Legal Name: Apex Quality Contrast Solutions Ltd", fill="black")
    draw.text((100, 500), "Date of Registration: 15/08/2021", fill=(140, 140, 140))

    pdf_buf = io.BytesIO()
    img.save(pdf_buf, format="PDF")
    pdf_bytes = pdf_buf.getvalue()

    upload_res = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("scanned_tax_cert.pdf", pdf_bytes, "application/pdf")},
        data={"document_category": "TAX_CERTIFICATE"},
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["id"]

    # Trigger extraction
    ext_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/extract")
    assert ext_res.status_code == 200
    data = ext_res.json()
    fields = data["fields"]

    gstin_field = fields["gstin"]
    legal_name_field = fields["legal_entity_name"]

    # Both fields extracted from Page 1 via OCR
    assert gstin_field["source"]["page_number"] == 1
    assert legal_name_field["source"]["page_number"] == 1
    assert gstin_field["source"]["extraction_method"] == "OCR"
    assert legal_name_field["source"]["extraction_method"] == "OCR"

    # Confirm field-quality assessments differ on the same page
    assert gstin_field["quality_breakdown"]["source_quality"] != legal_name_field["quality_breakdown"]["source_quality"]
    assert gstin_field["quality_score"] != legal_name_field["quality_score"]

    # Confirm token-level confidence is reported in explanations
    assert "OCR token confidence" in gstin_field["quality_explanation"]
    assert "OCR token confidence" in legal_name_field["quality_explanation"]


def test_scenario_2_preview_normal_png_opens_correctly(client: TestClient):
    """Scenario 2: Preview a normal PNG and confirm it opens correctly."""
    vendor = create_vendor_helper(client, name="Apex PNG Preview Corp")
    vendor_id = vendor["id"]

    # Generate a normal valid PNG image
    img = Image.new("RGB", (600, 400), color=(240, 245, 250))
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "VOID CANCELLED CHEQUE - HDFC BANK", fill=(20, 40, 80))
    draw.text((50, 100), "Account: 50100987654321", fill=(20, 40, 80))
    draw.text((50, 150), "IFSC: HDFC0001234", fill=(20, 40, 80))

    png_buf = io.BytesIO()
    img.save(png_buf, format="PNG")
    png_bytes = png_buf.getvalue()

    upload_res = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("cancelled_cheque.png", png_bytes, "image/png")},
        data={"document_category": "BANK_PROOF"},
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["id"]

    # Request preview of Page 1
    preview_res = client.get(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/pages/1/preview")
    assert preview_res.status_code == 200
    assert preview_res.headers["content-type"] == "image/png"
    assert preview_res.headers["cache-control"] == "private, no-store, max-age=0"
    assert preview_res.headers["x-content-type-options"] == "nosniff"
    assert preview_res.headers["x-current-page"] == "1"
    assert preview_res.headers["x-total-pages"] == "1"

    # Confirm it opens correctly as a valid PNG
    assert preview_res.content.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(io.BytesIO(preview_res.content)) as opened_img:
        assert opened_img.format == "PNG"
        assert opened_img.size == (600, 400)


def test_scenario_3_oversized_and_malformed_image_rejected_safely(client: TestClient):
    """Scenario 3: Try an oversized or malformed synthetic image and confirm
    the preview is rejected safely without server error (500).
    """
    vendor = create_vendor_helper(client, name="Apex Image Security Corp")
    vendor_id = vendor["id"]

    # 3A. Malformed image: starts with PNG magic header but has corrupted body
    corrupted_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR_CORRUPTED_BODY_GARBAGE_BYTES"
    malformed_upload = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("corrupted.png", corrupted_bytes, "image/png")},
        data={"document_category": "OTHER"},
    )
    assert malformed_upload.status_code == 201
    malformed_doc_id = malformed_upload.json()["id"]

    malformed_preview = client.get(
        f"/api/v1/vendors/{vendor_id}/documents/{malformed_doc_id}/pages/1/preview"
    )
    assert malformed_preview.status_code == 400
    assert "corrupt" in malformed_preview.json()["detail"].lower() or "not a valid image" in malformed_preview.json()["detail"].lower()

    # 3B. Oversized image (width 4100px exceeds MAX_PREVIEW_DIMENSION 4096)
    oversized_img = Image.new("RGB", (4100, 100), color="white")
    oversized_buf = io.BytesIO()
    oversized_img.save(oversized_buf, format="PNG")
    oversized_bytes = oversized_buf.getvalue()

    oversized_upload = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("oversized.png", oversized_bytes, "image/png")},
        data={"document_category": "OTHER"},
    )
    assert oversized_upload.status_code == 201
    oversized_doc_id = oversized_upload.json()["id"]

    oversized_preview = client.get(
        f"/api/v1/vendors/{vendor_id}/documents/{oversized_doc_id}/pages/1/preview"
    )
    assert oversized_preview.status_code == 400
    assert "exceed" in oversized_preview.json()["detail"].lower()


def test_scenario_4_impossible_date_not_normalized_into_valid_date(client: TestClient):
    """Scenario 4: Test an impossible date such as 31/04/2024; confirm it is not
    normalized into a valid date.
    """
    # 4A. Direct calendar date validation: 31/04/2024 (April only has 30 days)
    res_apr_31 = normalize_date("31/04/2024")
    assert res_apr_31.is_valid_format is False
    assert any("Invalid calendar date" in note for note in res_apr_31.notes)

    # 4B. Non-leap year February 29th: 29/02/2023
    res_feb_29_nonleap = normalize_date("29/02/2023")
    assert res_feb_29_nonleap.is_valid_format is False
    assert any("Invalid calendar date" in note for note in res_feb_29_nonleap.notes)

    # 4C. ISO impossible date: 2024-04-31
    res_iso_invalid = normalize_date("2024-04-31")
    assert res_iso_invalid.is_valid_format is False
    assert any("Invalid calendar date" in note for note in res_iso_invalid.notes)

    # 4D. Real leap year date: 29/02/2024 succeeds
    res_feb_29_leap = normalize_date("29/02/2024")
    assert res_feb_29_leap.is_valid_format is True
    assert res_feb_29_leap.normalized_value == "2024-02-29"

    # 4E. End-to-end document extraction with impossible date
    vendor = create_vendor_helper(client, name="Apex Calendar Test Corp")
    vendor_id = vendor["id"]

    img = Image.new("RGB", (1000, 600), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "Certificate of Registration", fill="black")
    draw.text((50, 150), "Registration Number: 29ABCDE1234F1Z5", fill="black")
    draw.text((50, 250), "Date of Registration: 31/04/2024", fill="black")

    pdf_buf = io.BytesIO()
    img.save(pdf_buf, format="PDF")
    pdf_bytes = pdf_buf.getvalue()

    upload_res = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("impossible_date_doc.pdf", pdf_bytes, "application/pdf")},
        data={"document_category": "TAX_CERTIFICATE"},
    )
    doc_id = upload_res.json()["id"]

    ext_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/extract")
    assert ext_res.status_code == 200
    date_field = ext_res.json()["fields"]["registration_date"]

    # Confirm it is NOT normalized into a valid ISO date
    assert date_field["value"] != "2024-04-31"
    assert date_field["status"] in (FieldStatus.NEEDS_REVIEW.value, FieldStatus.UNREADABLE.value)
    assert date_field["normalization_notes"] is not None
    assert "Invalid calendar date" in date_field["normalization_notes"] or "does not strictly match" in date_field["quality_explanation"]
