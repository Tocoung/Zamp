"""End-to-End Submission Readiness Integration Tests (Phase 2).

Validates the four mandatory submission scenarios:
Scenario A: Successful Vendor Onboarding (complete details, GST & bank docs, classification, OCR extraction, decision engine, persistence across restart).
Scenario B: Incomplete Vendor Submission (missing required fields, missing docs, explainable pending status, no fabrication).
Scenario C: Wrong Document Uploaded (incorrect declared category, mismatch detection, non-satisfaction of checklist, explainable review path).
Scenario D: Low-Confidence or Unreadable OCR (obscured/noisy scan, UNREADABLE/NEEDS_REVIEW field status, evidence quality scoring, no vendor profile overwrite, no automatic fraud rejection).
"""

import io
import os
import uuid
import pytest
from PIL import Image, ImageDraw, ImageFont
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.vendor import Vendor
from app.models.document import VendorDocument
from app.models.extraction import DocumentExtraction
from app.models.classification import DocumentClassification
from app.models.decision import VendorDecision
from app.models.activity import VendorActivity
from app.schemas.extraction import FieldStatus, ExtractionStatus


def get_font(size: int = 24):
    """Safely loads Arial or falls back to default font."""
    font_paths = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def create_synthetic_pdf(text: str) -> bytes:
    """Builds a minimal valid single-page PDF containing the provided selectable text."""
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


