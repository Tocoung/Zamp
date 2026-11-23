"""Cross-document verification rules registry and evaluation handlers."""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.models.vendor import Vendor
from app.models.document import VendorDocument
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
from app.verification.normalization import mask_account_number


@dataclass
class VerificationRuleContext:
    """Contextual data payload provided to cross-document verification rules."""
    vendor: Vendor
    vendor_dict: Dict[str, Any]
    # Category -> (latest_document, latest_extraction, fields_map)
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
    """Constructs a standardized EvidenceSource for a vendor profile field."""
    display_val = mask_account_number(str(value)) if is_masked else (str(value) if value is not None else None)
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

    if extracted_field:
        val_display = extracted_field.masked_value or extracted_field.value
        # Strict zero-leakage masking for banking account numbers
        if (extracted_field.field_name or fallback_field_name) in ("account_number", "bank_account_number"):
            val_display = mask_account_number(val_display)
        status = extracted_field.status.value if hasattr(extracted_field.status, "value") else str(extracted_field.status)
        score = extracted_field.quality_score if extracted_field.quality_score is not None else extracted_field.confidence
        if extracted_field.source:
            page_num = extracted_field.source.page_number
            method = extracted_field.source.extraction_method
            snippet = extracted_field.source.evidence_snippet

    return EvidenceSource(
        source_type=EvidenceSourceType.EXTRACTED_DOCUMENT_FIELD,
        field_name=extracted_field.field_name if extracted_field else fallback_field_name,
        value_display=val_display,
        document_id=doc.id,
        document_name=doc.original_filename,
        document_category=doc.document_category,
        extraction_id=ext.id if ext else None,
        page_number=page_num,
        extraction_method=method,
        extraction_status=status,
        confidence_score=score,
        sanitized_snippet=snippet,
    )


# -----------------------------------------------------------------------------
# Rule 1: GSTIN consistency (Vendor Profile vs Tax Certificate)
# -----------------------------------------------------------------------------
def rule_gstin_consistency(ctx: VerificationRuleContext) -> EvaluatedRuleFinding:
    profile_tax_id = ctx.vendor_dict.get("tax_id_number")
    doc, ext, fields = ctx.category_extractions.get("TAX_CERTIFICATE", (None, None, {}))

    ev_profile = build_profile_evidence("tax_id_number", profile_tax_id)

    if not doc:
        return EvaluatedRuleFinding(
            field_name="gstin",
            comparison_type=ComparisonType.EXACT_IDENTIFIER,
            result=FindingResult.MISSING_DOCUMENT,
            severity=FindingSeverity.WARNING,
            explanation="Tax Certificate (GST proof) has not been uploaded. Cannot verify statutory tax identifier.",
            comparison_summary="Tax Certificate missing",
            evidence_sources=[ev_profile],
        )

    gstin_field = fields.get("gstin")
    ev_doc = build_doc_evidence(doc, ext, gstin_field, "gstin")

    if not ext or not gstin_field or gstin_field.status == FieldStatus.MISSING:
        return EvaluatedRuleFinding(
            field_name="gstin",
            comparison_type=ComparisonType.EXACT_IDENTIFIER,
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation="GSTIN could not be located in the uploaded Tax Certificate.",
            comparison_summary="GSTIN absent from document extraction",
            evidence_sources=[ev_profile, ev_doc],
        )

    if gstin_field.status == FieldStatus.UNREADABLE:
        return EvaluatedRuleFinding(
            field_name="gstin",
            comparison_type=ComparisonType.EXACT_IDENTIFIER,
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation="GSTIN region in Tax Certificate is illegible or unreadable. Human review required.",
            comparison_summary="GSTIN unreadable in document",
            evidence_sources=[ev_profile, ev_doc],
        )

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
    )

    return EvaluatedRuleFinding(
        field_name="gstin",
        comparison_type=ComparisonType.EXACT_IDENTIFIER,
        result=outcome.result,
        severity=outcome.severity,
        explanation=outcome.explanation,
        similarity_score=outcome.similarity_score,
        comparison_summary=outcome.comparison_summary,
        evidence_sources=[ev_profile, ev_doc],
    )


