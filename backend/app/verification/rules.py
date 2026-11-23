"""Cross-document verification rules registry and evaluation handlers."""

from dataclasses import dataclass, field
from itertools import product
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from app.models.vendor import Vendor
from app.models.document import VendorDocument
from app.models.classification import DocumentClassification
from app.models.extraction import DocumentExtraction
from app.schemas.extraction import ExtractedField, FieldStatus
from app.schemas.verification import (
    ComparisonType,
    EvidenceSource,
    EvidenceSourceType,
    FindingResult,
    FindingSeverity,
)
from app.verification.comparison import (
    ComparisonOutcome,
    compare_exact_identifier,
    compare_account_numbers,
    compare_dates,
    compare_company_names,
    compare_addresses,
)
from app.verification.normalization import (
    mask_account_number,
    mask_sensitive_identifier,
    sanitize_evidence_snippet,
)


@dataclass
class DocumentEvidenceContext:
    """Encapsulates a vendor document along with its verified classification, extraction, and parsed fields."""
    document: VendorDocument
    classification: Optional[DocumentClassification] = None
    is_classification_confirmed: bool = False
    classification_conflict: bool = False
    classification_note: Optional[str] = None
    extraction: Optional[DocumentExtraction] = None
    is_extraction_eligible: bool = False
    extraction_note: Optional[str] = None
    fields: Dict[str, ExtractedField] = field(default_factory=dict)


@dataclass
class VerificationRuleContext:
    """Contextual data payload provided to cross-document verification rules."""
    vendor: Vendor
    vendor_dict: Dict[str, Any]
    # Category -> List of all DocumentEvidenceContext records (ordered deterministically)
    category_docs: Dict[str, List[DocumentEvidenceContext]] = field(default_factory=dict)
    # Category -> List of only eligible DocumentEvidenceContext records
    eligible_docs: Dict[str, List[DocumentEvidenceContext]] = field(default_factory=dict)
    # Backward compatibility helper: Category -> (latest_doc, latest_ext, fields_map)
    category_extractions: Dict[str, Tuple[Optional[VendorDocument], Optional[DocumentExtraction], Dict[str, ExtractedField]]] = field(default_factory=dict)


@dataclass
class EvaluatedRuleFinding:
    """Output of an evaluated cross-document verification rule."""
    field_name: str
    comparison_type: ComparisonType
    result: FindingResult
    severity: FindingSeverity
    explanation: str
    similarity_score: Optional[float] = None
    comparison_summary: Optional[str] = None
    evidence_sources: List[EvidenceSource] = field(default_factory=list)


def build_profile_evidence(field_name: str, value: Any, is_masked: bool = False) -> EvidenceSource:
    """Constructs a standardized EvidenceSource for a vendor profile field with zero leakage."""
    if value is None or str(value).strip() == "":
        display_val = None
    elif is_masked or field_name in (
        "bank_account_number", "account_number", "tax_id_number", "gstin", "pan",
        "cin_or_reg_number", "registration_number", "bank_routing_number", "ifsc_code", "ifsc"
    ):
        display_val = mask_sensitive_identifier(str(value), field_name)
    else:
        display_val = str(value)

    return EvidenceSource(
        source_type=EvidenceSourceType.VENDOR_PROFILE,
        field_name=field_name,
        value_display=display_val,
    )


def build_doc_evidence(
    doc: Optional[VendorDocument],
    ext: Optional[DocumentExtraction],
    extracted_field: Optional[ExtractedField],
    fallback_field_name: str,
    classification_id: Optional[str] = None,
) -> EvidenceSource:
    """Constructs a standardized EvidenceSource for an extracted document field."""
    if not doc:
        return EvidenceSource(
            source_type=EvidenceSourceType.EXTRACTED_DOCUMENT_FIELD,
            field_name=fallback_field_name,
            value_display=None,
        )

    val_display = None
    page_num = None
    method = None
    status = None
    score = None
    snippet = None
    target_field = extracted_field.field_name if extracted_field else fallback_field_name

    if extracted_field:
        val_display = extracted_field.masked_value or extracted_field.value
        # Strict zero-leakage masking for sensitive statutory identifiers
        if target_field in (
            "account_number", "bank_account_number", "gstin", "tax_id_number", "pan",
            "cin_or_reg_number", "registration_number", "ifsc_code", "bank_routing_number"
        ):
            val_display = mask_sensitive_identifier(val_display, target_field)
        status = extracted_field.status.value if hasattr(extracted_field.status, "value") else str(extracted_field.status)
        score = extracted_field.quality_score if extracted_field.quality_score is not None else extracted_field.confidence
        if extracted_field.source:
            page_num = extracted_field.source.page_number
            method = extracted_field.source.extraction_method
            snippet = sanitize_evidence_snippet(extracted_field.source.evidence_snippet)

    return EvidenceSource(
        source_type=EvidenceSourceType.EXTRACTED_DOCUMENT_FIELD,
        field_name=target_field,
        value_display=val_display,
        document_id=doc.id,
        document_name=doc.original_filename,
        document_category=doc.document_category,
        classification_id=classification_id,
        extraction_id=ext.id if ext else None,
        page_number=page_num,
        extraction_method=method,
        extraction_status=status,
        confidence_score=score,
        sanitized_snippet=snippet,
    )


# -----------------------------------------------------------------------------
# Rule 1: GSTIN consistency (Vendor Profile vs Tax Certificate(s))
# -----------------------------------------------------------------------------
def rule_gstin_consistency(ctx: VerificationRuleContext) -> List[EvaluatedRuleFinding]:
    profile_tax_id = ctx.vendor_dict.get("tax_id_number")
    ev_profile = build_profile_evidence("tax_id_number", profile_tax_id)
    all_docs = ctx.category_docs.get("TAX_CERTIFICATE", [])
    eligible_docs = ctx.eligible_docs.get("TAX_CERTIFICATE", [])

    if not all_docs:
        return [
            EvaluatedRuleFinding(
                field_name="gstin",
                comparison_type=ComparisonType.EXACT_IDENTIFIER,
                result=FindingResult.MISSING_DOCUMENT,
                severity=FindingSeverity.WARNING,
                explanation="Tax Certificate (GST proof) has not been uploaded. Cannot verify statutory tax identifier.",
                comparison_summary="Tax Certificate missing",
                evidence_sources=[ev_profile],
            )
        ]

    if not eligible_docs:
        return [
            EvaluatedRuleFinding(
                field_name="gstin",
                comparison_type=ComparisonType.EXACT_IDENTIFIER,
                result=FindingResult.INSUFFICIENT_EVIDENCE,
                severity=FindingSeverity.INFO,
                explanation="No eligible Tax Certificate with confirmed classification and extraction available for GSTIN verification.",
                comparison_summary="Tax Certificate evidence ineligible",
                evidence_sources=[ev_profile],
            )
        ]

    findings: List[EvaluatedRuleFinding] = []
    for doc_ctx in eligible_docs:
        doc = doc_ctx.document
        ext = doc_ctx.extraction
        gstin_field = doc_ctx.fields.get("gstin")
        ev_doc = build_doc_evidence(
            doc, ext, gstin_field, "gstin",
            classification_id=doc_ctx.classification.id if doc_ctx.classification else None,
        )

        if not ext or not gstin_field or gstin_field.status == FieldStatus.MISSING:
            findings.append(
                EvaluatedRuleFinding(
                    field_name="gstin",
                    comparison_type=ComparisonType.EXACT_IDENTIFIER,
                    result=FindingResult.INSUFFICIENT_EVIDENCE,
                    severity=FindingSeverity.INFO,
                    explanation=f"GSTIN could not be located in Tax Certificate ('{doc.original_filename}').",
                    comparison_summary=f"GSTIN absent from extraction ({doc.original_filename})",
                    evidence_sources=[ev_profile, ev_doc],
                )
            )
            continue

        if gstin_field.status == FieldStatus.UNREADABLE:
            findings.append(
                EvaluatedRuleFinding(
                    field_name="gstin",
                    comparison_type=ComparisonType.EXACT_IDENTIFIER,
                    result=FindingResult.INSUFFICIENT_EVIDENCE,
                    severity=FindingSeverity.INFO,
                    explanation=f"GSTIN region in Tax Certificate ('{doc.original_filename}') is illegible or unreadable. Human review required.",
                    comparison_summary=f"GSTIN unreadable ({doc.original_filename})",
                    evidence_sources=[ev_profile, ev_doc],
                )
            )
            continue

        score = gstin_field.quality_score if gstin_field.quality_score is not None else 0.5
        outcome = compare_exact_identifier(
            val1=profile_tax_id,
            val2=gstin_field.value,
            field_label="GSTIN",
            source1_label="Vendor Profile",
            source2_label=f"Tax Certificate ('{doc.original_filename}')",
            quality1=1.0,
            quality2=score,
            is_critical=True,
            is_sensitive=True,
        )

        findings.append(
            EvaluatedRuleFinding(
                field_name="gstin",
                comparison_type=ComparisonType.EXACT_IDENTIFIER,
                result=outcome.result,
                severity=outcome.severity,
                explanation=outcome.explanation,
                similarity_score=outcome.similarity_score,
                comparison_summary=outcome.comparison_summary,
                evidence_sources=[ev_profile, ev_doc],
            )
        )
    return findings


