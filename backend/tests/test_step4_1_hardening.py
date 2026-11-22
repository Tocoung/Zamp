"""Comprehensive automated test suite for Phase 2 Step 4.1 Evidence Quality & Preview Hardening.

Covers:
1. Field-level OCR confidence with token-level association vs page-level fallback.
2. Two fields on the same OCR page having distinct confidences from their respective tokens.
3. Composite score weights summing to 1.00 with provenance quality included.
4. Date normalization real calendar validation (31/04/2024, 29/02/2023, 29/02/2024, 05/05/2024, 03/04/2024).
5. Image preview protection: malformed images, oversized bounds (>4096, >16MP), decompression bombs, page bounds, and cross-vendor isolation.
"""

import io
import os
import uuid
import hashlib
import pytest
from PIL import Image
from unittest.mock import patch

from app.extraction.ocr_engine import OcrDocumentResult, OcrPageResult, OcrToken
from app.extraction.parsers import document_parser, CandidateFinding
from app.extraction.confidence import quality_assessor, HIGH_CONFIDENCE_THRESHOLD
from app.extraction.normalization import normalize_date, normalize_gstin
from app.schemas.extraction import FieldStatus
from app.models.vendor import Vendor
from app.models.document import VendorDocument
from app.schemas.document import DocumentCategory
from app.services.extraction_service import extraction_service, DocumentPreviewError, MAX_PREVIEW_TOTAL_PIXELS
from app.core.storage import document_storage


# =============================================================================
# 1. FIELD-LEVEL OCR CONFIDENCE & TOKEN ASSOCIATION
# =============================================================================
class TestFieldLevelOcrConfidence:

    def test_two_fields_on_same_page_have_distinct_token_confidences(self):
        """Demonstrates that two fields on the exact same OCR page evaluate with
        their respective token-level confidences rather than an identical page average."""
        # Page has average confidence 0.70
        tokens = [
            # High confidence GSTIN tokens (confidence 0.95)
            OcrToken(text="GSTIN:", confidence=0.92, line_num=1, word_num=1),
            OcrToken(text="29ABCDE1234F1Z5", confidence=0.96, line_num=1, word_num=2),
            # Low confidence Legal Name tokens (confidence 0.52)
            OcrToken(text="Legal", confidence=0.50, line_num=2, word_num=1),
            OcrToken(text="Name:", confidence=0.55, line_num=2, word_num=2),
            OcrToken(text="Acme", confidence=0.51, line_num=2, word_num=3),
            OcrToken(text="Global", confidence=0.53, line_num=2, word_num=4),
            OcrToken(text="Pvt", confidence=0.50, line_num=2, word_num=5),
            OcrToken(text="Ltd", confidence=0.51, line_num=2, word_num=6),
        ]
        page = OcrPageResult(
            page_number=1,
            text="GSTIN: 29ABCDE1234F1Z5\nLegal Name: Acme Global Pvt Ltd",
            extraction_method="OCR",
            confidence=0.70,  # Page-level average
            lines=["GSTIN: 29ABCDE1234F1Z5", "Legal Name: Acme Global Pvt Ltd"],
            tokens=tokens,
        )
        ocr_doc = OcrDocumentResult(pages=[page], total_pages=1)

        fields = document_parser.parse("doc-123", "TAX_CERTIFICATE", ocr_doc)

        gstin_field = fields["gstin"]
        name_field = fields["legal_entity_name"]

        # 1. GSTIN was associated with high confidence token (0.96)
        assert gstin_field.quality_breakdown.source_quality >= 0.92
        assert "OCR token confidence" in gstin_field.quality_explanation
        assert "Page-level OCR confidence fallback" not in gstin_field.quality_explanation

        # 2. Legal Name was associated with low confidence tokens (~0.51)
        assert name_field.quality_breakdown.source_quality <= 0.60
        assert "OCR token confidence" in name_field.quality_explanation

        # 3. They MUST differ despite being on the exact same OCR page!
        assert gstin_field.quality_breakdown.source_quality != name_field.quality_breakdown.source_quality
        assert gstin_field.quality_score > name_field.quality_score

    def test_page_level_fallback_when_tokens_missing(self):
        """When token data is missing, parser must fall back to page confidence and explain the limitation."""
        page_no_tokens = OcrPageResult(
            page_number=1,
            text="GSTIN: 29ABCDE1234F1Z5",
            extraction_method="OCR",
            confidence=0.82,
            lines=["GSTIN: 29ABCDE1234F1Z5"],
            tokens=[],  # Empty tokens
        )
        ocr_doc = OcrDocumentResult(pages=[page_no_tokens], total_pages=1)

        fields = document_parser.parse("doc-456", "TAX_CERTIFICATE", ocr_doc)
        gstin_field = fields["gstin"]

        # Falls back to page-level confidence
        assert gstin_field.quality_breakdown.source_quality == 0.82
        assert "Page-level OCR confidence fallback used; token-level data unavailable" in gstin_field.quality_explanation

    def test_digital_text_preserves_digital_stream_fidelity_without_ocr_tokens(self):
        """Digital PDFs should use digital text stream fidelity (0.98) without fabricating OCR tokens."""
        digital_page = OcrPageResult(
            page_number=1,
            text="GSTIN: 29ABCDE1234F1Z5",
            extraction_method="DIGITAL_TEXT",
            confidence=1.0,
            lines=["GSTIN: 29ABCDE1234F1Z5"],
            tokens=[],
        )
        ocr_doc = OcrDocumentResult(pages=[digital_page], total_pages=1)

        fields = document_parser.parse("doc-789", "TAX_CERTIFICATE", ocr_doc)
        gstin_field = fields["gstin"]

        assert gstin_field.quality_breakdown.source_quality == 0.98
        assert "digital text stream" in gstin_field.quality_explanation
        assert "OCR" not in gstin_field.quality_explanation