# -----------------------------------------------------------------------------
# Rule 2: Legal Entity Name (Vendor Profile vs Tax Certificate)
# -----------------------------------------------------------------------------
def rule_legal_name_gst(ctx: VerificationRuleContext) -> EvaluatedRuleFinding:
    profile_name = ctx.vendor_dict.get("legal_name")
    doc, ext, fields = ctx.category_extractions.get("TAX_CERTIFICATE", (None, None, {}))
    ev_profile = build_profile_evidence("legal_name", profile_name)

    if not doc:
        return EvaluatedRuleFinding(
            field_name="legal_entity_name",
            comparison_type=ComparisonType.FUZZY_NAME,
            result=FindingResult.MISSING_DOCUMENT,
            severity=FindingSeverity.WARNING,
            explanation="Tax Certificate has not been uploaded. Cannot verify legal entity name against tax records.",
            comparison_summary="Tax Certificate missing",
            evidence_sources=[ev_profile],
        )

    name_field = fields.get("legal_entity_name")
    ev_doc = build_doc_evidence(doc, ext, name_field, "legal_entity_name")

    if not ext or not name_field or name_field.status == FieldStatus.MISSING:
        return EvaluatedRuleFinding(
            field_name="legal_entity_name",
            comparison_type=ComparisonType.FUZZY_NAME,
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation="Legal entity name could not be located in Tax Certificate.",
            comparison_summary="Legal name missing in tax document",
            evidence_sources=[ev_profile, ev_doc],
        )

    if name_field.status == FieldStatus.UNREADABLE:
        return EvaluatedRuleFinding(
            field_name="legal_entity_name",
            comparison_type=ComparisonType.FUZZY_NAME,
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation="Legal entity name in Tax Certificate is unreadable or corrupted.",
            comparison_summary="Legal name unreadable in tax document",
            evidence_sources=[ev_profile, ev_doc],
        )

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

    return EvaluatedRuleFinding(
        field_name="legal_entity_name",
        comparison_type=ComparisonType.FUZZY_NAME,
        result=outcome.result,
        severity=outcome.severity,
        explanation=outcome.explanation,
        similarity_score=outcome.similarity_score,
        comparison_summary=outcome.comparison_summary,
        evidence_sources=[ev_profile, ev_doc],
    )


# -----------------------------------------------------------------------------
# Rule 3: Legal Entity Name (Vendor Profile vs Certificate of Incorporation)
# -----------------------------------------------------------------------------
def rule_legal_name_inc(ctx: VerificationRuleContext) -> EvaluatedRuleFinding:
    profile_name = ctx.vendor_dict.get("legal_name")
    doc, ext, fields = ctx.category_extractions.get("CERTIFICATE_OF_INCORPORATION", (None, None, {}))
    ev_profile = build_profile_evidence("legal_name", profile_name)

    if not doc:
        return EvaluatedRuleFinding(
            field_name="legal_entity_name",
            comparison_type=ComparisonType.FUZZY_NAME,
            result=FindingResult.MISSING_DOCUMENT,
            severity=FindingSeverity.WARNING,
            explanation="Certificate of Incorporation has not been uploaded. Cannot verify incorporation company name.",
            comparison_summary="Incorporation Certificate missing",
            evidence_sources=[ev_profile],
        )

    name_field = fields.get("company_name")
    ev_doc = build_doc_evidence(doc, ext, name_field, "company_name")

    if not ext or not name_field or name_field.status == FieldStatus.MISSING:
        return EvaluatedRuleFinding(
            field_name="legal_entity_name",
            comparison_type=ComparisonType.FUZZY_NAME,
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation="Company name could not be located in Certificate of Incorporation.",
            comparison_summary="Company name missing in incorporation document",
            evidence_sources=[ev_profile, ev_doc],
        )

    if name_field.status == FieldStatus.UNREADABLE:
        return EvaluatedRuleFinding(
            field_name="legal_entity_name",
            comparison_type=ComparisonType.FUZZY_NAME,
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation="Company name in Certificate of Incorporation is unreadable.",
            comparison_summary="Company name unreadable in incorporation document",
            evidence_sources=[ev_profile, ev_doc],
        )

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

    return EvaluatedRuleFinding(
        field_name="legal_entity_name",
        comparison_type=ComparisonType.FUZZY_NAME,
        result=outcome.result,
        severity=outcome.severity,
        explanation=outcome.explanation,
        similarity_score=outcome.similarity_score,
        comparison_summary=outcome.comparison_summary,
        evidence_sources=[ev_profile, ev_doc],
    )


