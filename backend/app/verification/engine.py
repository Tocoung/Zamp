"""Cross-document verification engine orchestrator."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.models.vendor import Vendor
from app.models.document import VendorDocument
from app.models.extraction import DocumentExtraction
from app.schemas.extraction import ExtractedField
from app.schemas.verification import (
    FindingResult,
    FindingSeverity,
    VerificationFindingResponse,
    VerificationRunResponse,
    VerificationRunStatus,
    VerificationRunSummary,
)
from app.verification.rules import (
    ALL_VERIFICATION_RULES,
    EvaluatedRuleFinding,
    VerificationRuleContext,
)


class VerificationEngine:
    """Orchestrates deterministic cross-document validation and discrepancy scoring."""

    def __init__(self, ruleset_version: str = "1.0.0"):
        self.ruleset_version = ruleset_version

    def evaluate(
        self,
        vendor: Vendor,
        vendor_dict: Dict[str, Any],
        documents: List[VendorDocument],
        extractions: List[DocumentExtraction],
    ) -> Tuple[VerificationRunSummary, List[EvaluatedRuleFinding]]:
        """Executes all registered verification rules against vendor data and extracted document evidence."""
        run_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)

        # 1. Map each document to its latest eligible extraction
        latest_doc_extractions: Dict[str, DocumentExtraction] = {}
        for ext in sorted(extractions, key=lambda e: e.created_at or datetime.min):
            latest_doc_extractions[ext.document_id] = ext

        # 2. Build category -> (latest_doc, latest_extraction, fields_map)
        category_extractions: Dict[str, Tuple[Optional[VendorDocument], Optional[DocumentExtraction], Dict[str, ExtractedField]]] = {}
        for doc in sorted(documents, key=lambda d: d.created_at or datetime.min):
            cat = (doc.document_category or "OTHER").upper()
            ext = latest_doc_extractions.get(doc.id)
            fields_map: Dict[str, ExtractedField] = {}
            if ext and ext.fields:
                for k, v in ext.fields.items():
                    if isinstance(v, dict):
                        try:
                            fields_map[k] = ExtractedField.model_validate(v)
                        except Exception:
                            pass
            category_extractions[cat] = (doc, ext, fields_map)

        # 3. Create context and evaluate rules
        context = VerificationRuleContext(
            vendor=vendor,
            vendor_dict=vendor_dict,
            category_extractions=category_extractions,
        )

        findings: List[EvaluatedRuleFinding] = []
        for rule_fn in ALL_VERIFICATION_RULES:
            try:
                finding = rule_fn(context)
                findings.append(finding)
            except Exception as e:
                # Rule execution safety: preserve execution, log unsupported/error finding
                findings.append(
                    EvaluatedRuleFinding(
                        field_name="general",
                        comparison_type="UNSUPPORTED",
                        result=FindingResult.INSUFFICIENT_EVIDENCE,
                        severity=FindingSeverity.INFO,
                        explanation=f"Verification rule '{rule_fn.__name__}' encountered unexpected error: {type(e).__name__}.",
                        comparison_summary="Rule execution failed gracefully",
                    )
                )

        # 4. Compute summary statistics
        total_comp = len(findings)
        matches = sum(1 for f in findings if f.result == FindingResult.MATCH)
        confirmed_disc = sum(1 for f in findings if f.result == FindingResult.CONFIRMED_DISCREPANCY)
        potential_disc = sum(1 for f in findings if f.result == FindingResult.POTENTIAL_DISCREPANCY)
        insuff_ev = sum(1 for f in findings if f.result == FindingResult.INSUFFICIENT_EVIDENCE)
        missing_docs = sum(1 for f in findings if f.result == FindingResult.MISSING_DOCUMENT)
        unsupported_docs = sum(1 for f in findings if f.result == FindingResult.UNSUPPORTED_DOCUMENT)

        # 5. Determine overall VerificationRunStatus precedence (Section 7)
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
            f"Cross-document validation executed {total_comp} comparisons. "
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
                "evaluated_categories": list(category_extractions.keys()),
            },
            created_at=created_at,
        )

        return summary, findings


# Singleton instance
verification_engine = VerificationEngine()