# -----------------------------------------------------------------------------
# Rule 1.1: Intra-Document GSTIN Conflict (Multiple Tax Certificates)
# -----------------------------------------------------------------------------
def rule_gstin_intra_doc_conflict(ctx: VerificationRuleContext) -> List[EvaluatedRuleFinding]:
    """Identifies conflicts between multiple uploaded Tax Certificates (GST proofs)."""
    eligible_tax_docs = ctx.eligible_docs.get("TAX_CERTIFICATE", [])
    if len(eligible_tax_docs) < 2:
        return []

    findings: List[EvaluatedRuleFinding] = []
    # Deterministic pairwise comparisons without duplicates (i < j)
    for i in range(len(eligible_tax_docs)):
        for j in range(i + 1, len(eligible_tax_docs)):
            doc1_ctx = eligible_tax_docs[i]
            doc2_ctx = eligible_tax_docs[j]
            doc1, ext1 = doc1_ctx.document, doc1_ctx.extraction
            doc2, ext2 = doc2_ctx.document, doc2_ctx.extraction

            f1 = doc1_ctx.fields.get("gstin")
            f2 = doc2_ctx.fields.get("gstin")
            ev1 = build_doc_evidence(doc1, ext1, f1, "gstin", classification_id=doc1_ctx.classification.id if doc1_ctx.classification else None)
            ev2 = build_doc_evidence(doc2, ext2, f2, "gstin", classification_id=doc2_ctx.classification.id if doc2_ctx.classification else None)

            if not f1 or f1.status in (FieldStatus.MISSING, FieldStatus.UNREADABLE) or \
               not f2 or f2.status in (FieldStatus.MISSING, FieldStatus.UNREADABLE):
                findings.append(
                    EvaluatedRuleFinding(
                        field_name="gstin_intra_conflict",
                        comparison_type=ComparisonType.EXACT_IDENTIFIER,
                        result=FindingResult.INSUFFICIENT_EVIDENCE,
                        severity=FindingSeverity.INFO,
                        explanation=f"Cannot compare multiple Tax Certificates: GSTIN unreadable in '{doc1.original_filename}' or '{doc2.original_filename}'.",
                        comparison_summary="GSTIN unreadable in intra-check",
                        evidence_sources=[ev1, ev2],
                    )
                )
                continue

            score1 = f1.quality_score if f1.quality_score is not None else 0.5
            score2 = f2.quality_score if f2.quality_score is not None else 0.5
            outcome = compare_exact_identifier(
                val1=f1.value,
                val2=f2.value,
                field_label="GSTIN",
                source1_label=f"Tax Certificate 1 ('{doc1.original_filename}')",
                source2_label=f"Tax Certificate 2 ('{doc2.original_filename}')",
                quality1=score1,
                quality2=score2,
                is_critical=True,
                is_sensitive=True,
            )

            if outcome.result == FindingResult.MATCH:
                expl = (
                    f"Intra-document GSTIN consistency: Tax Certificate ('{doc1.original_filename}') and "
                    f"Tax Certificate ('{doc2.original_filename}') agree on GSTIN ({mask_sensitive_identifier(f1.value, 'gstin')})."
                )
                summary = f"Matching GSTIN between certificates ({mask_sensitive_identifier(f1.value, 'gstin')})"
            else:
                expl = (
                    f"Conflicting GST certificates detected: '{doc1.original_filename}' specifies "
                    f"{mask_sensitive_identifier(f1.value, 'gstin')} whereas '{doc2.original_filename}' specifies "
                    f"{mask_sensitive_identifier(f2.value, 'gstin')}."
                )
                summary = f"GSTIN conflict: {mask_sensitive_identifier(f1.value, 'gstin')} ≠ {mask_sensitive_identifier(f2.value, 'gstin')}"

            findings.append(
                EvaluatedRuleFinding(
                    field_name="gstin_intra_conflict",
                    comparison_type=ComparisonType.EXACT_IDENTIFIER,
                    result=outcome.result,
                    severity=outcome.severity,
                    explanation=expl,
                    similarity_score=outcome.similarity_score,
                    comparison_summary=summary,
                    evidence_sources=[ev1, ev2],
                )
            )
    return findings


# -----------------------------------------------------------------------------
# Rule 2: Legal Entity Name (Vendor Profile vs Tax Certificate(s))
# -----------------------------------------------------------------------------
def rule_legal_name_gst(ctx: VerificationRuleContext) -> List[EvaluatedRuleFinding]:
    profile_name = ctx.vendor_dict.get("legal_name")
    ev_profile = build_profile_evidence("legal_name", profile_name)
    all_docs = ctx.category_docs.get("TAX_CERTIFICATE", [])
    eligible_docs = ctx.eligible_docs.get("TAX_CERTIFICATE", [])

    if not all_docs:
        return [
            EvaluatedRuleFinding(
                field_name="legal_entity_name",
                comparison_type=ComparisonType.FUZZY_NAME,
                result=FindingResult.MISSING_DOCUMENT,
                severity=FindingSeverity.WARNING,
                explanation="Tax Certificate has not been uploaded. Cannot verify legal entity name against tax records.",
                comparison_summary="Tax Certificate missing",
                evidence_sources=[ev_profile],
            )
        ]

    if not eligible_docs:
        return [
            EvaluatedRuleFinding(
                field_name="legal_entity_name",
                comparison_type=ComparisonType.FUZZY_NAME,
                result=FindingResult.INSUFFICIENT_EVIDENCE,
                severity=FindingSeverity.INFO,
                explanation="No eligible Tax Certificate available for legal entity name verification.",
                comparison_summary="Tax Certificate evidence ineligible",
                evidence_sources=[ev_profile],
            )
        ]

    findings: List[EvaluatedRuleFinding] = []
    for doc_ctx in eligible_docs:
        doc = doc_ctx.document
        ext = doc_ctx.extraction
        name_field = doc_ctx.fields.get("legal_entity_name")
        ev_doc = build_doc_evidence(
            doc, ext, name_field, "legal_entity_name",
            classification_id=doc_ctx.classification.id if doc_ctx.classification else None,
        )

        if not ext or not name_field or name_field.status == FieldStatus.MISSING:
            findings.append(
                EvaluatedRuleFinding(
                    field_name="legal_entity_name",
                    comparison_type=ComparisonType.FUZZY_NAME,
                    result=FindingResult.INSUFFICIENT_EVIDENCE,
                    severity=FindingSeverity.INFO,
                    explanation=f"Legal entity name could not be located in Tax Certificate ('{doc.original_filename}').",
                    comparison_summary=f"Legal name missing in tax document ({doc.original_filename})",
                    evidence_sources=[ev_profile, ev_doc],
                )
            )
            continue

        if name_field.status == FieldStatus.UNREADABLE:
            findings.append(
                EvaluatedRuleFinding(
                    field_name="legal_entity_name",
                    comparison_type=ComparisonType.FUZZY_NAME,
                    result=FindingResult.INSUFFICIENT_EVIDENCE,
                    severity=FindingSeverity.INFO,
                    explanation=f"Legal entity name in Tax Certificate ('{doc.original_filename}') is unreadable.",
                    comparison_summary=f"Legal name unreadable in tax document ({doc.original_filename})",
                    evidence_sources=[ev_profile, ev_doc],
                )
            )
            continue

        score = name_field.quality_score if name_field.quality_score is not None else 0.5
        outcome = compare_company_names(
            name1=profile_name,
            name2=name_field.value,
            field_label="Legal Entity Name",
            source1_label="Vendor Profile",
            source2_label=f"Tax Certificate ('{doc.original_filename}')",
            quality1=1.0,
            quality2=score,
            is_critical=True,
        )

        findings.append(
            EvaluatedRuleFinding(
                field_name="legal_entity_name",
                comparison_type=ComparisonType.FUZZY_NAME,
                result=outcome.result,
                severity=outcome.severity,
                explanation=outcome.explanation,
                similarity_score=outcome.similarity_score,
                comparison_summary=outcome.comparison_summary,
                evidence_sources=[ev_profile, ev_doc],
            )
        )
    return findings