# -----------------------------------------------------------------------------
# Rule 4: Legal Entity Name Cross-Doc (Tax Certificate vs Certificate of Incorporation)
# -----------------------------------------------------------------------------
def rule_legal_name_doc_cross(ctx: VerificationRuleContext) -> EvaluatedRuleFinding:
    tax_doc, tax_ext, tax_fields = ctx.category_extractions.get("TAX_CERTIFICATE", (None, None, {}))
    inc_doc, inc_ext, inc_fields = ctx.category_extractions.get("CERTIFICATE_OF_INCORPORATION", (None, None, {}))

    ev_tax = build_doc_evidence(tax_doc, tax_ext, tax_fields.get("legal_entity_name"), "legal_entity_name")
    ev_inc = build_doc_evidence(inc_doc, inc_ext, inc_fields.get("company_name"), "company_name")

    if not tax_doc or not inc_doc:
        missing_doc = "Tax Certificate" if not tax_doc else "Certificate of Incorporation"
        return EvaluatedRuleFinding(
            field_name="legal_entity_name",
            comparison_type=ComparisonType.FUZZY_NAME,
            result=FindingResult.MISSING_DOCUMENT,
            severity=FindingSeverity.INFO,
            explanation=f"Cross-document entity name comparison requires both Tax Certificate and Incorporation Certificate. Missing: {missing_doc}.",
            comparison_summary=f"{missing_doc} missing for cross-doc check",
            evidence_sources=[ev_tax, ev_inc],
        )

    tax_field = tax_fields.get("legal_entity_name")
    inc_field = inc_fields.get("company_name")

    if not tax_field or tax_field.status in (FieldStatus.MISSING, FieldStatus.UNREADABLE) or \
       not inc_field or inc_field.status in (FieldStatus.MISSING, FieldStatus.UNREADABLE):
        return EvaluatedRuleFinding(
            field_name="legal_entity_name",
            comparison_type=ComparisonType.FUZZY_NAME,
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation="Entity name is missing or unreadable in one of the compared documents.",
            comparison_summary="Entity name unreadable in cross-doc check",
            evidence_sources=[ev_tax, ev_inc],
        )

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

    return EvaluatedRuleFinding(
        field_name="legal_entity_name",
        comparison_type=ComparisonType.FUZZY_NAME,
        result=outcome.result,
        severity=outcome.severity,
        explanation=outcome.explanation,
        similarity_score=outcome.similarity_score,
        comparison_summary=outcome.comparison_summary,
        evidence_sources=[ev_tax, ev_inc],
    )


