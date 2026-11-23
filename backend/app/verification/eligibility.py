"""Shared evidence eligibility boundary and validation rules.

Enforces consistent eligibility across classification, extraction,
cross-document verification, and onboarding decision orchestration.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from app.models.classification import DocumentClassification
from app.models.document import VendorDocument
from app.models.extraction import DocumentExtraction
from app.schemas.extraction import ExtractedField, ExtractionStatus, ExtractionLimitationCode


# Standard statutory categories supported by the platform
VALID_STATUTORY_CATEGORIES = {
    "TAX_CERTIFICATE",
    "CERTIFICATE_OF_INCORPORATION",
    "BANK_PROOF",
    "ADDRESS_PROOF",
}

# Category equivalence mapping for legacy or variant terms
CATEGORY_EQUIVALENCES = {
    "GST_CERTIFICATE": "TAX_CERTIFICATE",
    "PAN_CARD": "TAX_CERTIFICATE",
    "TAX_DOCUMENT": "TAX_CERTIFICATE",
    "INCORPORATION_CERTIFICATE": "CERTIFICATE_OF_INCORPORATION",
    "CANCELLED_CHEQUE": "BANK_PROOF",
    "BANK_STATEMENT": "BANK_PROOF",
}


def canonicalize_category(cat: Optional[str]) -> str:
    """Normalizes category strings to standard statutory identifiers."""
    if not cat or not str(cat).strip():
        return "OTHER"
    raw = str(cat).strip().upper()
    return CATEGORY_EQUIVALENCES.get(raw, raw)


@dataclass
class ClassificationEligibilityResult:
    """Eligibility assessment for a document's classification."""
    is_confirmed: bool
    is_conflict: bool
    status: str
    declared_category: str
    predicted_category: Optional[str]
    effective_category: Optional[str]
    confidence_score: Optional[float]
    reason_code: str
    explanation: str


@dataclass
class ExtractionEligibilityResult:
    """Eligibility assessment for a document's OCR and structured extraction."""
    is_eligible: bool
    status: str
    extracted_fields_count: int
    average_confidence: Optional[float]
    limitation_code: Optional[str]
    reason_code: str
    explanation: str
    fields: Dict[str, ExtractedField] = field(default_factory=dict)


@dataclass
class DocumentEligibilityResult:
    """Comprehensive eligibility evaluation for a document."""
    document_id: str
    file_name: str
    declared_category: str
    effective_category: Optional[str]
    is_classification_confirmed: bool
    is_extraction_eligible: bool
    is_eligible_for_verification: bool
    classification: ClassificationEligibilityResult
    extraction: ExtractionEligibilityResult
    ineligible_reason_code: Optional[str] = None
    ineligible_explanation: Optional[str] = None