# -----------------------------------------------------------------------------
# Rule 3: Legal Entity Name (Vendor Profile vs Certificate of Incorporation)
# -----------------------------------------------------------------------------
def rule_legal_name_inc(ctx: VerificationRuleContext) -> List[EvaluatedRuleFinding]:
    profile_name = ctx.vendor_dict.get("legal_name")
    ev_profile = build_profile_evidence("legal_name", profile_name)
    all_docs = ctx.category_docs.get("CERTIFICATE_OF_INCORPORATION", [])
    eligible_docs = ctx.eligible_docs.get("CERTIFICATE_OF_INCORPORATION", [])

    if not all_docs:
        return [
            EvaluatedRuleFinding(
                field_name="legal_entity_name",
                comparison_type=ComparisonType.FUZZY_NAME,
                result=FindingResult.MISSING_DOCUMENT,
                severity=FindingSeverity.WARNING,
                explanation="Certificate of Incorporation has not been uploaded. Cannot verify incorporation company name.",
                comparison_summary="Incorporation Certificate missing",
                evidence_sources=[ev_profile],
            )
        ]

    if not eligible_docs:
        return [
            EvaluatedRuleFinding(
                field_name="legal_entity_name",
                comparison_type=ComparisonType.FUZZY_NAME,
                result=FindingResult.INSUFFICIENT_EVIDENCE,
                severity=FindingSeverity.INFO,
                explanation="No eligible Certificate of Incorporation available for company name verification.",
                comparison_summary="Incorporation Certificate evidence ineligible",
                evidence_sources=[ev_profile],
            )
        ]

    findings: List[EvaluatedRuleFinding] = []
    for doc_ctx in eligible_docs:
        doc = doc_ctx.document
        ext = doc_ctx.extraction
        name_field = doc_ctx.fields.get("company_name")
        ev_doc = build_doc_evidence(
            doc, ext, name_field, "company_name",
            classification_id=doc_ctx.classification.id if doc_ctx.classification else None,
        )

        if not ext or not name_field or name_field.status == FieldStatus.MISSING:
            findings.append(
                EvaluatedRuleFinding(
                    field_name="legal_entity_name",
                    comparison_type=ComparisonType.FUZZY_NAME,
                    result=FindingResult.INSUFFICIENT_EVIDENCE,
                    severity=FindingSeverity.INFO,
                    explanation=f"Company name could not be located in Certificate of Incorporation ('{doc.original_filename}').",
                    comparison_summary=f"Company name missing in incorporation document ({doc.original_filename})",
                    evidence_sources=[ev_profile, ev_doc],
                )
            )
            continue

        if name_field.status == FieldStatus.UNREADABLE:
            findings.append(
                EvaluatedRuleFinding(
                    field_name="legal_entity_name",
                    comparison_type=ComparisonType.FUZZY_NAME,
                    result=FindingResult.INSUFFICIENT_EVIDENCE,
                    severity=FindingSeverity.INFO,
                    explanation=f"Company name in Certificate of Incorporation ('{doc.original_filename}') is unreadable.",
                    comparison_summary=f"Company name unreadable in incorporation document ({doc.original_filename})",
                    evidence_sources=[ev_profile, ev_doc],
                )
            )
            continue

        score = name_field.quality_score if name_field.quality_score is not None else 0.5
        outcome = compare_company_names(
            name1=profile_name,
            name2=name_field.value,
            field_label="Legal Entity Name",
            source1_label="Vendor Profile",
            source2_label=f"Incorporation Certificate ('{doc.original_filename}')",
            quality1=1.0,
            quality2=score,
            is_critical=True,
        )

        findings.append(
            EvaluatedRuleFinding(
                field_name="legal_entity_name",
                comparison_type=ComparisonType.FUZZY_NAME,
                result=outcome.result,
                severity=outcome.severity,
                explanation=outcome.explanation,
                similarity_score=outcome.similarity_score,
                comparison_summary=outcome.comparison_summary,
                evidence_sources=[ev_profile, ev_doc],
            )
        )
    return findings


# -----------------------------------------------------------------------------
# Rule 4: Legal Entity Name Cross-Doc (Tax Certificate vs Certificate of Incorporation)
# -----------------------------------------------------------------------------
def rule_legal_name_doc_cross(ctx: VerificationRuleContext) -> List[EvaluatedRuleFinding]:
    all_tax = ctx.category_docs.get("TAX_CERTIFICATE", [])
    all_inc = ctx.category_docs.get("CERTIFICATE_OF_INCORPORATION", [])
    el_tax = ctx.eligible_docs.get("TAX_CERTIFICATE", [])
    el_inc = ctx.eligible_docs.get("CERTIFICATE_OF_INCORPORATION", [])

    if not all_tax or not all_inc:
        missing_doc = "Tax Certificate" if not all_tax else "Certificate of Incorporation"
        return [
            EvaluatedRuleFinding(
                field_name="legal_entity_name",
                comparison_type=ComparisonType.FUZZY_NAME,
                result=FindingResult.MISSING_DOCUMENT,
                severity=FindingSeverity.INFO,
                explanation=f"Cross-document entity name comparison requires both Tax Certificate and Incorporation Certificate. Missing: {missing_doc}.",
                comparison_summary=f"{missing_doc} missing for cross-doc check",
                evidence_sources=[],
            )
        ]

    if not el_tax or not el_inc:
        return [
            EvaluatedRuleFinding(
                field_name="legal_entity_name",
                comparison_type=ComparisonType.FUZZY_NAME,
                result=FindingResult.INSUFFICIENT_EVIDENCE,
                severity=FindingSeverity.INFO,
                explanation="Cross-document entity name check requires eligible evidence in both Tax and Incorporation certificates.",
                comparison_summary="Ineligible evidence for cross-doc check",
                evidence_sources=[],
            )
        ]

    findings: List[EvaluatedRuleFinding] = []
    for tax_ctx, inc_ctx in product(el_tax, el_inc):
        tax_doc, tax_ext = tax_ctx.document, tax_ctx.extraction
        inc_doc, inc_ext = inc_ctx.document, inc_ctx.extraction

        tax_field = tax_ctx.fields.get("legal_entity_name")
        inc_field = inc_ctx.fields.get("company_name")

        ev_tax = build_doc_evidence(tax_doc, tax_ext, tax_field, "legal_entity_name", classification_id=tax_ctx.classification.id if tax_ctx.classification else None)
        ev_inc = build_doc_evidence(inc_doc, inc_ext, inc_field, "company_name", classification_id=inc_ctx.classification.id if inc_ctx.classification else None)

        if not tax_field or tax_field.status in (FieldStatus.MISSING, FieldStatus.UNREADABLE) or \
           not inc_field or inc_field.status in (FieldStatus.MISSING, FieldStatus.UNREADABLE):
            findings.append(
                EvaluatedRuleFinding(
                    field_name="legal_entity_name",
                    comparison_type=ComparisonType.FUZZY_NAME,
                    result=FindingResult.INSUFFICIENT_EVIDENCE,
                    severity=FindingSeverity.INFO,
                    explanation=f"Entity name is missing or unreadable in '{tax_doc.original_filename}' or '{inc_doc.original_filename}'.",
                    comparison_summary="Entity name unreadable in cross-doc check",
                    evidence_sources=[ev_tax, ev_inc],
                )
            )
            continue

        score1 = tax_field.quality_score if tax_field.quality_score is not None else 0.5
        score2 = inc_field.quality_score if inc_field.quality_score is not None else 0.5
        outcome = compare_company_names(
            name1=tax_field.value,
            name2=inc_field.value,
            field_label="Legal Entity Name",
            source1_label=f"Tax Certificate ('{tax_doc.original_filename}')",
            source2_label=f"Incorporation Certificate ('{inc_doc.original_filename}')",
            quality1=score1,
            quality2=score2,
            is_critical=True,
        )

        findings.append(
            EvaluatedRuleFinding(
                field_name="legal_entity_name",
                comparison_type=ComparisonType.FUZZY_NAME,
                result=outcome.result,
                severity=outcome.severity,
                explanation=outcome.explanation,
                similarity_score=outcome.similarity_score,
                comparison_summary=outcome.comparison_summary,
                evidence_sources=[ev_tax, ev_inc],
            )
        )
    return findings