# -----------------------------------------------------------------------------
# Rule 5: Registration Number (Vendor Profile vs Certificate of Incorporation)
# -----------------------------------------------------------------------------
def rule_reg_number_inc(ctx: VerificationRuleContext) -> EvaluatedRuleFinding:
    profile_reg = ctx.vendor_dict.get("registration_number")
    doc, ext, fields = ctx.category_extractions.get("CERTIFICATE_OF_INCORPORATION", (None, None, {}))
    ev_profile = build_profile_evidence("registration_number", profile_reg)

    if not doc:
        return EvaluatedRuleFinding(
            field_name="registration_number",
            comparison_type=ComparisonType.EXACT_IDENTIFIER,
            result=FindingResult.MISSING_DOCUMENT,
            severity=FindingSeverity.WARNING,
            explanation="Certificate of Incorporation missing. Cannot verify statutory registration number.",
            comparison_summary="Incorporation Certificate missing",
            evidence_sources=[ev_profile],
        )

    reg_field = fields.get("cin_or_reg_number")
    ev_doc = build_doc_evidence(doc, ext, reg_field, "cin_or_reg_number")

    if not ext or not reg_field or reg_field.status == FieldStatus.MISSING:
        return EvaluatedRuleFinding(
            field_name="registration_number",
            comparison_type=ComparisonType.EXACT_IDENTIFIER,
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation="Registration number / CIN could not be located in Certificate of Incorporation.",
            comparison_summary="Registration number missing in document",
            evidence_sources=[ev_profile, ev_doc],
        )

    if reg_field.status == FieldStatus.UNREADABLE:
        return EvaluatedRuleFinding(
            field_name="registration_number",
            comparison_type=ComparisonType.EXACT_IDENTIFIER,
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation="Registration number in Certificate of Incorporation is unreadable.",
            comparison_summary="Registration number unreadable in document",
            evidence_sources=[ev_profile, ev_doc],
        )

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
    )

    return EvaluatedRuleFinding(
        field_name="registration_number",
        comparison_type=ComparisonType.EXACT_IDENTIFIER,
        result=outcome.result,
        severity=outcome.severity,
        explanation=outcome.explanation,
        similarity_score=outcome.similarity_score,
        comparison_summary=outcome.comparison_summary,
        evidence_sources=[ev_profile, ev_doc],
    )


# -----------------------------------------------------------------------------
# Rule 6: Account Holder Name (Vendor Profile vs Bank Proof)
# -----------------------------------------------------------------------------
def rule_account_holder_name(ctx: VerificationRuleContext) -> EvaluatedRuleFinding:
    profile_holder = ctx.vendor_dict.get("bank_account_holder_name")
    doc, ext, fields = ctx.category_extractions.get("BANK_PROOF", (None, None, {}))
    ev_profile = build_profile_evidence("bank_account_holder_name", profile_holder)

    if not doc:
        return EvaluatedRuleFinding(
            field_name="account_holder_name",
            comparison_type=ComparisonType.FUZZY_NAME,
            result=FindingResult.MISSING_DOCUMENT,
            severity=FindingSeverity.WARNING,
            explanation="Bank Proof (cheque or statement) missing. Cannot verify bank account beneficiary name.",
            comparison_summary="Bank Proof missing",
            evidence_sources=[ev_profile],
        )

    name_field = fields.get("account_holder_name")
    ev_doc = build_doc_evidence(doc, ext, name_field, "account_holder_name")

    if not ext or not name_field or name_field.status == FieldStatus.MISSING:
        return EvaluatedRuleFinding(
            field_name="account_holder_name",
            comparison_type=ComparisonType.FUZZY_NAME,
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation="Account holder name could not be located in Bank Proof.",
            comparison_summary="Account holder name missing in bank document",
            evidence_sources=[ev_profile, ev_doc],
        )

    if name_field.status == FieldStatus.UNREADABLE:
        return EvaluatedRuleFinding(
            field_name="account_holder_name",
            comparison_type=ComparisonType.FUZZY_NAME,
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation="Account holder name in Bank Proof is unreadable.",
            comparison_summary="Account holder name unreadable in bank document",
            evidence_sources=[ev_profile, ev_doc],
        )

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

    return EvaluatedRuleFinding(
        field_name="account_holder_name",
        comparison_type=ComparisonType.FUZZY_NAME,
        result=outcome.result,
        severity=outcome.severity,
        explanation=outcome.explanation,
        similarity_score=outcome.similarity_score,
        comparison_summary=outcome.comparison_summary,
        evidence_sources=[ev_profile, ev_doc],
    )


