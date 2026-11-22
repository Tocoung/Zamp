"""Comprehensive automated test suite for Phase 2 Step 3: OCR & Structured Information Extraction."""

import io
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from PIL import Image, ImageDraw, ImageFont

from app.models.vendor import Vendor
from app.models.document import VendorDocument
from app.models.extraction import DocumentExtraction
from app.models.activity import VendorActivity
from app.schemas.extraction import FieldStatus, ExtractionStatus, ExtractionLimitationCode


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


def make_scanned_pdf(lines: list) -> bytes:
    img = Image.new("RGB", (1200, 700), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=24)
    y = 50
    for line in lines:
        draw.text((50, y), line, fill=(0, 0, 0), font=font)
        y += 50
    buf = io.BytesIO()
    img.save(buf, format="PDF")
    return buf.getvalue()


def make_image_document(lines: list, format="PNG") -> bytes:
    img = Image.new("RGB", (1200, 700), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=24)
    y = 50
    for line in lines:
        draw.text((50, y), line, fill=(0, 0, 0), font=font)
        y += 50
    buf = io.BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


@pytest.fixture
def extraction_vendor(client: TestClient) -> dict:
    unique_reg = f"U72200DL2024PTC{uuid.uuid4().hex[:6].upper()}"
    payload = {
        "legal_name": "Apex Extraction Solutions Pvt Ltd",
        "trade_name": "Apex Extract",
        "business_type": "Private Limited",
        "country_of_incorporation": "India",
        "registration_number": unique_reg,
        "contact_name": "Kavita Rao",
        "contact_email": f"kavita.{uuid.uuid4().hex[:4]}@apexextract.com",
        "contact_phone": "+919876543210",
        "address_line1": "Tower B, Sector 62",
        "city": "Noida",
        "state_province": "Uttar Pradesh",
        "postal_code": "201301",
        "address_country": "India",
        "tax_id_type": "GSTIN",
        "tax_id_number": "09AAACA1234A1Z5",
        "bank_account_number": "987654321012",
        "bank_routing_number": "HDFC0001234",
        "bank_name": "HDFC Bank",
        "bank_account_holder_name": "Apex Extraction Solutions Pvt Ltd",
        "bank_country": "India",
    }
    response = client.post("/api/v1/vendors", json=payload)
    assert response.status_code == 201
    return response.json()


def test_digital_pdf_gst_certificate_extraction(client: TestClient, extraction_vendor: dict):
    vendor_id = extraction_vendor["id"]
    gst_content = """GOVERNMENT OF INDIA Form GST REG-06 Registration Certificate
Goods and Services Tax GSTIN: 09AAACA1234A1Z5
Legal Name: Apex Extraction Solutions Pvt Ltd
Date of Registration: 23/08/2021
Principal Place of Business: Tower B, Sector 62, Noida, Uttar Pradesh 201301"""
    pdf_bytes = make_pdf_with_text(gst_content)

    upload_res = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("gst_cert.pdf", pdf_bytes, "application/pdf")},
        data={"document_category": "TAX_CERTIFICATE"},
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["id"]

    ext_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/extract")
    assert ext_res.status_code == 200, ext_res.text
    data = ext_res.json()

    assert data["status"] == ExtractionStatus.COMPLETED.value
    assert data["document_category_used"] == "TAX_CERTIFICATE"
    assert data["extracted_fields_count"] == 4

    fields = data["fields"]
    assert fields["gstin"]["status"] == FieldStatus.EXTRACTED.value
    assert fields["gstin"]["value"] == "09AAACA1234A1Z5"
    assert fields["gstin"]["source"]["extraction_method"] == "DIGITAL_TEXT"
    assert fields["gstin"]["source"]["page_number"] == 1

    assert fields["legal_entity_name"]["status"] == FieldStatus.EXTRACTED.value
    assert fields["legal_entity_name"]["value"] == "Apex Extraction Solutions Pvt Ltd"

    assert fields["registration_date"]["status"] == FieldStatus.EXTRACTED.value
    assert fields["registration_date"]["value"] == "2021-08-23"

    assert fields["registered_address"]["status"] == FieldStatus.EXTRACTED.value


def test_scanned_pdf_ocr_extraction(client: TestClient, extraction_vendor: dict):
    vendor_id = extraction_vendor["id"]
    scanned_lines = [
        "GOVERNMENT OF INDIA",
        "Registration Certificate",
        "GSTIN: 09AAACA1234A1Z5",
        "Legal Name: Apex Scanned Tech Pvt Ltd",
        "Date of Registration: 15/04/2022",
        "Principal Place of Business: Sector 62 Noida",
    ]
    scanned_bytes = make_scanned_pdf(scanned_lines)

    upload_res = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("scanned_tax.pdf", scanned_bytes, "application/pdf")},
        data={"document_category": "TAX_CERTIFICATE"},
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["id"]

    ext_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/extract")
    assert ext_res.status_code == 200, ext_res.text
    data = ext_res.json()

    assert data["status"] in (ExtractionStatus.COMPLETED.value, ExtractionStatus.PARTIAL.value)
    fields = data["fields"]
    assert fields["gstin"]["status"] == FieldStatus.EXTRACTED.value
    assert fields["gstin"]["value"] == "09AAACA1234A1Z5"
    assert fields["gstin"]["source"]["extraction_method"] == "OCR"
    assert fields["gstin"]["source"]["page_number"] == 1