# -----------------------------------------------------------------------------
# Rule 4.1: Intra-Document COI Conflict (Multiple Incorporation Certificates)
# -----------------------------------------------------------------------------
def rule_coi_intra_doc_conflict(ctx: VerificationRuleContext) -> List[EvaluatedRuleFinding]:
    """Identifies conflicts between multiple uploaded Certificates of Incorporation."""
    eligible_inc_docs = ctx.eligible_docs.get("CERTIFICATE_OF_INCORPORATION", [])
    if len(eligible_inc_docs) < 2:
        return []

    findings: List[EvaluatedRuleFinding] = []
    for i in range(len(eligible_inc_docs)):
        for j in range(i + 1, len(eligible_inc_docs)):
            doc1_ctx = eligible_inc_docs[i]
            doc2_ctx = eligible_inc_docs[j]
            doc1, ext1 = doc1_ctx.document, doc1_ctx.extraction
            doc2, ext2 = doc2_ctx.document, doc2_ctx.extraction

            # 1. Compare registration number / CIN
            f1_cin = doc1_ctx.fields.get("cin_or_reg_number")
            f2_cin = doc2_ctx.fields.get("cin_or_reg_number")
            ev1_cin = build_doc_evidence(doc1, ext1, f1_cin, "cin_or_reg_number", classification_id=doc1_ctx.classification.id if doc1_ctx.classification else None)
            ev2_cin = build_doc_evidence(doc2, ext2, f2_cin, "cin_or_reg_number", classification_id=doc2_ctx.classification.id if doc2_ctx.classification else None)

            if f1_cin and f1_cin.value and f2_cin and f2_cin.value:
                score1 = f1_cin.quality_score if f1_cin.quality_score is not None else 0.5
                score2 = f2_cin.quality_score if f2_cin.quality_score is not None else 0.5
                outcome = compare_exact_identifier(
                    val1=f1_cin.value,
                    val2=f2_cin.value,
                    field_label="Registration Number",
                    source1_label=f"Incorporation Cert 1 ('{doc1.original_filename}')",
                    source2_label=f"Incorporation Cert 2 ('{doc2.original_filename}')",
                    quality1=score1,
                    quality2=score2,
                    is_critical=True,
                    is_sensitive=True,
                )
                findings.append(
                    EvaluatedRuleFinding(
                        field_name="registration_number_intra_conflict",
                        comparison_type=ComparisonType.EXACT_IDENTIFIER,
                        result=outcome.result,
                        severity=outcome.severity,
                        explanation=outcome.explanation,
                        similarity_score=outcome.similarity_score,
                        comparison_summary=outcome.comparison_summary,
                        evidence_sources=[ev1_cin, ev2_cin],
                    )
                )
    return findings


# -----------------------------------------------------------------------------
# Rule 5: Registration Number (Vendor Profile vs Certificate of Incorporation)
# -----------------------------------------------------------------------------
def rule_reg_number_inc(ctx: VerificationRuleContext) -> List[EvaluatedRuleFinding]:
    profile_reg = ctx.vendor_dict.get("registration_number")
    ev_profile = build_profile_evidence("registration_number", profile_reg)
    all_docs = ctx.category_docs.get("CERTIFICATE_OF_INCORPORATION", [])
    eligible_docs = ctx.eligible_docs.get("CERTIFICATE_OF_INCORPORATION", [])

    if not all_docs:
        return [
            EvaluatedRuleFinding(
                field_name="registration_number",
                comparison_type=ComparisonType.EXACT_IDENTIFIER,
                result=FindingResult.MISSING_DOCUMENT,
                severity=FindingSeverity.WARNING,
                explanation="Certificate of Incorporation missing. Cannot verify statutory registration number.",
                comparison_summary="Incorporation Certificate missing",
                evidence_sources=[ev_profile],
            )
        ]

    if not eligible_docs:
        return [
            EvaluatedRuleFinding(
                field_name="registration_number",
                comparison_type=ComparisonType.EXACT_IDENTIFIER,
                result=FindingResult.INSUFFICIENT_EVIDENCE,
                severity=FindingSeverity.INFO,
                explanation="No eligible Certificate of Incorporation available for registration number check.",
                comparison_summary="Incorporation Certificate evidence ineligible",
                evidence_sources=[ev_profile],
            )
        ]

    findings: List[EvaluatedRuleFinding] = []
    for doc_ctx in eligible_docs:
        doc = doc_ctx.document
        ext = doc_ctx.extraction
        reg_field = doc_ctx.fields.get("cin_or_reg_number")
        ev_doc = build_doc_evidence(
            doc, ext, reg_field, "cin_or_reg_number",
            classification_id=doc_ctx.classification.id if doc_ctx.classification else None,
        )

        if not ext or not reg_field or reg_field.status == FieldStatus.MISSING:
            findings.append(
                EvaluatedRuleFinding(
                    field_name="registration_number",
                    comparison_type=ComparisonType.EXACT_IDENTIFIER,
                    result=FindingResult.INSUFFICIENT_EVIDENCE,
                    severity=FindingSeverity.INFO,
                    explanation=f"Registration number / CIN could not be located in Certificate of Incorporation ('{doc.original_filename}').",
                    comparison_summary=f"Registration number missing in document ({doc.original_filename})",
                    evidence_sources=[ev_profile, ev_doc],
                )
            )
            continue

        if reg_field.status == FieldStatus.UNREADABLE:
            findings.append(
                EvaluatedRuleFinding(
                    field_name="registration_number",
                    comparison_type=ComparisonType.EXACT_IDENTIFIER,
                    result=FindingResult.INSUFFICIENT_EVIDENCE,
                    severity=FindingSeverity.INFO,
                    explanation=f"Registration number in Certificate of Incorporation ('{doc.original_filename}') is unreadable.",
                    comparison_summary=f"Registration number unreadable in document ({doc.original_filename})",
                    evidence_sources=[ev_profile, ev_doc],
                )
            )
            continue

        score = reg_field.quality_score if reg_field.quality_score is not None else 0.5
        outcome = compare_exact_identifier(
            val1=profile_reg,
            val2=reg_field.value,
            field_label="Registration Number",
            source1_label="Vendor Profile",
            source2_label=f"Incorporation Certificate ('{doc.original_filename}')",
            quality1=1.0,
            quality2=score,
            is_critical=True,
            is_sensitive=True,
        )

        findings.append(
            EvaluatedRuleFinding(
                field_name="registration_number",
                comparison_type=ComparisonType.EXACT_IDENTIFIER,
                result=outcome.result,
                severity=outcome.severity,
                explanation=outcome.explanation,
                similarity_score=outcome.similarity_score,
                comparison_summary=outcome.comparison_summary,
                evidence_sources=[ev_profile, ev_doc],
            )
        )
    return findings


# -----------------------------------------------------------------------------
# Rule 6: Account Holder Name (Vendor Profile vs Bank Proof(s))
# -----------------------------------------------------------------------------
def rule_account_holder_name(ctx: VerificationRuleContext) -> List[EvaluatedRuleFinding]:
    profile_holder = ctx.vendor_dict.get("bank_account_holder_name")
    ev_profile = build_profile_evidence("bank_account_holder_name", profile_holder)
    all_docs = ctx.category_docs.get("BANK_PROOF", [])
    eligible_docs = ctx.eligible_docs.get("BANK_PROOF", [])

    if not all_docs:
        return [
            EvaluatedRuleFinding(
                field_name="account_holder_name",
                comparison_type=ComparisonType.FUZZY_NAME,
                result=FindingResult.MISSING_DOCUMENT,
                severity=FindingSeverity.WARNING,
                explanation="Bank Proof (cheque or statement) missing. Cannot verify bank account beneficiary name.",
                comparison_summary="Bank Proof missing",
                evidence_sources=[ev_profile],
            )
        ]

    if not eligible_docs:
        return [
            EvaluatedRuleFinding(
                field_name="account_holder_name",
                comparison_type=ComparisonType.FUZZY_NAME,
                result=FindingResult.INSUFFICIENT_EVIDENCE,
                severity=FindingSeverity.INFO,
                explanation="No eligible Bank Proof available for account holder name verification.",
                comparison_summary="Bank Proof evidence ineligible",
                evidence_sources=[ev_profile],
            )
        ]

    findings: List[EvaluatedRuleFinding] = []
    for doc_ctx in eligible_docs:
        doc = doc_ctx.document
        ext = doc_ctx.extraction
        name_field = doc_ctx.fields.get("account_holder_name")
        ev_doc = build_doc_evidence(
            doc, ext, name_field, "account_holder_name",
            classification_id=doc_ctx.classification.id if doc_ctx.classification else None,
        )

        if not ext or not name_field or name_field.status == FieldStatus.MISSING:
            findings.append(
                EvaluatedRuleFinding(
                    field_name="account_holder_name",
                    comparison_type=ComparisonType.FUZZY_NAME,
                    result=FindingResult.INSUFFICIENT_EVIDENCE,
                    severity=FindingSeverity.INFO,
                    explanation=f"Account holder name could not be located in Bank Proof ('{doc.original_filename}').",
                    comparison_summary=f"Account holder name missing in bank document ({doc.original_filename})",
                    evidence_sources=[ev_profile, ev_doc],
                )
            )
            continue

        if name_field.status == FieldStatus.UNREADABLE:
            findings.append(
                EvaluatedRuleFinding(
                    field_name="account_holder_name",
                    comparison_type=ComparisonType.FUZZY_NAME,
                    result=FindingResult.INSUFFICIENT_EVIDENCE,
                    severity=FindingSeverity.INFO,
                    explanation=f"Account holder name in Bank Proof ('{doc.original_filename}') is unreadable.",
                    comparison_summary=f"Account holder name unreadable in bank document ({doc.original_filename})",
                    evidence_sources=[ev_profile, ev_doc],
                )
            )
            continue

        score = name_field.quality_score if name_field.quality_score is not None else 0.5
        outcome = compare_company_names(
            name1=profile_holder,
            name2=name_field.value,
            field_label="Account Holder Name",
            source1_label="Vendor Profile",
            source2_label=f"Bank Proof ('{doc.original_filename}')",
            quality1=1.0,
            quality2=score,
            is_critical=True,
        )

        findings.append(
            EvaluatedRuleFinding(
                field_name="account_holder_name",
                comparison_type=ComparisonType.FUZZY_NAME,
                result=outcome.result,
                severity=outcome.severity,
                explanation=outcome.explanation,
                similarity_score=outcome.similarity_score,
                comparison_summary=outcome.comparison_summary,
                evidence_sources=[ev_profile, ev_doc],
            )
        )
    return findings