# -----------------------------------------------------------------------------
# Rule 7: Bank Account Number (Vendor Profile vs Bank Proof)
# -----------------------------------------------------------------------------
def rule_bank_account_number(ctx: VerificationRuleContext) -> EvaluatedRuleFinding:
    profile_acc = ctx.vendor_dict.get("bank_account_number")
    doc, ext, fields = ctx.category_extractions.get("BANK_PROOF", (None, None, {}))
    ev_profile = build_profile_evidence("bank_account_number", profile_acc, is_masked=True)

    if not doc:
        return EvaluatedRuleFinding(
            field_name="bank_account_number",
            comparison_type=ComparisonType.EXACT_IDENTIFIER,
            result=FindingResult.MISSING_DOCUMENT,
            severity=FindingSeverity.WARNING,
            explanation="Bank Proof missing. Cannot verify settlement bank account number.",
            comparison_summary="Bank Proof missing",
            evidence_sources=[ev_profile],
        )

    acc_field = fields.get("account_number")
    ev_doc = build_doc_evidence(doc, ext, acc_field, "account_number")

    if not ext or not acc_field or acc_field.status == FieldStatus.MISSING:
        return EvaluatedRuleFinding(
            field_name="bank_account_number",
            comparison_type=ComparisonType.EXACT_IDENTIFIER,
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation="Account number could not be located in Bank Proof.",
            comparison_summary="Account number missing in bank document",
            evidence_sources=[ev_profile, ev_doc],
        )

    if acc_field.status == FieldStatus.UNREADABLE:
        return EvaluatedRuleFinding(
            field_name="bank_account_number",
            comparison_type=ComparisonType.EXACT_IDENTIFIER,
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation="Account number in Bank Proof is unreadable.",
            comparison_summary="Account number unreadable in bank document",
            evidence_sources=[ev_profile, ev_doc],
        )

    score = acc_field.quality_score if acc_field.quality_score is not None else 0.5
    outcome = compare_account_numbers(
        val1=profile_acc,
        val2=acc_field.value,
        source1_label="Vendor Profile",
        source2_label=f"Bank Proof ('{doc.original_filename}')",
        quality1=1.0,
        quality2=score,
    )

    return EvaluatedRuleFinding(
        field_name="bank_account_number",
        comparison_type=ComparisonType.EXACT_IDENTIFIER,
        result=outcome.result,
        severity=outcome.severity,
        explanation=outcome.explanation,
        similarity_score=outcome.similarity_score,
        comparison_summary=outcome.comparison_summary,
        evidence_sources=[ev_profile, ev_doc],
    )