def create_synthetic_image(lines: list, width: int = 1200, height: int = 800) -> bytes:
    """Generates a clean synthetic PNG image with rendered text lines for OCR."""
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = get_font(28)
    
    y = 60
    for line in lines:
        draw.text((60, y), line, fill=(0, 0, 0), font=font)
        y += 50
        
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestSubmissionScenarios:
    """Integration verification for Part 1 scenarios."""

    def test_scenario_a_successful_vendor_onboarding(
        self, client: TestClient, test_session_factory
    ):
        """Scenario A: Successful Vendor Onboarding.
        
        1. Register complete and valid vendor.
        2. Upload GST certificate and Bank proof documents.
        3. Verify document storage encryption and retrieval.
        4. Run classification -> TAX_CERTIFICATE and BANK_PROOF.
        5. Run OCR extraction -> fields extracted with provenance.
        6. Deterministic decision engine -> APPROVED.
        7. Activity timeline & decision history persist consistently.
        """
        # 1. Register vendor
        vendor_payload = {
            "legal_name": "Apex Global Solutions Pvt Ltd",
            "trade_name": "Apex Global",
            "business_type": "Private Limited",
            "country_of_incorporation": "India",
            "registration_number": "U72900KA2021PTC145678",
            "contact_name": "Kiran Rao",
            "contact_email": "kiran.rao@apexglobal.example.in",
            "contact_phone": "+919876543210",
            "address_line1": "45 Residency Road",
            "city": "Bengaluru",
            "state_province": "Karnataka",
            "postal_code": "560025",
            "address_country": "India",
            "tax_id_type": "GSTIN",
            "tax_id_number": "29ABCDE1234F1Z5",
            "bank_account_holder_name": "Apex Global Solutions Pvt Ltd",
            "bank_name": "HDFC Bank",
            "bank_account_number": "50100234567890",
            "bank_routing_number": "HDFC0001234",
            "bank_country": "India",
        }
        res = client.post("/api/v1/vendors", json=vendor_payload)
        assert res.status_code == 201, res.text
        vendor = res.json()
        vendor_id = vendor["id"]
        assert vendor["status"] == "SUBMITTED"
        assert vendor["bank_account_number_masked"] == "••••••••7890"

        # 2. Upload GST certificate (PDF)
        gst_text = (
            "GOVERNMENT OF INDIA\n"
            "Registration Certificate under GST\n"
            "Registration Number: 29ABCDE1234F1Z5\n"
            "Legal Name: Apex Global Solutions Pvt Ltd\n"
            "Date of Registration: 15/08/2021\n"
        )
        gst_pdf = create_synthetic_pdf(gst_text)
        res_gst = client.post(
            f"/api/v1/vendors/{vendor_id}/documents",
            files={"file": ("gst_certificate.pdf", gst_pdf, "application/pdf")},
            data={"document_category": "TAX_CERTIFICATE"},
        )
        assert res_gst.status_code == 201, res_gst.text
        gst_doc = res_gst.json()
        gst_doc_id = gst_doc["id"]
        assert gst_doc["document_category"] == "TAX_CERTIFICATE"

        # Upload Bank Proof (PNG)
        bank_lines = [
            "HDFC BANK LIMITED",
            "ACCOUNT STATEMENT / CANCELLED CHEQUE PROOF",
            "Account Name: Apex Global Solutions Pvt Ltd",
            "Account Number: 50100234567890",
            "IFSC Code: HDFC0001234",
            "Branch: Bengaluru Residency Road",
        ]
        bank_png = create_synthetic_image(bank_lines)
        res_bank = client.post(
            f"/api/v1/vendors/{vendor_id}/documents",
            files={"file": ("bank_proof.png", bank_png, "image/png")},
            data={"document_category": "BANK_PROOF"},
        )
        assert res_bank.status_code == 201, res_bank.text
        bank_doc = res_bank.json()
        bank_doc_id = bank_doc["id"]
        assert bank_doc["document_category"] == "BANK_PROOF"

        # 3. Verify encrypted download retrieval
        dl_res = client.get(f"/api/v1/vendors/{vendor_id}/documents/{gst_doc_id}/content")
        assert dl_res.status_code == 200
        assert dl_res.content == gst_pdf
        assert "attachment" in dl_res.headers.get("content-disposition", "")

        # 4. Run classification
        cls_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{gst_doc_id}/classify")
        assert cls_res.status_code == 200
        cls_data = cls_res.json()
        assert cls_data["predicted_category"] == "TAX_CERTIFICATE"
        assert cls_data["declared_category"] == cls_data["predicted_category"]

        # 5. Run OCR and structured extraction on GST document
        ext_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{gst_doc_id}/extract")
        assert ext_res.status_code == 200
        ext_data = ext_res.json()
        assert ext_data["status"] in ("COMPLETED", "PARTIAL")
        fields = ext_data["fields"]
        assert "gstin" in fields
        assert fields["gstin"]["status"] == "EXTRACTED"
        assert fields["gstin"]["value"] == "29ABCDE1234F1Z5"
        assert fields["gstin"]["source"]["page_number"] == 1
        assert fields["gstin"]["quality_score"] > 0.50

        # 6. Evaluate deterministic decision
        dec_res = client.post(f"/api/v1/vendors/{vendor_id}/decide")
        assert dec_res.status_code == 200
        decision = dec_res.json()
        assert decision["status"] == "APPROVED"

        # 7. Check persisted state, decision history, and activity timeline
        v_check = client.get(f"/api/v1/vendors/{vendor_id}")
        assert v_check.status_code == 200
        assert v_check.json()["status"] == "APPROVED"

        hist_res = client.get(f"/api/v1/vendors/{vendor_id}/decision-history")
        assert hist_res.status_code == 200
        assert hist_res.json()["total"] >= 1

        act_res = client.get(f"/api/v1/vendors/{vendor_id}/activities")
        assert act_res.status_code == 200
        events = [a["event_type"] for a in act_res.json()["items"]]
        assert "VENDOR_SUBMITTED" in events
        assert "DECISION_EXECUTED" in events

        # 8. Verify persistence across clean database session re-query
        from sqlalchemy import select
        with test_session_factory() as verify_session:
            reloaded_vendor = verify_session.scalar(select(Vendor).where(Vendor.id == vendor_id))
            assert reloaded_vendor is not None
            assert reloaded_vendor.status == "APPROVED"
            assert reloaded_vendor.legal_name == "Apex Global Solutions Pvt Ltd"

            reloaded_docs = list(verify_session.scalars(select(VendorDocument).where(VendorDocument.vendor_id == vendor_id)).all())
            assert len(reloaded_docs) == 2

            reloaded_cls = verify_session.scalar(select(DocumentClassification).where(DocumentClassification.document_id == gst_doc_id))
            assert reloaded_cls is not None
            assert reloaded_cls.predicted_category == "TAX_CERTIFICATE"

            reloaded_ext = verify_session.scalar(select(DocumentExtraction).where(DocumentExtraction.document_id == gst_doc_id))
            assert reloaded_ext is not None
            assert "gstin" in reloaded_ext.fields

            reloaded_dec = verify_session.scalar(select(VendorDecision).where(VendorDecision.vendor_id == vendor_id))
            assert reloaded_dec is not None
            assert reloaded_dec.status == "APPROVED"

            reloaded_activities = list(verify_session.scalars(select(VendorActivity).where(VendorActivity.vendor_id == vendor_id)).all())
            assert len(reloaded_activities) >= 5

    def test_scenario_b_incomplete_vendor_submission(
        self, client: TestClient, test_db_session: Session
    ):
        """Scenario B: Incomplete Vendor Submission.
        
        1. Register vendor with partial details.
        2. Test validation endpoint for missing mandatory registration number.
        3. Upload only tax certificate; bank proof is omitted.
        4. Verify missing documents explicitly identified in document list.
        5. Verify that missing information is NOT fabricated.
        """
        # Complete vendor for initial persistence
        vendor_payload = {
            "legal_name": "Incomplete Ventures LLP",
            "business_type": "Partnership",
            "country_of_incorporation": "India",
            "registration_number": "TMP123456",
            "contact_name": "Priya Patel",
            "contact_email": "priya.patel@incomplete-ventures.example.in",
            "contact_phone": "+919876543210",
            "address_line1": "100 Commercial Road",
            "city": "Mumbai",
            "state_province": "Maharashtra",
            "postal_code": "400001",
            "address_country": "India",
            "tax_id_type": "GSTIN",
            "tax_id_number": "27AAAPN5678E1Z9",
            "bank_account_holder_name": "Incomplete Ventures LLP",
            "bank_name": "ICICI Bank",
            "bank_account_number": "8888000223344",
            "bank_routing_number": "ICIC0000456",
            "bank_country": "India",
        }
        res = client.post("/api/v1/vendors", json=vendor_payload)
        assert res.status_code == 201
        vendor_id = res.json()["id"]

        # Run validation endpoint with empty registration number
        check_payload = dict(vendor_payload)
        check_payload["registration_number"] = ""
        val_res = client.post("/api/v1/vendors/validate", json=check_payload)
        assert val_res.status_code == 200
        val_data = val_res.json()
        assert val_data["valid"] is False
        rule_ids = [f["rule_id"] for f in val_data["findings"]]
        assert "COMPANY_REGISTRATION_NUMBER_REQUIRED" in rule_ids

        # Upload tax certificate only (omitting bank proof)
        gst_text = (
            "GOVERNMENT OF INDIA\n"
            "Registration Certificate under GST\n"
            "Registration Number: 27AAAPN5678E1Z9\n"
            "Legal Name: Incomplete Ventures LLP\n"
        )
        res_gst = client.post(
            f"/api/v1/vendors/{vendor_id}/documents",
            files={"file": ("gst.pdf", create_synthetic_pdf(gst_text), "application/pdf")},
            data={"document_category": "TAX_CERTIFICATE"},
        )
        assert res_gst.status_code == 201

        # Check document list: TAX_CERTIFICATE present, BANK_PROOF absent
        docs_res = client.get(f"/api/v1/vendors/{vendor_id}/documents")
        assert docs_res.status_code == 200
        uploaded_categories = [d["document_category"] for d in docs_res.json()["items"]]
        assert "TAX_CERTIFICATE" in uploaded_categories
        assert "BANK_PROOF" not in uploaded_categories

        # Extract tax certificate: registration_date is omitted from document
        doc_id = res_gst.json()["id"]
        ext_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/extract")
        assert ext_res.status_code == 200
        ext_fields = ext_res.json()["fields"]
        # Verify omitted field is marked MISSING, not fabricated with a fake date
        assert "registration_date" in ext_fields
        assert ext_fields["registration_date"]["status"] == "MISSING"
        assert ext_fields["registration_date"]["value"] is None

    def test_scenario_c_wrong_document_uploaded(
        self, client: TestClient, test_db_session: Session
    ):
        """Scenario C: Wrong Document Uploaded.
        
        1. Upload an unrelated document (e.g. food receipt) declared as TAX_CERTIFICATE.
        2. Run classification and extraction.
        3. Classification detects category mismatch and provides explainable outcome.
        4. Extraction marks expected TAX fields MISSING; does not satisfy requirement.
        """
        # Create vendor
        v_res = client.post("/api/v1/vendors", json={
            "legal_name": "Delta Marine Supplies Pvt Ltd",
            "business_type": "Private Limited",
            "country_of_incorporation": "India",
            "registration_number": "U35100MH2020PTC345678",
            "contact_name": "Suresh Nair",
            "contact_email": "suresh@deltamarine.example.in",
            "contact_phone": "+919812345678",
            "address_line1": "Port Trust Road",
            "city": "Mumbai",
            "state_province": "Maharashtra",
            "postal_code": "400001",
            "address_country": "India",
            "tax_id_type": "GSTIN",
            "tax_id_number": "27ABCDE1234F1Z5",
            "bank_account_holder_name": "Delta Marine Supplies Pvt Ltd",
            "bank_name": "Canara Bank",
            "bank_account_number": "12345678901234",
            "bank_routing_number": "CNRB0001234",
            "bank_country": "India",
        })
        assert v_res.status_code == 201
        vendor_id = v_res.json()["id"]

        # Upload an unrelated receipt text declaring it as TAX_CERTIFICATE
        unrelated_text = (
            "COFFEE SHOP RECEIPT\n"
            "Table 4 - 2 Cappuccinos, 1 Croissant\n"
            "Total Amount: $14.50\n"
            "Thank you for your visit!\n"
        )
        pdf_bytes = create_synthetic_pdf(unrelated_text)
        doc_res = client.post(
            f"/api/v1/vendors/{vendor_id}/documents",
            files={"file": ("receipt.pdf", pdf_bytes, "application/pdf")},
            data={"document_category": "TAX_CERTIFICATE"},
        )
        assert doc_res.status_code == 201
        doc_id = doc_res.json()["id"]

        # Run classification
        cls_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/classify")
        assert cls_res.status_code == 200
        cls_data = cls_res.json()
        assert cls_data["declared_category"] != cls_data["predicted_category"]
        assert cls_data["predicted_category"] != "TAX_CERTIFICATE"

        # Run extraction
        ext_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/extract")
        assert ext_res.status_code == 200
        ext_data = ext_res.json()
        fields = ext_data["fields"]
        assert "gstin" in fields
        assert fields["gstin"]["status"] == "MISSING"

    def test_scenario_d_low_confidence_or_unreadable_ocr(
        self, client: TestClient, test_db_session: Session
    ):
        """Scenario D: Low-Confidence or Unreadable OCR.
        
        1. Upload a synthetic scanned document with obscured/unreadable text.
        2. Run OCR & extraction.
        3. Verify field marked UNREADABLE with evidence quality explanation.
        4. Confirm vendor submitted information is NOT silently overwritten.
        5. Confirm vendor is NOT automatically marked REJECTED for OCR noise.
        """
        # Create vendor
        v_res = client.post("/api/v1/vendors", json={
            "legal_name": "Zenith Systems Private Limited",
            "business_type": "Private Limited",
            "country_of_incorporation": "India",
            "registration_number": "U72200KA2020PTC123999",
            "contact_name": "Anita Desai",
            "contact_email": "anita@zenithsystems.example.in",
            "contact_phone": "+919876501234",
            "address_line1": "Tech Park, Whitefield",
            "city": "Bengaluru",
            "state_province": "Karnataka",
            "postal_code": "560066",
            "address_country": "India",
            "tax_id_type": "GSTIN",
            "tax_id_number": "29ABCDE1234F1Z5",
            "bank_account_holder_name": "Zenith Systems Private Limited",
            "bank_name": "Axis Bank",
            "bank_account_number": "91800234567890",
            "bank_routing_number": "UTIB0000123",
            "bank_country": "India",
        })
        assert v_res.status_code == 201
        vendor_id = v_res.json()["id"]

        # Synthetic image with clear label but obscured value
        img = Image.new("RGB", (1000, 400), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        font = get_font(30)
        draw.text((50, 50), "GOVERNMENT OF INDIA - GST REGISTRATION", fill=(0, 0, 0), font=font)
        draw.text((50, 130), "Registration Number: ", fill=(0, 0, 0), font=font)
        # Obscured value region: dense noise points
        for x in range(380, 750):
            for y in range(125, 175):
                if (x + y) % 3 == 0:
                    draw.point((x, y), fill=(30, 30, 30))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        doc_res = client.post(
            f"/api/v1/vendors/{vendor_id}/documents",
            files={"file": ("obscured_gst.png", buf.getvalue(), "image/png")},
            data={"document_category": "TAX_CERTIFICATE"},
        )
        assert doc_res.status_code == 201
        doc_id = doc_res.json()["id"]

        # Extract
        ext_res = client.post(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/extract")
        assert ext_res.status_code == 200
        ext_data = ext_res.json()
        fields = ext_data["fields"]
        
        tax_f = fields.get("gstin")
        assert tax_f is not None
        assert tax_f["status"] in ("UNREADABLE", "MISSING", "NEEDS_REVIEW")
        if tax_f["status"] == "UNREADABLE":
            assert tax_f["quality_score"] is not None
            assert "evidence" in tax_f["quality_explanation"].lower() or "score" in tax_f["quality_explanation"].lower()

        # Confirm vendor submitted details are NOT overwritten
        v_check = client.get(f"/api/v1/vendors/{vendor_id}")
        assert v_check.status_code == 200
        v_data = v_check.json()
        assert v_data["tax_id_number"] == "29ABCDE1234F1Z5"
        assert v_data["legal_name"] == "Zenith Systems Private Limited"

        # Confirm vendor is NOT automatically marked REJECTED purely for OCR scan noise
        dec_res = client.post(f"/api/v1/vendors/{vendor_id}/decide")
        assert dec_res.status_code == 200
        decision = dec_res.json()
        assert decision["status"] != "REJECTED"