def evaluate_classification_eligibility(
    declared_category: Optional[str],
    classification: Optional[DocumentClassification],
    filename: str = "document",
) -> ClassificationEligibilityResult:
    """Evaluates whether a document's classification satisfies the eligibility policy.
    
    Eligibility Rules:
    1. Unclassified document: Not confirmed, reason=UNCLASSIFIED_DOCUMENT.
    2. Failed or error status: Not confirmed, reason=DOCUMENT_CLASSIFICATION_FAILED.
    3. Inconclusive (UNKNOWN, OTHER, LOW_CONFIDENCE, INSUFFICIENT_TEXT):
       Not confirmed, reason=LOW_CONFIDENCE_DOCUMENT_EVIDENCE or UNSUPPORTED_DOCUMENT_EVIDENCE.
    4. Classified with category mismatch:
       Conflict detected, Not confirmed, reason=DOCUMENT_CLASSIFICATION_MISMATCH.
    5. Classified with matching statutory category:
       Confirmed, reason=CLASSIFICATION_CONFIRMED.
    """
    decl_cat = canonicalize_category(declared_category)

    if not classification:
        return ClassificationEligibilityResult(
            is_confirmed=False,
            is_conflict=False,
            status="UNCLASSIFIED",
            declared_category=decl_cat,
            predicted_category=None,
            effective_category=None,
            confidence_score=None,
            reason_code="UNCLASSIFIED_DOCUMENT",
            explanation=f"Document '{filename}' has not undergone automated classification.",
        )

    c_status = (classification.status or "").upper()
    raw_pred = classification.predicted_category
    pred_cat = canonicalize_category(raw_pred) if raw_pred else "UNKNOWN"
    conf = classification.confidence_score

    # Check for technical failure
    if c_status in ("FAILED", "ERROR"):
        return ClassificationEligibilityResult(
            is_confirmed=False,
            is_conflict=False,
            status=c_status,
            declared_category=decl_cat,
            predicted_category=pred_cat,
            effective_category=None,
            confidence_score=conf,
            reason_code="DOCUMENT_CLASSIFICATION_FAILED",
            explanation=f"Classification process failed for document '{filename}'.",
        )

    # Inconclusive content or low confidence
    if c_status in ("INSUFFICIENT_TEXT", "LOW_CONFIDENCE") or pred_cat == "UNKNOWN":
        return ClassificationEligibilityResult(
            is_confirmed=False,
            is_conflict=False,
            status=c_status,
            declared_category=decl_cat,
            predicted_category=pred_cat,
            effective_category=None,
            confidence_score=conf,
            reason_code="LOW_CONFIDENCE_DOCUMENT_EVIDENCE",
            explanation=(
                f"Document '{filename}' classification is inconclusive "
                f"(status={c_status}, predicted={pred_cat}, confidence={conf or 0.0:.2f})."
            ),
        )

    # Document classified as non-statutory / OTHER
    if pred_cat == "OTHER":
        return ClassificationEligibilityResult(
            is_confirmed=False,
            is_conflict=(decl_cat != "OTHER"),
            status=c_status,
            declared_category=decl_cat,
            predicted_category="OTHER",
            effective_category=None,
            confidence_score=conf,
            reason_code="UNSUPPORTED_DOCUMENT_EVIDENCE",
            explanation=(
                f"Document '{filename}' was classified as OTHER (unsupported non-statutory document). "
                f"Declared category was '{decl_cat}'."
            ),
        )

    # Check category match vs conflict
    if c_status == "CLASSIFIED":
        if pred_cat == decl_cat:
            return ClassificationEligibilityResult(
                is_confirmed=True,
                is_conflict=False,
                status="CLASSIFIED",
                declared_category=decl_cat,
                predicted_category=pred_cat,
                effective_category=pred_cat,
                confidence_score=conf,
                reason_code="CLASSIFICATION_CONFIRMED",
                explanation=f"Document '{filename}' confirmed as {pred_cat} with confidence {conf or 0.0:.2f}.",
            )
        else:
            return ClassificationEligibilityResult(
                is_confirmed=False,
                is_conflict=True,
                status="CLASSIFIED",
                declared_category=decl_cat,
                predicted_category=pred_cat,
                effective_category=None,
                confidence_score=conf,
                reason_code="DOCUMENT_CLASSIFICATION_MISMATCH",
                explanation=(
                    f"Classification conflict detected for '{filename}': Declared as '{decl_cat}' "
                    f"but classified as '{pred_cat}' (confidence: {conf or 0.0:.2f})."
                ),
            )

    # Any other unconfirmed status
    return ClassificationEligibilityResult(
        is_confirmed=False,
        is_conflict=False,
        status=c_status,
        declared_category=decl_cat,
        predicted_category=pred_cat,
        effective_category=None,
        confidence_score=conf,
        reason_code="UNCONFIRMED_CLASSIFICATION",
        explanation=f"Document '{filename}' classification status '{c_status}' is unconfirmed.",
    )