# -----------------------------------------------------------------------------
# Rule 8: Bank Routing / IFSC Code (Vendor Profile vs Bank Proof)
# -----------------------------------------------------------------------------
def rule_bank_routing_number(ctx: VerificationRuleContext) -> EvaluatedRuleFinding:
    profile_routing = ctx.vendor_dict.get("bank_routing_number")
    doc, ext, fields = ctx.category_extractions.get("BANK_PROOF", (None, None, {}))
    ev_profile = build_profile_evidence("bank_routing_number", profile_routing)

    if not doc:
        return EvaluatedRuleFinding(
            field_name="ifsc_code",
            comparison_type=ComparisonType.EXACT_IDENTIFIER,
            result=FindingResult.MISSING_DOCUMENT,
            severity=FindingSeverity.WARNING,
            explanation="Bank Proof missing. Cannot verify bank routing/IFSC code.",
            comparison_summary="Bank Proof missing",
            evidence_sources=[ev_profile],
        )

    ifsc_field = fields.get("ifsc_code")
    ev_doc = build_doc_evidence(doc, ext, ifsc_field, "ifsc_code")

    if not ext or not ifsc_field or ifsc_field.status == FieldStatus.MISSING:
        return EvaluatedRuleFinding(
            field_name="ifsc_code",
            comparison_type=ComparisonType.EXACT_IDENTIFIER,
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation="Routing / IFSC code could not be located in Bank Proof.",
            comparison_summary="Routing code missing in bank document",
            evidence_sources=[ev_profile, ev_doc],
        )

    if ifsc_field.status == FieldStatus.UNREADABLE:
        return EvaluatedRuleFinding(
            field_name="ifsc_code",
            comparison_type=ComparisonType.EXACT_IDENTIFIER,
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation="Routing / IFSC code in Bank Proof is unreadable.",
            comparison_summary="Routing code unreadable in bank document",
            evidence_sources=[ev_profile, ev_doc],
        )

    score = ifsc_field.quality_score if ifsc_field.quality_score is not None else 0.5
    outcome = compare_exact_identifier(
        val1=profile_routing,
        val2=ifsc_field.value,
        field_label="Routing / IFSC Code",
        source1_label="Vendor Profile",
        source2_label=f"Bank Proof ('{doc.original_filename}')",
        quality1=1.0,
        quality2=score,
    )

    return EvaluatedRuleFinding(
        field_name="ifsc_code",
        comparison_type=ComparisonType.EXACT_IDENTIFIER,
        result=outcome.result,
        severity=outcome.severity,
        explanation=outcome.explanation,
        similarity_score=outcome.similarity_score,
        comparison_summary=outcome.comparison_summary,
        evidence_sources=[ev_profile, ev_doc],
    )


# -----------------------------------------------------------------------------
# Rule 9: Registered Address (Vendor Profile vs Tax Certificate)
# -----------------------------------------------------------------------------
def rule_registered_address_gst(ctx: VerificationRuleContext) -> EvaluatedRuleFinding:
    profile_addr = f"{ctx.vendor_dict.get('address_line1', '')} {ctx.vendor_dict.get('address_line2', '')} {ctx.vendor_dict.get('city', '')} {ctx.vendor_dict.get('state_province', '')} {ctx.vendor_dict.get('postal_code', '')} {ctx.vendor_dict.get('address_country', '')}".strip()
    doc, ext, fields = ctx.category_extractions.get("TAX_CERTIFICATE", (None, None, {}))
    ev_profile = build_profile_evidence("registered_address", profile_addr)

    if not doc:
        return EvaluatedRuleFinding(
            field_name="registered_address",
            comparison_type=ComparisonType.FUZZY_ADDRESS,
            result=FindingResult.MISSING_DOCUMENT,
            severity=FindingSeverity.WARNING,
            explanation="Tax Certificate missing. Cannot verify principal place of business / address.",
            comparison_summary="Tax Certificate missing",
            evidence_sources=[ev_profile],
        )

    addr_field = fields.get("registered_address")
    ev_doc = build_doc_evidence(doc, ext, addr_field, "registered_address")

    if not ext or not addr_field or addr_field.status == FieldStatus.MISSING:
        return EvaluatedRuleFinding(
            field_name="registered_address",
            comparison_type=ComparisonType.FUZZY_ADDRESS,
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation="Address could not be located in Tax Certificate.",
            comparison_summary="Address missing in tax document",
            evidence_sources=[ev_profile, ev_doc],
        )

    if addr_field.status == FieldStatus.UNREADABLE:
        return EvaluatedRuleFinding(
            field_name="registered_address",
            comparison_type=ComparisonType.FUZZY_ADDRESS,
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation="Address in Tax Certificate is unreadable.",
            comparison_summary="Address unreadable in tax document",
            evidence_sources=[ev_profile, ev_doc],
        )

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

    return EvaluatedRuleFinding(
        field_name="registered_address",
        comparison_type=ComparisonType.FUZZY_ADDRESS,
        result=outcome.result,
        severity=outcome.severity,
        explanation=outcome.explanation,
        similarity_score=outcome.similarity_score,
        comparison_summary=outcome.comparison_summary,
        evidence_sources=[ev_profile, ev_doc],
    )