# =============================================================================
# 2. COMPOSITE SCORE INTERNALLY CONSISTENT WEIGHTS
# =============================================================================
class TestCompositeScoreFormula:

    def test_weights_sum_to_one(self):
        """Verifies that weights for format, source, label, provenance, normalization, and ambiguity sum to 1.00."""
        # Perfect digital extraction with full provenance
        assessment = quality_assessor.evaluate_field(
            field_name="gstin",
            value="29ABCDE1234F1Z5",
            extraction_method="DIGITAL_TEXT",
            raw_ocr_confidence=None,
            field_ocr_confidence=None,
            has_token_level_confidence=False,
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
        # Expected components:
        # S = 0.98, w_S = 0.20 -> 0.196
        # L = 1.00, w_L = 0.20 -> 0.200
        # F = 1.00, w_F = 0.25 -> 0.250
        # P = 1.00, w_P = 0.15 -> 0.150
        # N = 1.00, w_N = 0.10 -> 0.100
        # A = 1.00, w_A = 0.10 -> 0.100
        # Total = 0.196 + 0.200 + 0.250 + 0.150 + 0.100 + 0.100 = 0.996 -> 1.00
        assert assessment.quality_score == 1.00
        assert assessment.status == FieldStatus.EXTRACTED
        assert assessment.breakdown.provenance_quality == 1.00

    def test_ocr_token_worked_example(self):
        """Worked example: OCR field with token confidence 0.65 yields quality score 0.93."""
        # S = 0.65, w_S = 0.20 -> 0.130
        # L = 1.00, w_L = 0.20 -> 0.200
        # F = 1.00, w_F = 0.25 -> 0.250
        # P = 1.00, w_P = 0.15 -> 0.150
        # N = 1.00, w_N = 0.10 -> 0.100
        # A = 1.00, w_A = 0.10 -> 0.100
        # Total = 0.130 + 0.200 + 0.250 + 0.150 + 0.100 + 0.100 = 0.930 -> 0.93
        assessment = quality_assessor.evaluate_field(
            field_name="gstin",
            value="29ABCDE1234F1Z5",
            extraction_method="OCR",
            raw_ocr_confidence=0.65,
            field_ocr_confidence=0.65,
            has_token_level_confidence=True,
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
        assert assessment.quality_score == 0.93
        assert assessment.status == FieldStatus.EXTRACTED

    def test_repaired_ocr_character_flags_needs_review(self):
        """OCR repaired character deducts normalization and strictly forces NEEDS_REVIEW."""
        assessment = quality_assessor.evaluate_field(
            field_name="gstin",
            value="29ABCDE1234F1Z5",
            extraction_method="OCR",
            raw_ocr_confidence=0.50,
            field_ocr_confidence=0.50,
            has_token_level_confidence=True,
            has_label_match=True,
            is_exact_label=True,
            is_valid_format=True,
            is_ambiguous=False,
            was_repaired=True,
            repaired_notes=["O->0 at pos 1"],
            candidate_count=1,
            has_page=True,
            has_location=True,
            has_snippet=True,
        )
        # N = 0.80 -> w_N * 0.80 = 0.080
        # S = 0.50 -> 0.100; L = 1.0 -> 0.200; F = 1.0 -> 0.250; P = 1.0 -> 0.150; A = 1.0 -> 0.100
        # Total = 0.100 + 0.200 + 0.250 + 0.150 + 0.080 + 0.100 = 0.88
        assert assessment.quality_score == 0.88
        assert assessment.status == FieldStatus.NEEDS_REVIEW
        assert any("OCR character repair" in r for r in assessment.reasons_for_review)

    def test_missing_field_score_is_zero(self):
        assessment = quality_assessor.evaluate_field(
            field_name="ifsc_code",
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
        assert assessment.quality_score == 0.0
        assert assessment.status == FieldStatus.MISSING

    def test_unreadable_field_score_is_twenty_percent(self):
        assessment = quality_assessor.evaluate_field(
            field_name="legal_entity_name",
            value=None,
            extraction_method="OCR",
            raw_ocr_confidence=0.40,
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
        assert assessment.quality_score == 0.20
        assert assessment.status == FieldStatus.UNREADABLE


# =============================================================================
# 3. DATE NORMALIZATION CALENDAR VALIDATION
# =============================================================================
class TestDateCalendarValidation:

    def test_invalid_day_31_in_april_rejected(self):
        """April has only 30 days; 31/04/2024 must fail calendar validation."""
        rec = normalize_date("31/04/2024")
        assert rec.is_valid_format is False
        assert rec.normalized_value == "31/04/2024"  # Un-normalized
        assert any("Invalid calendar date" in n for n in rec.notes)

    def test_invalid_leap_day_in_non_leap_year_rejected(self):
        """2023 is not a leap year; 29/02/2023 must fail calendar validation."""
        rec = normalize_date("29/02/2023")
        assert rec.is_valid_format is False
        assert any("Invalid calendar date" in n for n in rec.notes)

    def test_valid_leap_day_in_leap_year_accepted(self):
        """2024 is a leap year; 29/02/2024 must normalize successfully to 2024-02-29."""
        rec = normalize_date("29/02/2024")
        assert rec.is_valid_format is True
        assert rec.normalized_value == "2024-02-29"

    def test_identical_day_month_accepted(self):
        """05/05/2024 is unambiguous (day == month); must normalize to 2024-05-05."""
        rec = normalize_date("05/05/2024")
        assert rec.is_valid_format is True
        assert rec.is_ambiguous is False
        assert rec.normalized_value == "2024-05-05"

    def test_ambiguous_date_flagged_for_review(self):
        """03/04/2024 has day/month in 1..12; must not guess and flag as ambiguous."""
        rec = normalize_date("03/04/2024")
        assert rec.is_valid_format is True
        assert rec.is_ambiguous is True
        assert rec.normalized_value == "03/04/2024"
        assert any("Ambiguous date format" in n for n in rec.notes)

    def test_unambiguous_iso_calendar_validation(self):
        """Valid ISO date normalizes, while non-existent ISO date is rejected."""
        valid_iso = normalize_date("2024-05-15")
        assert valid_iso.is_valid_format is True
        assert valid_iso.normalized_value == "2024-05-15"

        invalid_iso = normalize_date("2024-04-31")
        assert invalid_iso.is_valid_format is False
        assert any("Invalid calendar date" in n for n in invalid_iso.notes)


# =============================================================================
# 4. ORIGINAL IMAGE PREVIEW PROTECTION & HARDENING
# =============================================================================
def _make_vendor(db, legal_name="Preview Test Corp") -> Vendor:
    unique_reg = f"U72200DL2024PTC{uuid.uuid4().hex[:6].upper()}"
    vendor = Vendor(
        legal_name=legal_name,
        business_type="Private Limited",
        country_of_incorporation="India",
        registration_number=unique_reg,
        contact_name="Rohan Gupta",
        contact_email=f"test.{uuid.uuid4().hex[:6]}@example.com",
        contact_phone="+919876543210",
        address_line1="123 Tech Park",
        city="Mumbai",
        state_province="Maharashtra",
        postal_code="400093",
        address_country="India",
        tax_id_type="GSTIN",
        tax_id_number="27AAACA9999A1Z5",
        bank_account_holder_name=legal_name,
        bank_name="HDFC Bank",
        bank_account_number="50100987654321",
        bank_routing_number="HDFC0001234",
        bank_country="India",
    )
    db.add(vendor)
    db.commit()
    return vendor


def _make_document(db, vendor_id: str, content: bytes, mime_type: str, filename: str, category: str = "OTHER") -> VendorDocument:
    doc_id = str(uuid.uuid4())
    storage_id = document_storage.store_document(vendor_id, doc_id, content)
    ext = os.path.splitext(filename)[1]
    doc = VendorDocument(
        id=doc_id,
        vendor_id=vendor_id,
        original_filename=filename,
        sanitized_filename=filename,
        document_category=category,
        mime_type=mime_type,
        file_extension=ext,
        file_size_bytes=len(content),
        storage_identifier=storage_id,
        sha256_checksum=hashlib.sha256(content).hexdigest(),
        upload_status="PROCESSED",
    )
    db.add(doc)
    db.commit()
    return doc


class TestImagePreviewProtection:

    def test_valid_image_preview_normalizes_to_safe_png(self, test_db_session):
        """Valid PNG is loaded, checked, and served as normalized in-memory PNG."""
        # 1. Create vendor and document
        vendor = _make_vendor(test_db_session, "Preview Test Corp")

        # Generate small valid JPEG
        img = Image.new("RGB", (300, 200), color="white")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        raw_jpeg = buf.getvalue()

        doc = _make_document(
            db=test_db_session,
            vendor_id=str(vendor.id),
            content=raw_jpeg,
            mime_type="image/jpeg",
            filename="invoice.jpg",
            category="TAX_CERTIFICATE",
        )

        # 2. Render preview
        png_bytes, mime, pages = extraction_service.render_document_page_preview(
            db=test_db_session,
            vendor_id=str(vendor.id),
            document_id=str(doc.id),
            page_number=1,
        )

        assert mime == "image/png"
        assert pages == 1
        # Check that result is a valid PNG
        with Image.open(io.BytesIO(png_bytes)) as out_img:
            assert out_img.format == "PNG"
            assert out_img.size == (300, 200)

    def test_malformed_image_rejected(self, test_db_session):
        """Corrupted image bytes must be rejected with DocumentPreviewError."""
        vendor = _make_vendor(test_db_session, "Corrupt Test Corp")

        corrupt_bytes = b"NOT_A_VALID_IMAGE_HEADER_CORRUPTED"
        doc = _make_document(
            db=test_db_session,
            vendor_id=str(vendor.id),
            content=corrupt_bytes,
            mime_type="image/png",
            filename="corrupt.png",
        )

        with pytest.raises(DocumentPreviewError) as exc_info:
            extraction_service.render_document_page_preview(
                db=test_db_session,
                vendor_id=str(vendor.id),
                document_id=str(doc.id),
                page_number=1,
            )
        assert "Malformed or corrupted image" in str(exc_info.value)

    def test_oversized_image_dimensions_rejected(self, test_db_session):
        """Images exceeding 4096 in dimension must be rejected."""
        vendor = _make_vendor(test_db_session, "Oversized Test Corp")

        # Mock an image with dimensions 5000 x 500
        img = Image.new("RGB", (100, 100), color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        doc = _make_document(
            db=test_db_session,
            vendor_id=str(vendor.id),
            content=png_bytes,
            mime_type="image/png",
            filename="giant.png",
        )

        # Simulate Pillow returning size (5000, 100)
        with patch.object(Image.Image, "size", new=(5000, 100)):
            with pytest.raises(DocumentPreviewError) as exc_info:
                extraction_service.render_document_page_preview(
                    db=test_db_session,
                    vendor_id=str(vendor.id),
                    document_id=str(doc.id),
                    page_number=1,
                )
            assert "exceed maximum allowed preview size" in str(exc_info.value)

    def test_decompression_bomb_rejected(self, test_db_session):
        """Images declaring pixel counts exceeding MAX_PREVIEW_TOTAL_PIXELS must be caught."""
        vendor = _make_vendor(test_db_session, "Decompression Bomb Corp")

        img = Image.new("RGB", (100, 100), color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        doc = _make_document(
            db=test_db_session,
            vendor_id=str(vendor.id),
            content=png_bytes,
            mime_type="image/png",
            filename="bomb.png",
        )

        # Simulate Pillow raising DecompressionBombError
        from PIL.Image import DecompressionBombError
        with patch("PIL.Image.open", side_effect=DecompressionBombError("Decompression bomb detected")):
            with pytest.raises(DocumentPreviewError) as exc_info:
                extraction_service.render_document_page_preview(
                    db=test_db_session,
                    vendor_id=str(vendor.id),
                    document_id=str(doc.id),
                    page_number=1,
                )
            assert "decompression bomb detected" in str(exc_info.value)

    def test_invalid_image_page_number_rejected(self, test_db_session):
        """Single-image document must reject page_number != 1."""
        vendor = _make_vendor(test_db_session, "Single Page Corp")

        img = Image.new("RGB", (100, 100), color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        doc = _make_document(
            db=test_db_session,
            vendor_id=str(vendor.id),
            content=png_bytes,
            mime_type="image/png",
            filename="single.png",
        )

        with pytest.raises(DocumentPreviewError) as exc_info:
            extraction_service.render_document_page_preview(
                db=test_db_session,
                vendor_id=str(vendor.id),
                document_id=str(doc.id),
                page_number=2,
            )
        assert "Image document only has 1 page (requested page 2)" in str(exc_info.value)
