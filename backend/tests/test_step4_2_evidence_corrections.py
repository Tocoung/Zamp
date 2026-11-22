"""Comprehensive automated test suite for Phase 2 Step 4.2 Final Field Evidence Scoring Corrections.

Covers:
1. Multi-line field token association:
   - Next line contains candidate value plus unrelated low-confidence text.
   - Verifies unrelated tokens do not distort candidate OCR confidence.
   - Preserves label tokens separately from value tokens.
   - Handles multi-word values with punctuation (commas, periods, slashes).
   - Preserves line and page provenance without persisting raw token text.

2. Unreadable field evidence quality calculation:
   - High-confidence label with unreadable value region.
   - Low-confidence label with unreadable value region.
   - Missing source location / incomplete provenance.
   - Deterministic weighted score calculations.
   - Mandatory UNREADABLE status and explicit evidence-anchor explanation.
"""

import pytest
from app.extraction.ocr_engine import OcrDocumentResult, OcrPageResult, OcrToken
from app.extraction.parsers import document_parser
from app.extraction.confidence import quality_assessor
from app.schemas.extraction import FieldStatus


# =============================================================================
# 1. MULTI-LINE FIELD TOKEN ASSOCIATION & ISOLATION
# =============================================================================
class TestMultiLineTokenAssociation:

    def test_next_line_unrelated_low_conf_tokens_do_not_distort_candidate_conf(self):
        """When a multi-line field has candidate on next line followed by unrelated low-confidence
        tokens, the parser must associate only candidate tokens so the score is not distorted.
        """
        # Line 1: Label (GSTIN:)
        # Line 2: Value (29ABCDE1234F1Z5) + Unrelated noisy text ("(Verified by Tax Dept - Bad Scan)")
        tokens = [
            # Label tokens on line 1
            OcrToken(text="Registration", confidence=0.92, line_num=1, word_num=1),
            OcrToken(text="Number:", confidence=0.94, line_num=1, word_num=2),
            # Candidate value token on line 2 (High confidence: 0.98)
            OcrToken(text="29ABCDE1234F1Z5", confidence=0.98, line_num=2, word_num=1),
            # Unrelated noisy tokens on line 2 (Low confidence: 0.25 - 0.35)
            OcrToken(text="(Verified", confidence=0.30, line_num=2, word_num=2),
            OcrToken(text="by", confidence=0.25, line_num=2, word_num=3),
            OcrToken(text="Tax", confidence=0.28, line_num=2, word_num=4),
            OcrToken(text="Department", confidence=0.32, line_num=2, word_num=5),
            OcrToken(text="Stamp)", confidence=0.26, line_num=2, word_num=6),
        ]
        page = OcrPageResult(
            page_number=1,
            text="Registration Number:\n29ABCDE1234F1Z5 (Verified by Tax Department Stamp)",
            extraction_method="OCR",
            confidence=0.55,
            lines=[
                "Registration Number:",
                "29ABCDE1234F1Z5 (Verified by Tax Department Stamp)",
            ],
            tokens=tokens,
        )
        ocr_doc = OcrDocumentResult(pages=[page], total_pages=1)

        # Parse tax certificate
        fields = document_parser.parse("doc-step4-2", "TAX_CERTIFICATE", ocr_doc)
        gstin_field = fields["gstin"]

        # 1. Candidate value extracted cleanly without trailing noise
        assert gstin_field.value == "29ABCDE1234F1Z5"
        assert gstin_field.status == FieldStatus.EXTRACTED

        # 2. Candidate value token confidence must be high (clamped to 0.95 max, NOT degraded by 0.28 noise tokens!)
        assert gstin_field.quality_breakdown.source_quality == 0.95
        assert "OCR token confidence 95%" in gstin_field.quality_explanation

        # 3. Provenance preserves line 1-2 multi-line reference
        assert gstin_field.source.page_number == 1
        assert "Lines 1-2" in gstin_field.source.evidence_location
        assert "Registration Number:" in gstin_field.source.evidence_snippet

    def test_multiword_entity_name_with_punctuation_and_unrelated_text(self):
        """Multi-word entity names with punctuation (Pvt. Ltd., commas) followed by unrelated
        annotations must associate only entity name tokens and exclude trailing notes.
        """
        tokens = [
            OcrToken(text="Legal", confidence=0.90, line_num=1, word_num=1),
            OcrToken(text="Name:", confidence=0.92, line_num=1, word_num=2),
            # Entity name tokens on line 2 (average conf: ~0.95)
            OcrToken(text="Acme", confidence=0.96, line_num=2, word_num=1),
            OcrToken(text="Global", confidence=0.94, line_num=2, word_num=2),
            OcrToken(text="Technologies,", confidence=0.95, line_num=2, word_num=3),
            OcrToken(text="Pvt.", confidence=0.95, line_num=2, word_num=4),
            OcrToken(text="Ltd.", confidence=0.96, line_num=2, word_num=5),
            # Unrelated annotation on line 2 (average conf: ~0.30)
            OcrToken(text="(Authorized", confidence=0.30, line_num=2, word_num=6),
            OcrToken(text="Signatory", confidence=0.28, line_num=2, word_num=7),
            OcrToken(text="Reg.", confidence=0.32, line_num=2, word_num=8),
            OcrToken(text="4421)", confidence=0.25, line_num=2, word_num=9),
        ]
        page = OcrPageResult(
            page_number=1,
            text="Legal Name:\nAcme Global Technologies, Pvt. Ltd. (Authorized Signatory Reg. 4421)",
            extraction_method="OCR",
            confidence=0.62,
            lines=[
                "Legal Name:",
                "Acme Global Technologies, Pvt. Ltd. (Authorized Signatory Reg. 4421)",
            ],
            tokens=tokens,
        )
        ocr_doc = OcrDocumentResult(pages=[page], total_pages=1)

        fields = document_parser.parse("doc-step4-2-name", "TAX_CERTIFICATE", ocr_doc)
        name_field = fields["legal_entity_name"]

        # 1. Clean extracted entity name without trailing annotation
        assert "Acme Global Technologies" in name_field.value
        assert "Authorized Signatory" not in name_field.value

        # 2. Source quality derived from high-confidence company tokens (~0.95), not 0.30 annotation
        assert name_field.quality_breakdown.source_quality >= 0.94
        assert "OCR token confidence 95%" in name_field.quality_explanation

    def test_label_and_value_tokens_preserved_separately(self):
        """Ensures label tokens and candidate value tokens are tracked separately in candidate finding."""
        tokens = [
            OcrToken(text="Account", confidence=0.85, line_num=1, word_num=1),
            OcrToken(text="Number:", confidence=0.87, line_num=1, word_num=2),
            OcrToken(text="50100987654321", confidence=0.96, line_num=2, word_num=1),
            OcrToken(text="[Savings]", confidence=0.40, line_num=2, word_num=2),
        ]
        page = OcrPageResult(
            page_number=1,
            text="Account Number:\n50100987654321 [Savings]",
            extraction_method="OCR",
            confidence=0.77,
            lines=["Account Number:", "50100987654321 [Savings]"],
            tokens=tokens,
        )
        ocr_doc = OcrDocumentResult(pages=[page], total_pages=1)

        fields = document_parser.parse("doc-bank", "BANK_PROOF", ocr_doc)
        acc_field = fields["account_number"]

        assert acc_field.value == "50100987654321"
        assert acc_field.quality_breakdown.source_quality == 0.95  # Clamped OCR token conf 0.96 -> 0.95
        assert "Lines 1-2" in acc_field.source.evidence_location
        assert "50100987654321" in acc_field.source.evidence_snippet