def test_image_bank_proof_extraction(client: TestClient, extraction_vendor: dict):
    vendor_id = extraction_vendor["id"]
    bank_lines = [
        "HDFC Bank Ltd",
        "Account Holder Name: Apex Extraction Solutions Pvt Ltd",
        "Account Number: 987654321012",
        "IFSC Code: HDFC0001234",
        "Branch: Sector 62 Noida",
    ]
    png_bytes = make_image_document(bank_lines, format="PNG")

    upload_res = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("bank_cheque.png", png_bytes, "image/png")},
        data={"document_category": "BANK_PROOF"},
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["id"]

    ext_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/extract")
    assert ext_res.status_code == 200, ext_res.text
    data = ext_res.json()

    fields = data["fields"]
    assert fields["bank_name"]["status"] == FieldStatus.EXTRACTED.value
    assert "HDFC Bank" in fields["bank_name"]["value"]

    assert fields["account_number"]["status"] == FieldStatus.EXTRACTED.value
    assert fields["account_number"]["masked_value"] == "********1012"

    assert fields["ifsc_code"]["status"] == FieldStatus.EXTRACTED.value
    assert fields["ifsc_code"]["value"] == "HDFC0001234"


def test_missing_fields_not_fabricated(client: TestClient, extraction_vendor: dict):
    vendor_id = extraction_vendor["id"]
    partial_gst_content = """GOVERNMENT OF INDIA Form GST REG-06
Goods and Services Tax GSTIN: 09AAACA1234A1Z5
Legal Name: Apex Incomplete Entity Pvt Ltd"""
    pdf_bytes = make_pdf_with_text(partial_gst_content)

    upload_res = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("partial_gst.pdf", pdf_bytes, "application/pdf")},
        data={"document_category": "TAX_CERTIFICATE"},
    )
    doc_id = upload_res.json()["id"]

    ext_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/extract")
    assert ext_res.status_code == 200
    data = ext_res.json()

    assert data["status"] == ExtractionStatus.PARTIAL.value
    fields = data["fields"]

    assert fields["gstin"]["status"] == FieldStatus.EXTRACTED.value
    assert fields["legal_entity_name"]["status"] == FieldStatus.EXTRACTED.value

    assert fields["registration_date"]["status"] == FieldStatus.MISSING.value
    assert fields["registration_date"]["value"] is None
    assert fields["registration_date"]["limitation_or_reason"] == "Field not detected in document content."

    assert fields["registered_address"]["status"] == FieldStatus.MISSING.value
    assert fields["registered_address"]["value"] is None
    assert fields["registered_address"]["limitation_or_reason"] == "Field not detected in document content."


def test_provenance_integrity(client: TestClient, extraction_vendor: dict):
    vendor_id = extraction_vendor["id"]
    gst_content = """GOVERNMENT OF INDIA Form GST REG-06 Registration Certificate
GSTIN: 09AAACA1234A1Z5
Legal Name: Provenance Test Corp"""
    pdf_bytes = make_pdf_with_text(gst_content)

    upload_res = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("provenance.pdf", pdf_bytes, "application/pdf")},
        data={"document_category": "TAX_CERTIFICATE"},
    )
    doc_id = upload_res.json()["id"]

    ext_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/extract")
    data = ext_res.json()
    fields = data["fields"]

    gstin_f = fields["gstin"]
    assert gstin_f["source"]["document_id"] == doc_id
    assert gstin_f["source"]["page_number"] == 1
    assert gstin_f["source"]["extraction_method"] == "DIGITAL_TEXT"
    assert "09AAACA1234A1Z5" in gstin_f["source"]["evidence_snippet"]

    name_f = fields["legal_entity_name"]
    assert name_f["source"]["document_id"] == doc_id
    assert name_f["source"]["page_number"] == 1
    assert "Provenance Test Corp" in name_f["source"]["evidence_snippet"]


def test_sensitive_information_masking_and_regression(
    client: TestClient,
    test_db_session: Session,
    extraction_vendor: dict,
    caplog,
):
    vendor_id = extraction_vendor["id"]
    secret_acc = "445566778899"
    bank_lines = [
        "HDFC Bank Statement",
        "Account Holder: Privacy Test Ltd",
        f"Account Number: {secret_acc}",
        "IFSC Code: HDFC0001234",
    ]
    png_bytes = make_image_document(bank_lines, format="PNG")

    upload_res = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": (f"cheque_{secret_acc}.png", png_bytes, "image/png")},
        data={"document_category": "BANK_PROOF"},
    )
    doc_id = upload_res.json()["id"]

    ext_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/extract")
    assert ext_res.status_code == 200
    data = ext_res.json()

    acc_field = data["fields"]["account_number"]
    assert acc_field["masked_value"] == "********8899"

    activities = test_db_session.query(VendorActivity).filter(VendorActivity.vendor_id == vendor_id).all()
    for act in activities:
        assert secret_acc not in (act.description or ""), f"Secret leaked in activity: {act.description}"

    del_res = client.delete(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}")
    assert del_res.status_code == 204

    ext_after_del = test_db_session.query(DocumentExtraction).filter(DocumentExtraction.document_id == doc_id).all()
    assert len(ext_after_del) == 0, "DocumentExtraction records were not cascaded upon document deletion!"


def test_cross_vendor_isolation(client: TestClient, extraction_vendor: dict):
    vendor_id = extraction_vendor["id"]
    pdf_bytes = make_pdf_with_text("Registration details")

    upload_res = client.post(
        f"/api/v1/vendors/{vendor_id}/documents",
        files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
    )
    doc_id = upload_res.json()["id"]

    other_vendor_id = str(uuid.uuid4())
    res = client.post(f"/api/v1/vendors/{other_vendor_id}/documents/{doc_id}/extract")
    assert res.status_code == 404