# -----------------------------------------------------------------------------
# Rule 7: Bank Account Number (Vendor Profile vs Bank Proof(s))
# -----------------------------------------------------------------------------
def rule_bank_account_number(ctx: VerificationRuleContext) -> List[EvaluatedRuleFinding]:
    profile_acc = ctx.vendor_dict.get("bank_account_number")
    ev_profile = build_profile_evidence("bank_account_number", profile_acc, is_masked=True)
    all_docs = ctx.category_docs.get("BANK_PROOF", [])
    eligible_docs = ctx.eligible_docs.get("BANK_PROOF", [])

    if not all_docs:
        return [
            EvaluatedRuleFinding(
                field_name="bank_account_number",
                comparison_type=ComparisonType.EXACT_IDENTIFIER,
                result=FindingResult.MISSING_DOCUMENT,
                severity=FindingSeverity.WARNING,
                explanation="Bank Proof missing. Cannot verify settlement bank account number.",
                comparison_summary="Bank Proof missing",
                evidence_sources=[ev_profile],
            )
        ]

    if not eligible_docs:
        return [
            EvaluatedRuleFinding(
                field_name="bank_account_number",
                comparison_type=ComparisonType.EXACT_IDENTIFIER,
                result=FindingResult.INSUFFICIENT_EVIDENCE,
                severity=FindingSeverity.INFO,
                explanation="No eligible Bank Proof available for account number verification.",
                comparison_summary="Bank Proof evidence ineligible",
                evidence_sources=[ev_profile],
            )
        ]

    findings: List[EvaluatedRuleFinding] = []
    for doc_ctx in eligible_docs:
        doc = doc_ctx.document
        ext = doc_ctx.extraction
        acc_field = doc_ctx.fields.get("account_number")
        ev_doc = build_doc_evidence(
            doc, ext, acc_field, "account_number",
            classification_id=doc_ctx.classification.id if doc_ctx.classification else None,
        )

        if not ext or not acc_field or acc_field.status == FieldStatus.MISSING:
            findings.append(
                EvaluatedRuleFinding(
                    field_name="bank_account_number",
                    comparison_type=ComparisonType.EXACT_IDENTIFIER,
                    result=FindingResult.INSUFFICIENT_EVIDENCE,
                    severity=FindingSeverity.INFO,
                    explanation=f"Account number could not be located in Bank Proof ('{doc.original_filename}').",
                    comparison_summary=f"Account number missing in bank document ({doc.original_filename})",
                    evidence_sources=[ev_profile, ev_doc],
                )
            )
            continue

        if acc_field.status == FieldStatus.UNREADABLE:
            findings.append(
                EvaluatedRuleFinding(
                    field_name="bank_account_number",
                    comparison_type=ComparisonType.EXACT_IDENTIFIER,
                    result=FindingResult.INSUFFICIENT_EVIDENCE,
                    severity=FindingSeverity.INFO,
                    explanation=f"Account number in Bank Proof ('{doc.original_filename}') is unreadable.",
                    comparison_summary=f"Account number unreadable in bank document ({doc.original_filename})",
                    evidence_sources=[ev_profile, ev_doc],
                )
            )
            continue

        score = acc_field.quality_score if acc_field.quality_score is not None else 0.5
        outcome = compare_account_numbers(
            val1=profile_acc,
            val2=acc_field.value,
            source1_label="Vendor Profile",
            source2_label=f"Bank Proof ('{doc.original_filename}')",
            quality1=1.0,
            quality2=score,
        )

        findings.append(
            EvaluatedRuleFinding(
                field_name="bank_account_number",
                comparison_type=ComparisonType.EXACT_IDENTIFIER,
                result=outcome.result,
                severity=outcome.severity,
                explanation=outcome.explanation,
                similarity_score=outcome.similarity_score,
                comparison_summary=outcome.comparison_summary,
                evidence_sources=[ev_profile, ev_doc],
            )
        )
    return findings


# -----------------------------------------------------------------------------
# Rule 8: Bank Routing / IFSC Code (Vendor Profile vs Bank Proof(s))
# -----------------------------------------------------------------------------
def rule_bank_routing_number(ctx: VerificationRuleContext) -> List[EvaluatedRuleFinding]:
    profile_routing = ctx.vendor_dict.get("bank_routing_number")
    ev_profile = build_profile_evidence("bank_routing_number", profile_routing)
    all_docs = ctx.category_docs.get("BANK_PROOF", [])
    eligible_docs = ctx.eligible_docs.get("BANK_PROOF", [])

    if not all_docs:
        return [
            EvaluatedRuleFinding(
                field_name="ifsc_code",
                comparison_type=ComparisonType.EXACT_IDENTIFIER,
                result=FindingResult.MISSING_DOCUMENT,
                severity=FindingSeverity.WARNING,
                explanation="Bank Proof missing. Cannot verify bank routing/IFSC code.",
                comparison_summary="Bank Proof missing",
                evidence_sources=[ev_profile],
            )
        ]

    if not eligible_docs:
        return [
            EvaluatedRuleFinding(
                field_name="ifsc_code",
                comparison_type=ComparisonType.EXACT_IDENTIFIER,
                result=FindingResult.INSUFFICIENT_EVIDENCE,
                severity=FindingSeverity.INFO,
                explanation="No eligible Bank Proof available for routing/IFSC verification.",
                comparison_summary="Bank Proof evidence ineligible",
                evidence_sources=[ev_profile],
            )
        ]

    findings: List[EvaluatedRuleFinding] = []
    for doc_ctx in eligible_docs:
        doc = doc_ctx.document
        ext = doc_ctx.extraction
        ifsc_field = doc_ctx.fields.get("ifsc_code")
        ev_doc = build_doc_evidence(
            doc, ext, ifsc_field, "ifsc_code",
            classification_id=doc_ctx.classification.id if doc_ctx.classification else None,
        )

        if not ext or not ifsc_field or ifsc_field.status == FieldStatus.MISSING:
            findings.append(
                EvaluatedRuleFinding(
                    field_name="ifsc_code",
                    comparison_type=ComparisonType.EXACT_IDENTIFIER,
                    result=FindingResult.INSUFFICIENT_EVIDENCE,
                    severity=FindingSeverity.INFO,
                    explanation=f"Routing / IFSC code could not be located in Bank Proof ('{doc.original_filename}').",
                    comparison_summary=f"Routing code missing in bank document ({doc.original_filename})",
                    evidence_sources=[ev_profile, ev_doc],
                )
            )
            continue

        if ifsc_field.status == FieldStatus.UNREADABLE:
            findings.append(
                EvaluatedRuleFinding(
                    field_name="ifsc_code",
                    comparison_type=ComparisonType.EXACT_IDENTIFIER,
                    result=FindingResult.INSUFFICIENT_EVIDENCE,
                    severity=FindingSeverity.INFO,
                    explanation=f"Routing / IFSC code in Bank Proof ('{doc.original_filename}') is unreadable.",
                    comparison_summary=f"Routing code unreadable in bank document ({doc.original_filename})",
                    evidence_sources=[ev_profile, ev_doc],
                )
            )
            continue

        score = ifsc_field.quality_score if ifsc_field.quality_score is not None else 0.5
        outcome = compare_exact_identifier(
            val1=profile_routing,
            val2=ifsc_field.value,
            field_label="Routing / IFSC Code",
            source1_label="Vendor Profile",
            source2_label=f"Bank Proof ('{doc.original_filename}')",
            quality1=1.0,
            quality2=score,
            is_sensitive=True,
        )

        findings.append(
            EvaluatedRuleFinding(
                field_name="ifsc_code",
                comparison_type=ComparisonType.EXACT_IDENTIFIER,
                result=outcome.result,
                severity=outcome.severity,
                explanation=outcome.explanation,
                similarity_score=outcome.similarity_score,
                comparison_summary=outcome.comparison_summary,
                evidence_sources=[ev_profile, ev_doc],
            )
        )
    return findings