# -----------------------------------------------------------------------------
# Rule 10: Registered Address (Vendor Profile vs Address Proof)
# -----------------------------------------------------------------------------
def rule_registered_address_proof(ctx: VerificationRuleContext) -> EvaluatedRuleFinding:
    profile_addr = f"{ctx.vendor_dict.get('address_line1', '')} {ctx.vendor_dict.get('address_line2', '')} {ctx.vendor_dict.get('city', '')} {ctx.vendor_dict.get('state_province', '')} {ctx.vendor_dict.get('postal_code', '')} {ctx.vendor_dict.get('address_country', '')}".strip()
    doc, ext, fields = ctx.category_extractions.get("ADDRESS_PROOF", (None, None, {}))
    ev_profile = build_profile_evidence("registered_address", profile_addr)

    if not doc:
        return EvaluatedRuleFinding(
            field_name="registered_address",
            comparison_type=ComparisonType.FUZZY_ADDRESS,
            result=FindingResult.MISSING_DOCUMENT,
            severity=FindingSeverity.INFO,
            explanation="Address Proof document not uploaded.",
            comparison_summary="Address Proof missing",
            evidence_sources=[ev_profile],
        )

    addr_field = fields.get("full_address")
    ev_doc = build_doc_evidence(doc, ext, addr_field, "full_address")

    if not ext or not addr_field or addr_field.status == FieldStatus.MISSING:
        return EvaluatedRuleFinding(
            field_name="registered_address",
            comparison_type=ComparisonType.FUZZY_ADDRESS,
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation="Address could not be located in Address Proof.",
            comparison_summary="Address missing in address proof",
            evidence_sources=[ev_profile, ev_doc],
        )

    if addr_field.status == FieldStatus.UNREADABLE:
        return EvaluatedRuleFinding(
            field_name="registered_address",
            comparison_type=ComparisonType.FUZZY_ADDRESS,
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation="Address in Address Proof is unreadable.",
            comparison_summary="Address unreadable in address proof",
            evidence_sources=[ev_profile, ev_doc],
        )

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

    return EvaluatedRuleFinding(
        field_name="registered_address",
        comparison_type=ComparisonType.FUZZY_ADDRESS,
        result=outcome.result,
        severity=outcome.severity,
        explanation=outcome.explanation,
        similarity_score=outcome.similarity_score,
        comparison_summary=outcome.comparison_summary,
        evidence_sources=[ev_profile, ev_doc],
    )


# -----------------------------------------------------------------------------
# Rule 11: Address Cross-Doc (Tax Certificate vs Address Proof)
# -----------------------------------------------------------------------------
def rule_address_doc_cross(ctx: VerificationRuleContext) -> EvaluatedRuleFinding:
    tax_doc, tax_ext, tax_fields = ctx.category_extractions.get("TAX_CERTIFICATE", (None, None, {}))
    addr_doc, addr_ext, addr_fields = ctx.category_extractions.get("ADDRESS_PROOF", (None, None, {}))

    ev_tax = build_doc_evidence(tax_doc, tax_ext, tax_fields.get("registered_address"), "registered_address")
    ev_addr = build_doc_evidence(addr_doc, addr_ext, addr_fields.get("full_address"), "full_address")

    if not tax_doc or not addr_doc:
        missing = "Tax Certificate" if not tax_doc else "Address Proof"
        return EvaluatedRuleFinding(
            field_name="registered_address",
            comparison_type=ComparisonType.FUZZY_ADDRESS,
            result=FindingResult.MISSING_DOCUMENT,
            severity=FindingSeverity.INFO,
            explanation=f"Cross-document address comparison requires both Tax Certificate and Address Proof. Missing: {missing}.",
            comparison_summary=f"{missing} missing for address cross-doc check",
            evidence_sources=[ev_tax, ev_addr],
        )

    tax_field = tax_fields.get("registered_address")
    addr_field = addr_fields.get("full_address")

    if not tax_field or tax_field.status in (FieldStatus.MISSING, FieldStatus.UNREADABLE) or \
       not addr_field or addr_field.status in (FieldStatus.MISSING, FieldStatus.UNREADABLE):
        return EvaluatedRuleFinding(
            field_name="registered_address",
            comparison_type=ComparisonType.FUZZY_ADDRESS,
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation="Address is missing or unreadable in one of the compared documents.",
            comparison_summary="Address unreadable in cross-doc check",
            evidence_sources=[ev_tax, ev_addr],
        )

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

    return EvaluatedRuleFinding(
        field_name="registered_address",
        comparison_type=ComparisonType.FUZZY_ADDRESS,
        result=outcome.result,
        severity=outcome.severity,
        explanation=outcome.explanation,
        similarity_score=outcome.similarity_score,
        comparison_summary=outcome.comparison_summary,
        evidence_sources=[ev_tax, ev_addr],
    )


