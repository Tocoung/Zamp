"""Comprehensive automated tests for Phase 2 Step 4: Extraction Confidence & Evidence Management."""

import io
import uuid
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from app.models.vendor import Vendor
from app.models.document import VendorDocument
from app.models.extraction import DocumentExtraction
from app.schemas.extraction import FieldStatus, ExtractionStatus
from app.extraction.normalization import (
    normalize_gstin,
    normalize_date,
    normalize_entity_name,
    normalize_address,
    normalize_ifsc,
    normalize_account_number,
)
from app.extraction.confidence import (
    quality_assessor,
    HIGH_CONFIDENCE_THRESHOLD,
    LOW_CONFIDENCE_THRESHOLD,
)
from app.extraction.ocr_engine import OcrDocumentResult, OcrPageResult
from app.extraction.parsers import DocumentParser


# ---------------------------------------------------------------------------
# Test Normalization Layer
# ---------------------------------------------------------------------------

class TestNormalizationLayer:
    """Tests dedicated normalization rules and edge cases."""

    def test_gstin_normalization_valid(self):
        rec = normalize_gstin("  27aaaca9999a1z5  ")
        assert rec.is_valid_format is True
        assert rec.normalized_value == "27AAACA9999A1Z5"
        assert rec.was_repaired is False
        assert rec.penalty == 0.0

    def test_gstin_ocr_repair_tracking(self):
        # Starts with 'O' instead of '0', e.g. O9AAACA1234A1Z5
        rec = normalize_gstin("O9AAACA1234A1Z5")
        assert rec.is_valid_format is True
        assert rec.normalized_value == "09AAACA1234A1Z5"
        assert rec.was_repaired is True
        assert "O->0 at pos 0" in rec.repaired_chars
        assert rec.penalty > 0.0
        assert "Repaired OCR character confusion" in rec.summary_note

    def test_gstin_malformed_syntax(self):
        rec = normalize_gstin("INVALID-GSTIN-123")
        assert rec.is_valid_format is False
        assert rec.penalty >= 0.50

    def test_date_unambiguous_iso_and_slash(self):
        # 15/04/2021 -> day 15 is unambiguously day
        rec = normalize_date("15/04/2021")
        assert rec.is_valid_format is True
        assert rec.is_ambiguous is False
        assert rec.normalized_value == "2021-04-15"

        rec2 = normalize_date("2022-11-20")
        assert rec2.normalized_value == "2022-11-20"

        rec3 = normalize_date("15th April, 2023")
        assert rec3.normalized_value == "2023-04-15"

    def test_date_ambiguous_numeric_flags_review(self):
        # 03/04/2024 -> could be March 4 or April 3; must NOT guess!
        rec = normalize_date("03/04/2024")
        assert rec.is_valid_format is True
        assert rec.is_ambiguous is True
        assert rec.penalty > 0.0
        assert "Ambiguous date format" in rec.summary_note

    def test_entity_name_preserves_legal_suffixes(self):
        rec = normalize_entity_name("  M/s Apex Solutions Pvt. Ltd.  ")
        assert rec.is_valid_format is True
        assert rec.normalized_value == "Apex Solutions Pvt. Ltd."
        assert "Pvt. Ltd." in rec.normalized_value

    def test_entity_name_rejects_empty_or_too_short(self):
        rec = normalize_entity_name("X")
        assert rec.is_valid_format is False
        assert rec.penalty > 0.0

    def test_address_normalization_repairs_hyphenated_breaks(self):
        raw = "Plot 42, MIDC Indus-\ntrial Area, Andheri East, Mumbai 400093"
        rec = normalize_address(raw)
        assert rec.is_valid_format is True
        assert "Industrial Area" in rec.normalized_value
        assert "\n" not in rec.normalized_value

    def test_ifsc_normalization_and_repair(self):
        rec = normalize_ifsc("hdfc0001234")
        assert rec.is_valid_format is True
        assert rec.normalized_value == "HDFC0001234"

        # Position 4 is letter 'O' instead of digit '0'
        rec_repaired = normalize_ifsc("HDFCO001234")
        assert rec_repaired.is_valid_format is True
        assert rec_repaired.normalized_value == "HDFC0001234"
        assert rec_repaired.was_repaired is True

    def test_account_number_masking_and_dummy_rejection(self):
        rec = normalize_account_number("50100234567890")
        assert rec.is_valid_format is True
        assert rec.masked_value == "**********7890"
        assert rec.raw_value == "[REDACTED]"

        rec_dummy = normalize_account_number("000000000000")
        assert rec_dummy.is_valid_format is False
        assert "Dummy" in rec_dummy.summary_note


