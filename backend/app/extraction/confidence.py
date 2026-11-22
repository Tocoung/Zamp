"""Field-level evidence quality and confidence assessment engine."""

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
from app.schemas.extraction import FieldStatus, QualityBreakdown


# Configurable, justified thresholds
HIGH_CONFIDENCE_THRESHOLD = 0.75
LOW_CONFIDENCE_THRESHOLD = 0.50


@dataclass
class QualityAssessment:
    """Detailed explainable field-level extraction quality evaluation."""
    quality_score: float
    breakdown: QualityBreakdown
    status: FieldStatus
    explanation: str
    reasons_for_review: List[str]

    def to_dict(self) -> dict:
        return {
            "quality_score": self.quality_score,
            "breakdown": self.breakdown.model_dump(),
            "status": self.status.value,
            "explanation": self.explanation,
            "reasons_for_review": self.reasons_for_review,
        }


class QualityAssessor:
    """Evaluates field-level extraction evidence quality and confidence from concrete measured signals."""

    def evaluate_field(
        self,
        field_name: str,
        value: Optional[str],
        extraction_method: Optional[str],
        raw_ocr_confidence: Optional[float],
        has_label_match: bool,
        is_exact_label: bool,
        is_valid_format: bool,
        is_ambiguous: bool,
        was_repaired: bool,
        repaired_notes: List[str],
        candidate_count: int,
        has_page: bool,
        has_location: bool,
        has_snippet: bool,
        is_unreadable: bool = False,
        field_ocr_confidence: Optional[float] = None,
        has_token_level_confidence: bool = False,
        label_ocr_confidence: Optional[float] = None,
    ) -> QualityAssessment:
        """Computes deterministic quality score, signal breakdown, and explainable status.
        
        Composite formula weights (summing to 1.00):
            format_validity (w_F = 0.25)
            source_quality (w_S = 0.20)
            label_match (w_L = 0.20)
            provenance_quality (w_P = 0.15)
            normalization_adjustment (w_N = 0.10)
            ambiguity_penalty (w_A = 0.10)
        """
        # 1. Unreadable field handling (weighted signal evidence score)
        if is_unreadable:
            # Source quality of the detected anchor/label region
            if extraction_method == "DIGITAL_TEXT":
                source_q = 0.98
            elif extraction_method == "OCR":
                if label_ocr_confidence is not None:
                    source_q = min(0.95, max(0.20, float(label_ocr_confidence)))
                elif has_token_level_confidence and field_ocr_confidence is not None:
                    source_q = min(0.95, max(0.20, float(field_ocr_confidence)))
                elif raw_ocr_confidence is not None and raw_ocr_confidence > 0:
                    source_q = min(0.90, max(0.20, float(raw_ocr_confidence)))
                else:
                    source_q = 0.50
            else:
                source_q = float(raw_ocr_confidence or 0.40)

            # Label match signal
            if is_exact_label:
                label_q = 1.00
            elif has_label_match:
                label_q = 0.85
            else:
                label_q = 0.50

            # Format and normalization are 0.0 because value is unreadable
            format_q = 0.0
            norm_q = 0.0

            # Provenance signal
            prov_q = 0.0
            if has_page:
                prov_q += 0.50
            if has_location:
                prov_q += 0.30
            if has_snippet:
                prov_q += 0.20

            # Ambiguity: no extracted value candidate
            ambiguity_q = 0.0

            # Weighted composite score using documented weights:
            # 0.20 * source_q + 0.20 * label_q + 0.25 * format_q + 0.15 * prov_q + 0.10 * norm_q + 0.10 * ambiguity_q
            raw_score = (
                0.20 * source_q +
                0.20 * label_q +
                0.25 * format_q +
                0.15 * prov_q +
                0.10 * norm_q +
                0.10 * ambiguity_q
            )
            quality_score = round(raw_score, 2)

            breakdown = QualityBreakdown(
                source_quality=round(source_q, 2),
                label_match=round(label_q, 2),
                format_validity=0.0,
                normalization_adjustment=0.0,
                ambiguity_penalty=0.0,
                provenance_quality=round(prov_q, 2),
            )

            explanation = (
                f"Unreadable field evidence quality ({quality_score:.2f}): "
                f"Field '{field_name}' label was identified in source document, but the corresponding value text was illegible or unreadable. "
                f"Score reflects evidence anchor quality, not recovered value confidence."
            )
            return QualityAssessment(
                quality_score=quality_score,
                breakdown=breakdown,
                status=FieldStatus.UNREADABLE,
                explanation=explanation,
                reasons_for_review=[
                    "Illegible or corrupted text in field value region",
                    "No value could be extracted",
                ],
            )

        # 2. Missing field handling
        if not value or str(value).strip() == "":
            breakdown = QualityBreakdown(
                source_quality=0.0,
                label_match=0.0,
                format_validity=0.0,
                normalization_adjustment=0.0,
                ambiguity_penalty=1.0,
                provenance_quality=0.0,
            )
            return QualityAssessment(
                quality_score=0.0,
                breakdown=breakdown,
                status=FieldStatus.MISSING,
                explanation="Field not detected in document content.",
                reasons_for_review=["Field absent from document"],
            )

        # 3. Source Quality Signal (w_S = 0.20)
        # Digital text stream provides highest baseline fidelity;
        # OCR reflects measured word-token confidence when available, falling back to page-level confidence
        used_page_fallback = False
        if extraction_method == "DIGITAL_TEXT":
            source_q = 0.98
        elif extraction_method == "OCR":
            if has_token_level_confidence and field_ocr_confidence is not None:
                source_q = min(0.95, max(0.30, float(field_ocr_confidence)))
            elif raw_ocr_confidence is not None and raw_ocr_confidence > 0:
                source_q = min(0.90, max(0.30, float(raw_ocr_confidence)))
                used_page_fallback = True
            else:
                source_q = 0.70
                used_page_fallback = True
        else:
            source_q = 0.50

        # 4. Label Match Signal (w_L = 0.20)
        if is_exact_label:
            label_q = 1.00
        elif has_label_match:
            label_q = 0.85
        else:
            label_q = 0.50  # Unlabelled regex or pattern match

        # 5. Format Validity Signal (w_F = 0.25)
        if is_valid_format:
            format_q = 1.00
        else:
            format_q = 0.30

        # 6. Normalization Adjustment Signal (w_N = 0.10)
        norm_q = 1.00
        review_reasons: List[str] = []

        if is_ambiguous:
            norm_q -= 0.50
            review_reasons.append("Ambiguous value format requires human inspection")
        if was_repaired:
            norm_q -= 0.20
            repair_desc = "; ".join(repaired_notes) if repaired_notes else "OCR characters repaired"
            review_reasons.append(f"OCR character repair applied ({repair_desc})")

        norm_q = max(0.20, norm_q)

        # 7. Ambiguity Penalty Signal (w_A = 0.10)
        if candidate_count > 1:
            ambiguity_q = 0.60
            review_reasons.append(f"Multiple candidate values detected ({candidate_count} candidates found)")
        else:
            ambiguity_q = 1.00

        # 8. Provenance Quality Signal (w_P = 0.15)
        prov_q = 0.0
        if has_page:
            prov_q += 0.50
        if has_location:
            prov_q += 0.30
        if has_snippet:
            prov_q += 0.20

        # 9. Weighted Composite Score Calculation (weights sum to 1.00)
        raw_score = (
            0.20 * source_q +
            0.20 * label_q +
            0.25 * format_q +
            0.15 * prov_q +
            0.10 * norm_q +
            0.10 * ambiguity_q
        )
        quality_score = round(min(1.0, max(0.0, raw_score)), 2)

        breakdown = QualityBreakdown(
            source_quality=round(source_q, 2),
            label_match=round(label_q, 2),
            format_validity=round(format_q, 2),
            normalization_adjustment=round(norm_q, 2),
            ambiguity_penalty=round(ambiguity_q, 2),
            provenance_quality=round(prov_q, 2),
        )

        # 10. Status Determination
        if is_ambiguous:
            status = FieldStatus.NEEDS_REVIEW
        elif not is_valid_format:
            status = FieldStatus.NEEDS_REVIEW
            review_reasons.append("Value does not strictly match expected statutory format")
        elif candidate_count > 1:
            status = FieldStatus.NEEDS_REVIEW
        elif was_repaired:
            status = FieldStatus.NEEDS_REVIEW
        elif quality_score < HIGH_CONFIDENCE_THRESHOLD:
            status = FieldStatus.NEEDS_REVIEW
            review_reasons.append(f"Quality score ({quality_score:.2f}) below high confidence threshold ({HIGH_CONFIDENCE_THRESHOLD})")
        else:
            status = FieldStatus.EXTRACTED

        # 11. Human-Readable Explanation
        explanation_parts = []
        if status == FieldStatus.EXTRACTED:
            if extraction_method == "DIGITAL_TEXT":
                src_desc = "digital text stream"
            elif has_token_level_confidence:
                src_desc = f"OCR token confidence {source_q:.0%}"
            else:
                src_desc = f"OCR page confidence {source_q:.0%}"
            label_desc = "exact label" if is_exact_label else "supporting label" if has_label_match else "unlabelled pattern"
            explanation_parts.append(f"High evidence quality ({quality_score:.2f}): extracted via {src_desc} with {label_desc} and valid statutory format.")
        else:
            reasons_str = "; ".join(review_reasons) if review_reasons else "Quality score below threshold"
            explanation_parts.append(f"Needs review ({quality_score:.2f}): {reasons_str}.")

        if used_page_fallback and extraction_method == "OCR":
            explanation_parts.append("(Page-level OCR confidence fallback used; token-level data unavailable).")

        return QualityAssessment(
            quality_score=quality_score,
            breakdown=breakdown,
            status=status,
            explanation=" ".join(explanation_parts),
            reasons_for_review=review_reasons,
        )


quality_assessor = QualityAssessor()