# -----------------------------------------------------------------------------
# Rule 12: Incorporation / Registration Date Cross-Doc
# -----------------------------------------------------------------------------
def rule_incorporation_date(ctx: VerificationRuleContext) -> EvaluatedRuleFinding:
    inc_doc, inc_ext, inc_fields = ctx.category_extractions.get("CERTIFICATE_OF_INCORPORATION", (None, None, {}))
    tax_doc, tax_ext, tax_fields = ctx.category_extractions.get("TAX_CERTIFICATE", (None, None, {}))

    ev_inc = build_doc_evidence(inc_doc, inc_ext, inc_fields.get("incorporation_date"), "incorporation_date")
    ev_tax = build_doc_evidence(tax_doc, tax_ext, tax_fields.get("registration_date"), "registration_date")

    if not inc_doc or not tax_doc:
        missing = "Certificate of Incorporation" if not inc_doc else "Tax Certificate"
        return EvaluatedRuleFinding(
            field_name="incorporation_date",
            comparison_type=ComparisonType.DATE,
            result=FindingResult.MISSING_DOCUMENT,
            severity=FindingSeverity.INFO,
            explanation=f"Incorporation vs tax registration date check requires both documents. Missing: {missing}.",
            comparison_summary=f"{missing} missing for date check",
            evidence_sources=[ev_inc, ev_tax],
        )

    inc_date_field = inc_fields.get("incorporation_date")
    tax_date_field = tax_fields.get("registration_date")

    if not inc_date_field or inc_date_field.status in (FieldStatus.MISSING, FieldStatus.UNREADABLE) or \
       not tax_date_field or tax_date_field.status in (FieldStatus.MISSING, FieldStatus.UNREADABLE):
        return EvaluatedRuleFinding(
            field_name="incorporation_date",
            comparison_type=ComparisonType.DATE,
            result=FindingResult.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.INFO,
            explanation="Statutory date is missing or unreadable in one of the compared documents.",
            comparison_summary="Date unreadable in cross-doc check",
            evidence_sources=[ev_inc, ev_tax],
        )

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

    return EvaluatedRuleFinding(
        field_name="incorporation_date",
        comparison_type=ComparisonType.DATE,
        result=outcome.result,
        severity=outcome.severity,
        explanation=outcome.explanation,
        similarity_score=outcome.similarity_score,
        comparison_summary=outcome.comparison_summary,
        evidence_sources=[ev_inc, ev_tax],
    )


# Active registry of rules
ALL_VERIFICATION_RULES: List[Callable[[VerificationRuleContext], EvaluatedRuleFinding]] = [
    rule_gstin_consistency,
    rule_legal_name_gst,
    rule_legal_name_inc,
    rule_legal_name_doc_cross,
    rule_reg_number_inc,
    rule_account_holder_name,
    rule_bank_account_number,
    rule_bank_routing_number,
    rule_registered_address_gst,
    rule_registered_address_proof,
    rule_address_doc_cross,
    rule_incorporation_date,
]