# ---------------------------------------------------------------------------
# Test Confidence & Quality Assessor
# ---------------------------------------------------------------------------

class TestConfidenceAndQualityAssessor:
    """Tests explainable quality scoring formulas, thresholds, and signal breakdowns."""

    def test_high_quality_digital_field(self):
        assessment = quality_assessor.evaluate_field(
            field_name="gstin",
            value="27AAACA9999A1Z5",
            extraction_method="DIGITAL_TEXT",
            raw_ocr_confidence=None,
            has_label_match=True,
            is_exact_label=True,
            is_valid_format=True,
            is_ambiguous=False,
            was_repaired=False,
            repaired_notes=[],
            candidate_count=1,
            has_page=True,
            has_location=True,
            has_snippet=True,
        )
        assert assessment.quality_score >= HIGH_CONFIDENCE_THRESHOLD
        assert assessment.status == FieldStatus.EXTRACTED
        assert assessment.breakdown.source_quality >= 0.95
        assert assessment.breakdown.label_match == 1.0
        assert assessment.breakdown.format_validity == 1.0
        assert "High evidence quality" in assessment.explanation

    def test_ocr_correction_lowers_confidence_and_flags_review(self):
        assessment = quality_assessor.evaluate_field(
            field_name="gstin",
            value="09AAACA1234A1Z5",
            extraction_method="OCR",
            raw_ocr_confidence=0.88,
            has_label_match=True,
            is_exact_label=True,
            is_valid_format=True,
            is_ambiguous=False,
            was_repaired=True,
            repaired_notes=["O->0 at pos 0"],
            candidate_count=1,
            has_page=True,
            has_location=True,
            has_snippet=True,
        )
        assert assessment.status == FieldStatus.NEEDS_REVIEW
        assert "OCR character repair applied" in assessment.explanation
        assert assessment.breakdown.normalization_adjustment < 1.0

    def test_ambiguous_date_flags_review(self):
        assessment = quality_assessor.evaluate_field(
            field_name="registration_date",
            value="03/04/2024",
            extraction_method="DIGITAL_TEXT",
            raw_ocr_confidence=None,
            has_label_match=True,
            is_exact_label=True,
            is_valid_format=True,
            is_ambiguous=True,
            was_repaired=False,
            repaired_notes=[],
            candidate_count=1,
            has_page=True,
            has_location=True,
            has_snippet=True,
        )
        assert assessment.status == FieldStatus.NEEDS_REVIEW
        assert "Ambiguous value format" in assessment.explanation

    def test_multiple_candidates_ambiguity_penalty(self):
        assessment = quality_assessor.evaluate_field(
            field_name="gstin",
            value="27AAACA9999A1Z5",
            extraction_method="DIGITAL_TEXT",
            raw_ocr_confidence=None,
            has_label_match=True,
            is_exact_label=True,
            is_valid_format=True,
            is_ambiguous=False,
            was_repaired=False,
            repaired_notes=[],
            candidate_count=2,  # 2 competing GSTINs
            has_page=True,
            has_location=True,
            has_snippet=True,
        )
        assert assessment.status == FieldStatus.NEEDS_REVIEW
        assert assessment.breakdown.ambiguity_penalty == 0.60
        assert "Multiple candidate values detected" in assessment.explanation

    def test_unreadable_field_assessment(self):
        assessment = quality_assessor.evaluate_field(
            field_name="account_number",
            value=None,
            extraction_method="OCR",
            raw_ocr_confidence=0.30,
            has_label_match=True,
            is_exact_label=True,
            is_valid_format=False,
            is_ambiguous=False,
            was_repaired=False,
            repaired_notes=[],
            candidate_count=0,
            has_page=True,
            has_location=True,
            has_snippet=True,
            is_unreadable=True,
        )
        assert assessment.status == FieldStatus.UNREADABLE
        assert assessment.quality_score < LOW_CONFIDENCE_THRESHOLD
        assert "illegible or unreadable" in assessment.explanation

    def test_missing_field_assessment(self):
        assessment = quality_assessor.evaluate_field(
            field_name="registration_date",
            value=None,
            extraction_method=None,
            raw_ocr_confidence=None,
            has_label_match=False,
            is_exact_label=False,
            is_valid_format=False,
            is_ambiguous=False,
            was_repaired=False,
            repaired_notes=[],
            candidate_count=0,
            has_page=False,
            has_location=False,
            has_snippet=False,
        )
        assert assessment.status == FieldStatus.MISSING
        assert assessment.quality_score == 0.0

    def test_deterministic_reproducibility(self):
        a1 = quality_assessor.evaluate_field(
            field_name="gstin",
            value="27AAACA9999A1Z5",
            extraction_method="DIGITAL_TEXT",
            raw_ocr_confidence=None,
            has_label_match=True,
            is_exact_label=True,
            is_valid_format=True,
            is_ambiguous=False,
            was_repaired=False,
            repaired_notes=[],
            candidate_count=1,
            has_page=True,
            has_location=True,
            has_snippet=True,
        )
        a2 = quality_assessor.evaluate_field(
            field_name="gstin",
            value="27AAACA9999A1Z5",
            extraction_method="DIGITAL_TEXT",
            raw_ocr_confidence=None,
            has_label_match=True,
            is_exact_label=True,
            is_valid_format=True,
            is_ambiguous=False,
            was_repaired=False,
            repaired_notes=[],
            candidate_count=1,
            has_page=True,
            has_location=True,
            has_snippet=True,
        )
        assert a1.quality_score == a2.quality_score
        assert a1.breakdown.model_dump() == a2.breakdown.model_dump()
        assert a1.status == a2.status