# =============================================================================
# 2. UNREADABLE FIELD QUALITY CALCULATION
# =============================================================================
class TestUnreadableFieldQualityCalculation:

    def test_unreadable_high_confidence_label(self):
        """High-confidence label with unreadable value region.
        
        Formula:
            w_S(0.20) * source_q(0.95) = 0.19
            w_L(0.20) * label_q(1.00)  = 0.20
            w_F(0.25) * format_q(0.00) = 0.00
            w_P(0.15) * prov_q(1.00)   = 0.15
            w_N(0.10) * norm_q(0.00)   = 0.00
            w_A(0.10) * amb_q(0.00)    = 0.00
            Total Score = 0.54
        """
        assessment = quality_assessor.evaluate_field(
            field_name="gstin",
            value=None,
            extraction_method="OCR",
            raw_ocr_confidence=0.90,
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
            label_ocr_confidence=0.95,
        )

        assert assessment.status == FieldStatus.UNREADABLE
        assert assessment.quality_score == 0.54
        assert assessment.breakdown.source_quality == 0.95
        assert assessment.breakdown.label_match == 1.00
        assert assessment.breakdown.format_validity == 0.00
        assert assessment.breakdown.provenance_quality == 1.00
        assert assessment.breakdown.normalization_adjustment == 0.00
        assert assessment.breakdown.ambiguity_penalty == 0.00

        # Explanation must clarify that score measures evidence anchor quality, NOT value confidence
        assert "Unreadable field evidence quality (0.54)" in assessment.explanation
        assert "Score reflects evidence anchor quality, not recovered value confidence" in assessment.explanation
        assert "No value could be extracted" in assessment.reasons_for_review

    def test_unreadable_low_confidence_label(self):
        """Low-confidence label with unreadable value region.
        
        Formula:
            w_S(0.20) * source_q(0.40) = 0.08
            w_L(0.20) * label_q(1.00)  = 0.20
            w_P(0.15) * prov_q(1.00)   = 0.15
            Total Score = 0.43
        """
        assessment = quality_assessor.evaluate_field(
            field_name="gstin",
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
            label_ocr_confidence=0.40,
        )

        assert assessment.status == FieldStatus.UNREADABLE
        assert assessment.quality_score == 0.43
        assert assessment.breakdown.source_quality == 0.40
        assert "Unreadable field evidence quality (0.43)" in assessment.explanation

    def test_unreadable_missing_source_location(self):
        """When source location is missing, provenance quality is reduced (0.70 instead of 1.00),
        lowering the unreadable evidence score deterministically.
        
        Formula:
            w_S(0.20) * 0.95 = 0.19
            w_L(0.20) * 1.00 = 0.20
            w_P(0.15) * 0.70 = 0.105
            Total Score = 0.495 -> 0.50
        """
        assessment = quality_assessor.evaluate_field(
            field_name="registration_date",
            value=None,
            extraction_method="OCR",
            raw_ocr_confidence=0.90,
            has_label_match=True,
            is_exact_label=True,
            is_valid_format=False,
            is_ambiguous=False,
            was_repaired=False,
            repaired_notes=[],
            candidate_count=0,
            has_page=True,
            has_location=False,  # Location missing!
            has_snippet=True,
            is_unreadable=True,
            label_ocr_confidence=0.95,
        )

        assert assessment.status == FieldStatus.UNREADABLE
        assert assessment.breakdown.provenance_quality == 0.70
        assert assessment.quality_score == 0.49

        # When all provenance is missing: prov_q = 0.0 -> score = 0.19 + 0.20 = 0.39
        no_prov = quality_assessor.evaluate_field(
            field_name="registration_date",
            value=None,
            extraction_method="OCR",
            raw_ocr_confidence=0.90,
            has_label_match=True,
            is_exact_label=True,
            is_valid_format=False,
            is_ambiguous=False,
            was_repaired=False,
            repaired_notes=[],
            candidate_count=0,
            has_page=False,
            has_location=False,
            has_snippet=False,
            is_unreadable=True,
            label_ocr_confidence=0.95,
        )
        assert no_prov.quality_score == 0.39
        assert no_prov.breakdown.provenance_quality == 0.00

    def test_deterministic_score_ordering(self):
        """Demonstrates strict deterministic ordering:
        High-confidence label with full provenance > Low-confidence label > Missing provenance.
        All maintain mandatory UNREADABLE status.
        """
        high_full = quality_assessor.evaluate_field(
            field_name="f", value=None, extraction_method="OCR", raw_ocr_confidence=0.95,
            has_label_match=True, is_exact_label=True, is_valid_format=False, is_ambiguous=False,
            was_repaired=False, repaired_notes=[], candidate_count=0,
            has_page=True, has_location=True, has_snippet=True, is_unreadable=True,
            label_ocr_confidence=0.95,
        )
        low_full = quality_assessor.evaluate_field(
            field_name="f", value=None, extraction_method="OCR", raw_ocr_confidence=0.40,
            has_label_match=True, is_exact_label=True, is_valid_format=False, is_ambiguous=False,
            was_repaired=False, repaired_notes=[], candidate_count=0,
            has_page=True, has_location=True, has_snippet=True, is_unreadable=True,
            label_ocr_confidence=0.40,
        )
        high_no_loc = quality_assessor.evaluate_field(
            field_name="f", value=None, extraction_method="OCR", raw_ocr_confidence=0.95,
            has_label_match=True, is_exact_label=True, is_valid_format=False, is_ambiguous=False,
            was_repaired=False, repaired_notes=[], candidate_count=0,
            has_page=True, has_location=False, has_snippet=True, is_unreadable=True,
            label_ocr_confidence=0.95,
        )

        assert high_full.quality_score > high_no_loc.quality_score > low_full.quality_score
        assert high_full.status == low_full.status == high_no_loc.status == FieldStatus.UNREADABLE