# -----------------------------------------------------------------------------
# Rule 8.1: Intra-Document Bank Proof Conflict (Multiple Bank Proofs)
# -----------------------------------------------------------------------------
def rule_bank_intra_doc_conflict(ctx: VerificationRuleContext) -> List[EvaluatedRuleFinding]:
    """Identifies conflicts between multiple uploaded Bank Proofs (account number & holder name)."""
    eligible_bank_docs = ctx.eligible_docs.get("BANK_PROOF", [])
    if len(eligible_bank_docs) < 2:
        return []

    findings: List[EvaluatedRuleFinding] = []
    for i in range(len(eligible_bank_docs)):
        for j in range(i + 1, len(eligible_bank_docs)):
            doc1_ctx = eligible_bank_docs[i]
            doc2_ctx = eligible_bank_docs[j]
            doc1, ext1 = doc1_ctx.document, doc1_ctx.extraction
            doc2, ext2 = doc2_ctx.document, doc2_ctx.extraction

            # 1. Compare Bank Account Number
            acc1 = doc1_ctx.fields.get("account_number")
            acc2 = doc2_ctx.fields.get("account_number")
            ev1_acc = build_doc_evidence(doc1, ext1, acc1, "account_number", classification_id=doc1_ctx.classification.id if doc1_ctx.classification else None)
            ev2_acc = build_doc_evidence(doc2, ext2, acc2, "account_number", classification_id=doc2_ctx.classification.id if doc2_ctx.classification else None)

            if acc1 and acc1.value and acc2 and acc2.value:
                score1 = acc1.quality_score if acc1.quality_score is not None else 0.5
                score2 = acc2.quality_score if acc2.quality_score is not None else 0.5
                outcome_acc = compare_account_numbers(
                    val1=acc1.value,
                    val2=acc2.value,
                    source1_label=f"Bank Proof 1 ('{doc1.original_filename}')",
                    source2_label=f"Bank Proof 2 ('{doc2.original_filename}')",
                    quality1=score1,
                    quality2=score2,
                )
                if outcome_acc.result == FindingResult.MATCH:
                    expl = (
                        f"Intra-document bank account consistency: Bank Proof ('{doc1.original_filename}') and "
                        f"Bank Proof ('{doc2.original_filename}') agree on account number ({mask_account_number(acc1.value)})."
                    )
                    summary = f"Matching account number ({mask_account_number(acc1.value)})"
                else:
                    expl = (
                        f"Conflicting bank proofs detected: '{doc1.original_filename}' specifies "
                        f"{mask_account_number(acc1.value)} whereas '{doc2.original_filename}' specifies "
                        f"{mask_account_number(acc2.value)}."
                    )
                    summary = f"Account number conflict: {mask_account_number(acc1.value)} ≠ {mask_account_number(acc2.value)}"

                findings.append(
                    EvaluatedRuleFinding(
                        field_name="bank_account_intra_conflict",
                        comparison_type=ComparisonType.EXACT_IDENTIFIER,
                        result=outcome_acc.result,
                        severity=outcome_acc.severity,
                        explanation=expl,
                        similarity_score=outcome_acc.similarity_score,
                        comparison_summary=summary,
                        evidence_sources=[ev1_acc, ev2_acc],
                    )
                )

            # 2. Compare Account Holder Name
            h1 = doc1_ctx.fields.get("account_holder_name")
            h2 = doc2_ctx.fields.get("account_holder_name")
            ev1_h = build_doc_evidence(doc1, ext1, h1, "account_holder_name", classification_id=doc1_ctx.classification.id if doc1_ctx.classification else None)
            ev2_h = build_doc_evidence(doc2, ext2, h2, "account_holder_name", classification_id=doc2_ctx.classification.id if doc2_ctx.classification else None)

            if h1 and h1.value and h2 and h2.value:
                score1 = h1.quality_score if h1.quality_score is not None else 0.5
                score2 = h2.quality_score if h2.quality_score is not None else 0.5
                outcome_h = compare_company_names(
                    name1=h1.value,
                    name2=h2.value,
                    field_label="Account Holder Name",
                    source1_label=f"Bank Proof 1 ('{doc1.original_filename}')",
                    source2_label=f"Bank Proof 2 ('{doc2.original_filename}')",
                    quality1=score1,
                    quality2=score2,
                )
                if outcome_h.result != FindingResult.MATCH:
                    findings.append(
                        EvaluatedRuleFinding(
                            field_name="account_holder_intra_conflict",
                            comparison_type=ComparisonType.FUZZY_NAME,
                            result=FindingResult.POTENTIAL_DISCREPANCY,
                            severity=FindingSeverity.WARNING,
                            explanation=(
                                f"Conflicting account-holder information between bank proofs: '{doc1.original_filename}' "
                                f"states '{h1.value}' whereas '{doc2.original_filename}' states '{h2.value}'."
                            ),
                            comparison_summary=f"Holder conflict: '{h1.value}' ≠ '{h2.value}'",
                            evidence_sources=[ev1_h, ev2_h],
                        )
                    )
    return findings


# -----------------------------------------------------------------------------
# Rule 8.2: Bank Account Holder Cross-Doc (Bank Proof vs Legal Entity Name)
# -----------------------------------------------------------------------------
def rule_bank_holder_doc_cross(ctx: VerificationRuleContext) -> List[EvaluatedRuleFinding]:
    """Cross-compares Bank Proof account holder name vs Tax and Incorporation entity names."""
    el_bank = ctx.eligible_docs.get("BANK_PROOF", [])
    el_tax = ctx.eligible_docs.get("TAX_CERTIFICATE", [])
    el_inc = ctx.eligible_docs.get("CERTIFICATE_OF_INCORPORATION", [])

    if not el_bank:
        return []

    findings: List[EvaluatedRuleFinding] = []
    # Check Bank Proof holder vs Tax Certificate legal entity name
    for bank_ctx, tax_ctx in product(el_bank, el_tax):
        bank_doc, bank_ext = bank_ctx.document, bank_ctx.extraction
        tax_doc, tax_ext = tax_ctx.document, tax_ctx.extraction

        h_field = bank_ctx.fields.get("account_holder_name")
        tax_field = tax_ctx.fields.get("legal_entity_name")

        if h_field and h_field.value and tax_field and tax_field.value:
            ev_bank = build_doc_evidence(bank_doc, bank_ext, h_field, "account_holder_name", classification_id=bank_ctx.classification.id if bank_ctx.classification else None)
            ev_tax = build_doc_evidence(tax_doc, tax_ext, tax_field, "legal_entity_name", classification_id=tax_ctx.classification.id if tax_ctx.classification else None)
            score1 = h_field.quality_score if h_field.quality_score is not None else 0.5
            score2 = tax_field.quality_score if tax_field.quality_score is not None else 0.5
            outcome = compare_company_names(
                name1=h_field.value,
                name2=tax_field.value,
                field_label="Account Holder vs Tax Entity Name",
                source1_label=f"Bank Proof ('{bank_doc.original_filename}')",
                source2_label=f"Tax Certificate ('{tax_doc.original_filename}')",
                quality1=score1,
                quality2=score2,
            )
            findings.append(
                EvaluatedRuleFinding(
                    field_name="bank_holder_cross_check",
                    comparison_type=ComparisonType.FUZZY_NAME,
                    result=outcome.result,
                    severity=outcome.severity,
                    explanation=outcome.explanation,
                    similarity_score=outcome.similarity_score,
                    comparison_summary=outcome.comparison_summary,
                    evidence_sources=[ev_bank, ev_tax],
                )
            )

    return findings


