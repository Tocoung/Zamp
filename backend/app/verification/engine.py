"""Cross-document verification engine orchestrator."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.models.vendor import Vendor
from app.models.document import VendorDocument
from app.models.classification import DocumentClassification
from app.models.extraction import DocumentExtraction
from app.schemas.extraction import ExtractedField
from app.schemas.verification import (
    ComparisonType,
    FindingResult,
    FindingSeverity,
    VerificationFindingResponse,
    VerificationRunResponse,
    VerificationRunStatus,
    VerificationRunSummary,
)
from app.verification.rules import (
    ALL_VERIFICATION_RULES,
    DocumentEvidenceContext,
    EvaluatedRuleFinding,
    VerificationRuleContext,
    build_doc_evidence,
)
from app.verification.eligibility import evaluate_document_eligibility


class VerificationEngine:
    """Orchestrates deterministic cross-document validation, classification-aware eligibility, and discrepancy scoring."""

    def __init__(self, ruleset_version: str = "1.1.0"):
        self.ruleset_version = ruleset_version

    def evaluate(
        self,
        vendor: Vendor,
        vendor_dict: Dict[str, Any],
        documents: List[VendorDocument],
        extractions: List[DocumentExtraction],
        classifications: Optional[List[DocumentClassification]] = None,
    ) -> Tuple[VerificationRunSummary, List[EvaluatedRuleFinding]]:
        """Executes classification-aware evidence evaluation and registered cross-document verification rules."""
        run_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)

        # 1. Filter documents strictly for this vendor and sort deterministically
        vendor_docs = [d for d in documents if d.vendor_id == vendor.id]
        vendor_docs.sort(key=lambda d: (d.created_at or datetime.min, d.id))

        # 2. Map each document to its latest classification record
        latest_classifications: Dict[str, DocumentClassification] = {}
        for c in sorted(classifications or [], key=lambda x: (x.created_at or datetime.min, x.id)):
            if c.vendor_id == vendor.id:
                latest_classifications[c.document_id] = c

        # 3. Map each document to its latest extraction record
        latest_extractions: Dict[str, DocumentExtraction] = {}
        for e in sorted(extractions or [], key=lambda x: (x.created_at or datetime.min, x.id)):
            if e.vendor_id == vendor.id:
                latest_extractions[e.document_id] = e

        # 4. Evaluate evidence eligibility for each document
        category_docs: Dict[str, List[DocumentEvidenceContext]] = {}
        eligible_docs: Dict[str, List[DocumentEvidenceContext]] = {}
        eligibility_findings: List[EvaluatedRuleFinding] = []

        for doc in vendor_docs:
            c = latest_classifications.get(doc.id)
            e = latest_extractions.get(doc.id)
            elig_res = evaluate_document_eligibility(doc, c, e)

            decl_cat = elig_res.declared_category
            is_c_confirmed = elig_res.is_classification_confirmed
            c_conflict = elig_res.classification.is_conflict
            c_note = elig_res.classification.explanation if not is_c_confirmed else None
            is_e_eligible = elig_res.is_extraction_eligible
            e_note = elig_res.extraction.explanation if not is_e_eligible else None
            parsed_fields = elig_res.extraction.fields

            # Assemble DocumentEvidenceContext
            doc_ctx = DocumentEvidenceContext(
                document=doc,
                classification=c,
                is_classification_confirmed=is_c_confirmed,
                classification_conflict=c_conflict,
                classification_note=c_note,
                extraction=e,
                is_extraction_eligible=is_e_eligible,
                extraction_note=e_note,
                fields=parsed_fields,
            )

            category_docs.setdefault(decl_cat, []).append(doc_ctx)
            if is_c_confirmed and is_e_eligible:
                eligible_docs.setdefault(decl_cat, []).append(doc_ctx)

            # Generate upfront findings for classification anomalies or failed extractions
            if c_conflict:
                ev_source = build_doc_evidence(
                    doc, e, None, "document_classification",
                    classification_id=c.id if c else None,
                )
                eligibility_findings.append(
                    EvaluatedRuleFinding(
                        field_name="document_classification",
                        comparison_type=ComparisonType.UNSUPPORTED,
                        result=FindingResult.POTENTIAL_DISCREPANCY,
                        severity=FindingSeverity.WARNING,
                        explanation=c_note or "Classification conflict detected.",
                        comparison_summary=f"Declared: {decl_cat} ≠ Classified: {c.predicted_category if c else 'UNKNOWN'}",
                        evidence_sources=[ev_source],
                    )
                )
            elif not is_c_confirmed:
                ev_source = build_doc_evidence(
                    doc, e, None, "document_classification",
                    classification_id=c.id if c else None,
                )
                eligibility_findings.append(
                    EvaluatedRuleFinding(
                        field_name="document_classification",
                        comparison_type=ComparisonType.UNSUPPORTED,
                        result=FindingResult.INSUFFICIENT_EVIDENCE,
                        severity=FindingSeverity.INFO,
                        explanation=c_note or "Document classification is inconclusive.",
                        comparison_summary=f"Classification inconclusive ({doc.original_filename})",
                        evidence_sources=[ev_source],
                    )
                )

            if is_c_confirmed and not is_e_eligible:
                ev_source = build_doc_evidence(
                    doc, e, None, "document_extraction",
                    classification_id=c.id if c else None,
                )
                eligibility_findings.append(
                    EvaluatedRuleFinding(
                        field_name="document_extraction",
                        comparison_type=ComparisonType.UNSUPPORTED,
                        result=FindingResult.INSUFFICIENT_EVIDENCE,
                        severity=FindingSeverity.INFO,
                        explanation=e_note or "Document extraction is incomplete or unreadable.",
                        comparison_summary=f"Extraction incomplete ({doc.original_filename})",
                        evidence_sources=[ev_source],
                    )
                )

        # 5. Build category_extractions for backward compatibility (latest eligible doc per category)
        category_extractions: Dict[str, Tuple[Optional[VendorDocument], Optional[DocumentExtraction], Dict[str, ExtractedField]]] = {}
        for cat, doc_list in eligible_docs.items():
            if doc_list:
                latest_doc_ctx = doc_list[-1]
                category_extractions[cat] = (
                    latest_doc_ctx.document,
                    latest_doc_ctx.extraction,
                    latest_doc_ctx.fields,
                )

        # 6. Create verification rule context
        context = VerificationRuleContext(
            vendor=vendor,
            vendor_dict=vendor_dict,
            category_docs=category_docs,
            eligible_docs=eligible_docs,
            category_extractions=category_extractions,
        )

        # 7. Evaluate registered verification rules
        findings: List[EvaluatedRuleFinding] = list(eligibility_findings)
        for rule_fn in ALL_VERIFICATION_RULES:
            try:
                res = rule_fn(context)
                if isinstance(res, list):
                    findings.extend(res)
                elif res is not None:
                    findings.append(res)
            except Exception as e:
                findings.append(
                    EvaluatedRuleFinding(
                        field_name="general",
                        comparison_type=ComparisonType.UNSUPPORTED,
                        result=FindingResult.INSUFFICIENT_EVIDENCE,
                        severity=FindingSeverity.INFO,
                        explanation=f"Verification rule '{rule_fn.__name__}' encountered unexpected error: {type(e).__name__}.",
                        comparison_summary="Rule execution failed gracefully",
                    )
                )

        # 8. Compute summary statistics
        total_comp = len(findings)
        matches = sum(1 for f in findings if f.result == FindingResult.MATCH)
        confirmed_disc = sum(1 for f in findings if f.result == FindingResult.CONFIRMED_DISCREPANCY)
        potential_disc = sum(1 for f in findings if f.result == FindingResult.POTENTIAL_DISCREPANCY)
        insuff_ev = sum(1 for f in findings if f.result == FindingResult.INSUFFICIENT_EVIDENCE)
        missing_docs = sum(1 for f in findings if f.result == FindingResult.MISSING_DOCUMENT)
        unsupported_docs = sum(1 for f in findings if f.result == FindingResult.UNSUPPORTED_DOCUMENT)

        # 9. Determine overall VerificationRunStatus precedence (Section 7)
        if confirmed_disc > 0 or potential_disc > 0:
            status = VerificationRunStatus.NEEDS_REVIEW
        elif missing_docs > 0:
            status = VerificationRunStatus.INCOMPLETE
        elif insuff_ev > 0 or unsupported_docs > 0:
            status = VerificationRunStatus.COMPLETED_WITH_FINDINGS
        elif matches > 0:
            status = VerificationRunStatus.COMPLETED
        else:
            status = VerificationRunStatus.NOT_RUN

        summary_notes = (
            f"Cross-document validation executed {total_comp} comparisons across {len(vendor_docs)} document(s). "
            f"Matches: {matches}, Confirmed Discrepancies: {confirmed_disc}, "
            f"Potential Discrepancies: {potential_disc}, Incomplete Evidence: {insuff_ev + missing_docs}."
        )

        summary = VerificationRunSummary(
            id=run_id,
            vendor_id=vendor.id,
            status=status,
            ruleset_version=self.ruleset_version,
            total_comparisons=total_comp,
            matches=matches,
            confirmed_discrepancies=confirmed_disc,
            potential_discrepancies=potential_disc,
            insufficient_evidence=insuff_ev,
            missing_documents=missing_docs,
            unsupported_documents=unsupported_docs,
            summary_notes=summary_notes,
            meta={
                "evaluated_rules_count": len(ALL_VERIFICATION_RULES),
                "evaluated_categories": list(category_docs.keys()),
                "total_documents_count": len(vendor_docs),
                "eligible_documents_count": sum(len(docs) for docs in eligible_docs.values()),
            },
            created_at=created_at,
        )

        return summary, findings


# Singleton instance
verification_engine = VerificationEngine()