# ---------------------------------------------------------------------------
# Test Document Page Preview API
# ---------------------------------------------------------------------------

class TestDocumentPagePreviewAPI:
    """Tests dynamic page rendering, headers, boundaries, and cross-vendor isolation."""

    @pytest.fixture
    def test_vendor(self, client: TestClient):
        unique_reg = f"U72200DL2024PTC{uuid.uuid4().hex[:6].upper()}"
        payload = {
            "legal_name": "Preview Testing Corp",
            "trade_name": "Preview Testing",
            "business_type": "Private Limited",
            "country_of_incorporation": "India",
            "registration_number": unique_reg,
            "contact_name": "Rohan Gupta",
            "contact_email": f"rohan.{uuid.uuid4().hex[:4]}@previewtest.com",
            "contact_phone": "+919876543210",
            "address_line1": "123 Tech Park",
            "city": "Mumbai",
            "state_province": "Maharashtra",
            "postal_code": "400093",
            "address_country": "India",
            "tax_id_type": "GSTIN",
            "tax_id_number": "27AAACA9999A1Z5",
            "bank_account_number": "50100987654321",
            "bank_routing_number": "HDFC0001234",
            "bank_name": "HDFC Bank",
            "bank_account_holder_name": "Preview Testing Corp",
            "bank_country": "India",
        }
        res = client.post("/api/v1/vendors", json=payload)
        assert res.status_code == 201, res.text
        return res.json()

    @pytest.fixture
    def test_image_doc(self, client: TestClient, test_vendor: dict):
        # Create a simple test PNG
        img = Image.new("RGB", (400, 300), color=(240, 240, 245))
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), "Test Image Document", fill=(0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        vendor_id = test_vendor["id"]
        res = client.post(
            f"/api/v1/vendors/{vendor_id}/documents",
            files={"file": ("test_doc.png", png_bytes, "image/png")},
            data={"document_category": "BANK_PROOF"},
        )
        assert res.status_code == 201
        return res.json()

    def test_preview_image_document_success(self, client: TestClient, test_vendor: dict, test_image_doc: dict):
        vendor_id = test_vendor["id"]
        doc_id = test_image_doc["id"]

        res = client.get(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/pages/1/preview")
        assert res.status_code == 200
        assert res.headers["content-type"] == "image/png"
        assert res.headers["x-total-pages"] == "1"
        assert res.headers["x-current-page"] == "1"
        assert "private, no-store" in res.headers["cache-control"]
        assert len(res.content) > 0

    def test_preview_invalid_page_number_rejected(self, client: TestClient, test_vendor: dict, test_image_doc: dict):
        vendor_id = test_vendor["id"]
        doc_id = test_image_doc["id"]

        # Page 2 on a 1-page image
        res = client.get(f"/api/v1/vendors/{vendor_id}/documents/{doc_id}/pages/2/preview")
        assert res.status_code == 400
        assert "only has 1 page" in res.json()["detail"]

    def test_preview_cross_vendor_access_rejected(self, client: TestClient, test_vendor: dict, test_image_doc: dict):
        other_vendor_id = str(uuid.uuid4())
        doc_id = test_image_doc["id"]

        # Attempt to access document using a different vendor ID
        res = client.get(f"/api/v1/vendors/{other_vendor_id}/documents/{doc_id}/pages/1/preview")
        assert res.status_code == 404