# -----------------------------------------------------------------------------
# Rule 9: Registered Address (Vendor Profile vs Tax Certificate(s))
# -----------------------------------------------------------------------------
def rule_registered_address_gst(ctx: VerificationRuleContext) -> List[EvaluatedRuleFinding]:
    profile_addr = f"{ctx.vendor_dict.get('address_line1', '')} {ctx.vendor_dict.get('address_line2', '')} {ctx.vendor_dict.get('city', '')} {ctx.vendor_dict.get('state_province', '')} {ctx.vendor_dict.get('postal_code', '')} {ctx.vendor_dict.get('address_country', '')}".strip()
    ev_profile = build_profile_evidence("registered_address", profile_addr)
    all_docs = ctx.category_docs.get("TAX_CERTIFICATE", [])
    eligible_docs = ctx.eligible_docs.get("TAX_CERTIFICATE", [])

    if not all_docs:
        return [
            EvaluatedRuleFinding(
                field_name="registered_address",
                comparison_type=ComparisonType.FUZZY_ADDRESS,
                result=FindingResult.MISSING_DOCUMENT,
                severity=FindingSeverity.WARNING,
                explanation="Tax Certificate missing. Cannot verify principal place of business / address.",
                comparison_summary="Tax Certificate missing",
                evidence_sources=[ev_profile],
            )
        ]

    if not eligible_docs:
        return [
            EvaluatedRuleFinding(
                field_name="registered_address",
                comparison_type=ComparisonType.FUZZY_ADDRESS,
                result=FindingResult.INSUFFICIENT_EVIDENCE,
                severity=FindingSeverity.INFO,
                explanation="No eligible Tax Certificate available for registered address verification.",
                comparison_summary="Tax Certificate evidence ineligible",
                evidence_sources=[ev_profile],
            )
        ]

    findings: List[EvaluatedRuleFinding] = []
    for doc_ctx in eligible_docs:
        doc = doc_ctx.document
        ext = doc_ctx.extraction
        addr_field = doc_ctx.fields.get("registered_address")
        ev_doc = build_doc_evidence(
            doc, ext, addr_field, "registered_address",
            classification_id=doc_ctx.classification.id if doc_ctx.classification else None,
        )

        if not ext or not addr_field or addr_field.status == FieldStatus.MISSING:
            findings.append(
                EvaluatedRuleFinding(
                    field_name="registered_address",
                    comparison_type=ComparisonType.FUZZY_ADDRESS,
                    result=FindingResult.INSUFFICIENT_EVIDENCE,
                    severity=FindingSeverity.INFO,
                    explanation=f"Address could not be located in Tax Certificate ('{doc.original_filename}').",
                    comparison_summary=f"Address missing in tax document ({doc.original_filename})",
                    evidence_sources=[ev_profile, ev_doc],
                )
            )
            continue

        if addr_field.status == FieldStatus.UNREADABLE:
            findings.append(
                EvaluatedRuleFinding(
                    field_name="registered_address",
                    comparison_type=ComparisonType.FUZZY_ADDRESS,
                    result=FindingResult.INSUFFICIENT_EVIDENCE,
                    severity=FindingSeverity.INFO,
                    explanation=f"Address in Tax Certificate ('{doc.original_filename}') is unreadable.",
                    comparison_summary=f"Address unreadable in tax document ({doc.original_filename})",
                    evidence_sources=[ev_profile, ev_doc],
                )
            )
            continue

        score = addr_field.quality_score if addr_field.quality_score is not None else 0.5
        outcome = compare_addresses(
            addr1=profile_addr,
            addr2=addr_field.value,
            field_label="Registered Address",
            source1_label="Vendor Profile",
            source2_label=f"Tax Certificate ('{doc.original_filename}')",
            postal_code1=ctx.vendor_dict.get("postal_code"),
            city1=ctx.vendor_dict.get("city"),
            quality1=1.0,
            quality2=score,
        )

        findings.append(
            EvaluatedRuleFinding(
                field_name="registered_address",
                comparison_type=ComparisonType.FUZZY_ADDRESS,
                result=outcome.result,
                severity=outcome.severity,
                explanation=outcome.explanation,
                similarity_score=outcome.similarity_score,
                comparison_summary=outcome.comparison_summary,
                evidence_sources=[ev_profile, ev_doc],
            )
        )
    return findings


# -----------------------------------------------------------------------------
# Rule 10: Registered Address (Vendor Profile vs Address Proof(s))
# -----------------------------------------------------------------------------
def rule_registered_address_proof(ctx: VerificationRuleContext) -> List[EvaluatedRuleFinding]:
    profile_addr = f"{ctx.vendor_dict.get('address_line1', '')} {ctx.vendor_dict.get('address_line2', '')} {ctx.vendor_dict.get('city', '')} {ctx.vendor_dict.get('state_province', '')} {ctx.vendor_dict.get('postal_code', '')} {ctx.vendor_dict.get('address_country', '')}".strip()
    ev_profile = build_profile_evidence("registered_address", profile_addr)
    all_docs = ctx.category_docs.get("ADDRESS_PROOF", [])
    eligible_docs = ctx.eligible_docs.get("ADDRESS_PROOF", [])

    if not all_docs:
        return [
            EvaluatedRuleFinding(
                field_name="registered_address",
                comparison_type=ComparisonType.FUZZY_ADDRESS,
                result=FindingResult.MISSING_DOCUMENT,
                severity=FindingSeverity.INFO,
                explanation="Address Proof document not uploaded.",
                comparison_summary="Address Proof missing",
                evidence_sources=[ev_profile],
            )
        ]

    if not eligible_docs:
        return [
            EvaluatedRuleFinding(
                field_name="registered_address",
                comparison_type=ComparisonType.FUZZY_ADDRESS,
                result=FindingResult.INSUFFICIENT_EVIDENCE,
                severity=FindingSeverity.INFO,
                explanation="No eligible Address Proof available for registered address verification.",
                comparison_summary="Address Proof evidence ineligible",
                evidence_sources=[ev_profile],
            )
        ]

    findings: List[EvaluatedRuleFinding] = []
    for doc_ctx in eligible_docs:
        doc = doc_ctx.document
        ext = doc_ctx.extraction
        addr_field = doc_ctx.fields.get("full_address")
        ev_doc = build_doc_evidence(
            doc, ext, addr_field, "full_address",
            classification_id=doc_ctx.classification.id if doc_ctx.classification else None,
        )

        if not ext or not addr_field or addr_field.status == FieldStatus.MISSING:
            findings.append(
                EvaluatedRuleFinding(
                    field_name="registered_address",
                    comparison_type=ComparisonType.FUZZY_ADDRESS,
                    result=FindingResult.INSUFFICIENT_EVIDENCE,
                    severity=FindingSeverity.INFO,
                    explanation=f"Address could not be located in Address Proof ('{doc.original_filename}').",
                    comparison_summary=f"Address missing in address proof ({doc.original_filename})",
                    evidence_sources=[ev_profile, ev_doc],
                )
            )
            continue

        if addr_field.status == FieldStatus.UNREADABLE:
            findings.append(
                EvaluatedRuleFinding(
                    field_name="registered_address",
                    comparison_type=ComparisonType.FUZZY_ADDRESS,
                    result=FindingResult.INSUFFICIENT_EVIDENCE,
                    severity=FindingSeverity.INFO,
                    explanation=f"Address in Address Proof ('{doc.original_filename}') is unreadable.",
                    comparison_summary=f"Address unreadable in address proof ({doc.original_filename})",
                    evidence_sources=[ev_profile, ev_doc],
                )
            )
            continue

        score = addr_field.quality_score if addr_field.quality_score is not None else 0.5
        outcome = compare_addresses(
            addr1=profile_addr,
            addr2=addr_field.value,
            field_label="Registered Address",
            source1_label="Vendor Profile",
            source2_label=f"Address Proof ('{doc.original_filename}')",
            postal_code1=ctx.vendor_dict.get("postal_code"),
            city1=ctx.vendor_dict.get("city"),
            quality1=1.0,
            quality2=score,
        )

        findings.append(
            EvaluatedRuleFinding(
                field_name="registered_address",
                comparison_type=ComparisonType.FUZZY_ADDRESS,
                result=outcome.result,
                severity=outcome.severity,
                explanation=outcome.explanation,
                similarity_score=outcome.similarity_score,
                comparison_summary=outcome.comparison_summary,
                evidence_sources=[ev_profile, ev_doc],
            )
        )
    return findings