def evaluate_extraction_eligibility(
    extraction: Optional[DocumentExtraction],
    filename: str = "document",
) -> ExtractionEligibilityResult:
    """Evaluates whether a document extraction record is eligible for verification.
    
    Eligibility Rules:
    1. No extraction record: Ineligible (NO_EXTRACTION).
    2. Extraction status FAILED or ERROR: Ineligible (CORRUPTED_DOCUMENT_EVIDENCE or UNSUPPORTED_DOCUMENT_EVIDENCE).
    3. Extraction status INSUFFICIENT_TEXT: Ineligible (UNREADABLE_DOCUMENT_EVIDENCE).
    4. Successful extraction: Eligible (EXTRACTION_ELIGIBLE).
    """
    if not extraction:
        return ExtractionEligibilityResult(
            is_eligible=False,
            status="PENDING",
            extracted_fields_count=0,
            average_confidence=None,
            limitation_code=None,
            reason_code="NO_EXTRACTION",
            explanation=f"No extraction record found for document '{filename}'.",
            fields={},
        )

    e_status = (extraction.status or "").upper()
    lim_code = extraction.limitation_code
    raw_fields = extraction.fields or {}

    parsed_fields: Dict[str, ExtractedField] = {}
    for k, v in raw_fields.items():
        if isinstance(v, dict):
            try:
                parsed_fields[k] = ExtractedField.model_validate(v)
            except Exception:
                pass

    scores = [
        f.quality_score if f.quality_score is not None else f.confidence
        for f in parsed_fields.values()
        if (f.quality_score is not None or f.confidence is not None)
    ]
    avg_conf = round(sum(scores) / len(scores), 4) if scores else None
    count = extraction.extracted_fields_count or len(parsed_fields)

    if e_status in ("FAILED", "ERROR"):
        reason_code = (
            "CORRUPTED_DOCUMENT_EVIDENCE"
            if lim_code == ExtractionLimitationCode.CORRUPTED_DOCUMENT.value
            else "UNSUPPORTED_DOCUMENT_EVIDENCE"
        )
        return ExtractionEligibilityResult(
            is_eligible=False,
            status=e_status,
            extracted_fields_count=count,
            average_confidence=avg_conf,
            limitation_code=lim_code,
            reason_code=reason_code,
            explanation=f"Document '{filename}' extraction failed: {lim_code or 'technical failure'}.",
            fields=parsed_fields,
        )

    if e_status in ("INSUFFICIENT_TEXT", "UNREADABLE"):
        return ExtractionEligibilityResult(
            is_eligible=False,
            status=e_status,
            extracted_fields_count=count,
            average_confidence=avg_conf,
            limitation_code=lim_code or ExtractionLimitationCode.INSUFFICIENT_READABLE_TEXT.value,
            reason_code="UNREADABLE_DOCUMENT_EVIDENCE",
            explanation=f"Document '{filename}' contains insufficient readable text for reliable extraction.",
            fields=parsed_fields,
        )

    return ExtractionEligibilityResult(
        is_eligible=True,
        status=e_status,
        extracted_fields_count=count,
        average_confidence=avg_conf,
        limitation_code=lim_code,
        reason_code="EXTRACTION_ELIGIBLE",
        explanation=f"Document '{filename}' extraction complete ({count} fields extracted).",
        fields=parsed_fields,
    )


def evaluate_document_eligibility(
    document: VendorDocument,
    classification: Optional[DocumentClassification],
    extraction: Optional[DocumentExtraction],
) -> DocumentEligibilityResult:
    """Evaluates complete document evidence eligibility across classification and extraction."""
    filename = document.original_filename or "document"
    cls_result = evaluate_classification_eligibility(
        declared_category=document.document_category,
        classification=classification,
        filename=filename,
    )
    ext_result = evaluate_extraction_eligibility(
        extraction=extraction,
        filename=filename,
    )

    is_eligible = cls_result.is_confirmed and ext_result.is_eligible
    ineligible_reason_code = None
    ineligible_explanation = None

    if not cls_result.is_confirmed:
        ineligible_reason_code = cls_result.reason_code
        ineligible_explanation = cls_result.explanation
    elif not ext_result.is_eligible:
        ineligible_reason_code = ext_result.reason_code
        ineligible_explanation = ext_result.explanation

    return DocumentEligibilityResult(
        document_id=document.id,
        file_name=filename,
        declared_category=cls_result.declared_category,
        effective_category=cls_result.effective_category,
        is_classification_confirmed=cls_result.is_confirmed,
        is_extraction_eligible=ext_result.is_eligible,
        is_eligible_for_verification=is_eligible,
        classification=cls_result,
        extraction=ext_result,
        ineligible_reason_code=ineligible_reason_code,
        ineligible_explanation=ineligible_explanation,
    )