# -----------------------------------------------------------------------------
# Rule 11: Address Cross-Doc (Tax Certificate vs Address Proof)
# -----------------------------------------------------------------------------
def rule_address_doc_cross(ctx: VerificationRuleContext) -> List[EvaluatedRuleFinding]:
    all_tax = ctx.category_docs.get("TAX_CERTIFICATE", [])
    all_addr = ctx.category_docs.get("ADDRESS_PROOF", [])
    el_tax = ctx.eligible_docs.get("TAX_CERTIFICATE", [])
    el_addr = ctx.eligible_docs.get("ADDRESS_PROOF", [])

    if not all_tax or not all_addr:
        missing = "Tax Certificate" if not all_tax else "Address Proof"
        return [
            EvaluatedRuleFinding(
                field_name="registered_address",
                comparison_type=ComparisonType.FUZZY_ADDRESS,
                result=FindingResult.MISSING_DOCUMENT,
                severity=FindingSeverity.INFO,
                explanation=f"Cross-document address comparison requires both Tax Certificate and Address Proof. Missing: {missing}.",
                comparison_summary=f"{missing} missing for address cross-doc check",
                evidence_sources=[],
            )
        ]

    if not el_tax or not el_addr:
        return [
            EvaluatedRuleFinding(
                field_name="registered_address",
                comparison_type=ComparisonType.FUZZY_ADDRESS,
                result=FindingResult.INSUFFICIENT_EVIDENCE,
                severity=FindingSeverity.INFO,
                explanation="Cross-document address check requires eligible evidence in both Tax and Address documents.",
                comparison_summary="Ineligible evidence for address cross-check",
                evidence_sources=[],
            )
        ]

    findings: List[EvaluatedRuleFinding] = []
    for tax_ctx, addr_ctx in product(el_tax, el_addr):
        tax_doc, tax_ext = tax_ctx.document, tax_ctx.extraction
        addr_doc, addr_ext = addr_ctx.document, addr_ctx.extraction

        tax_field = tax_ctx.fields.get("registered_address")
        addr_field = addr_ctx.fields.get("full_address")

        ev_tax = build_doc_evidence(tax_doc, tax_ext, tax_field, "registered_address", classification_id=tax_ctx.classification.id if tax_ctx.classification else None)
        ev_addr = build_doc_evidence(addr_doc, addr_ext, addr_field, "full_address", classification_id=addr_ctx.classification.id if addr_ctx.classification else None)

        if not tax_field or tax_field.status in (FieldStatus.MISSING, FieldStatus.UNREADABLE) or \
           not addr_field or addr_field.status in (FieldStatus.MISSING, FieldStatus.UNREADABLE):
            findings.append(
                EvaluatedRuleFinding(
                    field_name="registered_address",
                    comparison_type=ComparisonType.FUZZY_ADDRESS,
                    result=FindingResult.INSUFFICIENT_EVIDENCE,
                    severity=FindingSeverity.INFO,
                    explanation=f"Address is missing or unreadable in '{tax_doc.original_filename}' or '{addr_doc.original_filename}'.",
                    comparison_summary="Address unreadable in cross-doc check",
                    evidence_sources=[ev_tax, ev_addr],
                )
            )
            continue

        score1 = tax_field.quality_score if tax_field.quality_score is not None else 0.5
        score2 = addr_field.quality_score if addr_field.quality_score is not None else 0.5
        outcome = compare_addresses(
            addr1=tax_field.value,
            addr2=addr_field.value,
            field_label="Registered Address",
            source1_label=f"Tax Certificate ('{tax_doc.original_filename}')",
            source2_label=f"Address Proof ('{addr_doc.original_filename}')",
            quality1=score1,
            quality2=score2,
        )

        findings.append(
            EvaluatedRuleFinding(
                field_name="registered_address",
                comparison_type=ComparisonType.FUZZY_ADDRESS,
                result=outcome.result,
                severity=outcome.severity,
                explanation=outcome.explanation,
                similarity_score=outcome.similarity_score,
                comparison_summary=outcome.comparison_summary,
                evidence_sources=[ev_tax, ev_addr],
            )
        )
    return findings


# -----------------------------------------------------------------------------
# Rule 12: Incorporation / Registration Date Cross-Doc
# -----------------------------------------------------------------------------
def rule_incorporation_date(ctx: VerificationRuleContext) -> List[EvaluatedRuleFinding]:
    all_inc = ctx.category_docs.get("CERTIFICATE_OF_INCORPORATION", [])
    all_tax = ctx.category_docs.get("TAX_CERTIFICATE", [])
    el_inc = ctx.eligible_docs.get("CERTIFICATE_OF_INCORPORATION", [])
    el_tax = ctx.eligible_docs.get("TAX_CERTIFICATE", [])

    if not all_inc or not all_tax:
        missing = "Certificate of Incorporation" if not all_inc else "Tax Certificate"
        return [
            EvaluatedRuleFinding(
                field_name="incorporation_date",
                comparison_type=ComparisonType.DATE,
                result=FindingResult.MISSING_DOCUMENT,
                severity=FindingSeverity.INFO,
                explanation=f"Incorporation vs tax registration date check requires both documents. Missing: {missing}.",
                comparison_summary=f"{missing} missing for date check",
                evidence_sources=[],
            )
        ]

    if not el_inc or not el_tax:
        return [
            EvaluatedRuleFinding(
                field_name="incorporation_date",
                comparison_type=ComparisonType.DATE,
                result=FindingResult.INSUFFICIENT_EVIDENCE,
                severity=FindingSeverity.INFO,
                explanation="Date comparison requires eligible evidence in both Incorporation and Tax certificates.",
                comparison_summary="Ineligible evidence for date check",
                evidence_sources=[],
            )
        ]

    findings: List[EvaluatedRuleFinding] = []
    for inc_ctx, tax_ctx in product(el_inc, el_tax):
        inc_doc, inc_ext = inc_ctx.document, inc_ctx.extraction
        tax_doc, tax_ext = tax_ctx.document, tax_ctx.extraction

        inc_date_field = inc_ctx.fields.get("incorporation_date")
        tax_date_field = tax_ctx.fields.get("registration_date")

        ev_inc = build_doc_evidence(inc_doc, inc_ext, inc_date_field, "incorporation_date", classification_id=inc_ctx.classification.id if inc_ctx.classification else None)
        ev_tax = build_doc_evidence(tax_doc, tax_ext, tax_date_field, "registration_date", classification_id=tax_ctx.classification.id if tax_ctx.classification else None)

        if not inc_date_field or inc_date_field.status in (FieldStatus.MISSING, FieldStatus.UNREADABLE) or \
           not tax_date_field or tax_date_field.status in (FieldStatus.MISSING, FieldStatus.UNREADABLE):
            findings.append(
                EvaluatedRuleFinding(
                    field_name="incorporation_date",
                    comparison_type=ComparisonType.DATE,
                    result=FindingResult.INSUFFICIENT_EVIDENCE,
                    severity=FindingSeverity.INFO,
                    explanation=f"Statutory date is missing or unreadable in '{inc_doc.original_filename}' or '{tax_doc.original_filename}'.",
                    comparison_summary="Date unreadable in cross-doc check",
                    evidence_sources=[ev_inc, ev_tax],
                )
            )
            continue

        score1 = inc_date_field.quality_score if inc_date_field.quality_score is not None else 0.5
        score2 = tax_date_field.quality_score if tax_date_field.quality_score is not None else 0.5
        outcome = compare_dates(
            date_str1=inc_date_field.value,
            date_str2=tax_date_field.value,
            field_label="Statutory Registration Date",
            source1_label=f"Incorporation Certificate ('{inc_doc.original_filename}')",
            source2_label=f"Tax Certificate ('{tax_doc.original_filename}')",
            quality1=score1,
            quality2=score2,
        )

        findings.append(
            EvaluatedRuleFinding(
                field_name="incorporation_date",
                comparison_type=ComparisonType.DATE,
                result=outcome.result,
                severity=outcome.severity,
                explanation=outcome.explanation,
                similarity_score=outcome.similarity_score,
                comparison_summary=outcome.comparison_summary,
                evidence_sources=[ev_inc, ev_tax],
            )
        )
    return findings


# Active registry of rules
ALL_VERIFICATION_RULES: List[Callable[[VerificationRuleContext], Union[EvaluatedRuleFinding, List[EvaluatedRuleFinding]]]] = [
    rule_gstin_consistency,
    rule_gstin_intra_doc_conflict,
    rule_legal_name_gst,
    rule_legal_name_inc,
    rule_legal_name_doc_cross,
    rule_coi_intra_doc_conflict,
    rule_reg_number_inc,
    rule_account_holder_name,
    rule_bank_account_number,
    rule_bank_routing_number,
    rule_bank_intra_doc_conflict,
    rule_bank_holder_doc_cross,
    rule_registered_address_gst,
    rule_registered_address_proof,
    rule_address_doc_cross,
    rule_incorporation_date,
]
