"""End-to-end Onboarding Orchestrator Service.

Coordinates document intake, classification, OCR extraction, evidence provenance,
cross-document verification, and Phase 1 deterministic validation/decision engine.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.models.vendor import Vendor
from app.models.document import VendorDocument
from app.models.classification import DocumentClassification
from app.models.extraction import DocumentExtraction
from app.models.verification import VerificationRun
from app.models.decision import VendorDecision
from app.models.activity import VendorActivity
from app.models.onboarding_process import OnboardingProcessRun
from app.schemas.onboarding_process import (
    DocumentProcessItem,
    OnboardingProcessHistoryResponse,
    OnboardingProcessRunResponse,
)
from app.schemas.extraction import ExtractionStatus, ExtractionLimitationCode
from app.services.classification_service import ClassificationService
from app.services.extraction_service import ExtractionService
from app.services.verification_service import VerificationService
from app.services.decision_service import DecisionService
from app.validation.models import ValidationFinding, Severity
from app.verification.normalization import mask_account_number
from app.verification.eligibility import (
    evaluate_classification_eligibility,
    evaluate_extraction_eligibility,
    canonicalize_category,
)
from app.core.logging import logger


class OnboardingOrchestratorError(Exception):
    """Base exception for onboarding orchestration errors."""
    pass


class VendorNotFoundError(OnboardingOrchestratorError):
    """Raised when vendor does not exist."""
    pass


REQUIRED_DOCUMENT_CATEGORIES = {
    "TAX_CERTIFICATE": ("MISSING_TAX_DOCUMENT", "Mandatory statutory tax registration document (GST certificate / Tax ID proof) is missing."),
    "CERTIFICATE_OF_INCORPORATION": ("MISSING_INCORPORATION_DOCUMENT", "Mandatory Certificate of Incorporation or commercial business registration document is missing."),
    "BANK_PROOF": ("MISSING_BANK_DOCUMENT", "Mandatory bank proof document (cancelled cheque / bank statement) is missing."),
}


class OnboardingOrchestratorService:
    """Coordinates the 8-stage automated onboarding workflow for vendors."""

    def __init__(
        self,
        classification_service: Optional[ClassificationService] = None,
        extraction_service: Optional[ExtractionService] = None,
        verification_service: Optional[VerificationService] = None,
        decision_service: Optional[DecisionService] = None,
    ):
        self.classification_service = classification_service or ClassificationService()
        self.extraction_service = extraction_service or ExtractionService()
        self.verification_service = verification_service or VerificationService()
        self.decision_service = decision_service or DecisionService()

    @staticmethod
    def _to_run_response(run: OnboardingProcessRun) -> OnboardingProcessRunResponse:
        """Converts an OnboardingProcessRun model to response schema."""
        doc_items = []
        for d in (run.document_breakdown or []):
            if isinstance(d, dict):
                doc_items.append(DocumentProcessItem(**d))
            elif isinstance(d, DocumentProcessItem):
                doc_items.append(d)

        decision_status = None
        decision_reasons = []
        if run.decision:
            decision_status = run.decision.status
            decision_reasons = run.decision.reason_codes or []

        return OnboardingProcessRunResponse(
            id=run.id,
            vendor_id=run.vendor_id,
            status=run.status,
            trigger_source=run.trigger_source,
            total_documents=run.total_documents,
            successful_documents=run.successful_documents,
            failed_documents=run.failed_documents,
            verification_run_id=run.verification_run_id,
            decision_id=run.decision_id,
            decision_status=decision_status,
            decision_reasons=decision_reasons,
            stage_results=run.stage_results or {},
            document_breakdown=doc_items,
            findings_summary=run.findings_summary or {},
            error_message=run.error_message,
            created_at=run.created_at,
            completed_at=run.completed_at,
        )

    def process_vendor_onboarding(
        self,
        db: Session,
        vendor_id: str,
        force_reprocess: bool = False,
        trigger_source: str = "MANUAL",
    ) -> OnboardingProcessRunResponse:
        """Executes the complete 8-stage onboarding workflow.

        Stages:
        1. Registration verification
        2. Document Intake evaluation
        3. Document Classification
        4. OCR & Text Recognition
        5. Structured Field Extraction
        6. Extraction Confidence & Evidence Assessment
        7. Cross-Document Verification
        8. Phase 1 Validation & Final Decision

        Idempotency:
        If vendor profile and documents are identical to the latest completed run,
        and force_reprocess is False, returns the existing run without duplicate decision records.
        """
        # 1. Fetch vendor
        vendor = db.get(Vendor, str(vendor_id))
        if not vendor:
            raise VendorNotFoundError(f"Vendor with ID '{vendor_id}' not found.")

        # 2. Retrieve all active documents for vendor (ignoring superseded, deleted, or inactive)
        documents: List[VendorDocument] = db.scalars(
            select(VendorDocument)
            .where(
                VendorDocument.vendor_id == vendor_id,
                VendorDocument.upload_status.notin_(["SUPERSEDED", "DELETED", "INACTIVE"]),
            )
            .order_by(VendorDocument.created_at.asc(), VendorDocument.id.asc())
        ).all()

        # Build comprehensive documents snapshot for change detection
        docs_snapshot = {
            str(doc.id): {
                "sha256": doc.sha256_checksum,
                "version": doc.document_version,
                "filename": doc.sanitized_filename or doc.original_filename,
                "category": doc.document_category,
                "upload_status": doc.upload_status,
                "classification_id": str(doc.latest_classification.id) if doc.latest_classification else None,
                "classification_status": doc.latest_classification.status if doc.latest_classification else None,
                "extraction_id": str(doc.latest_extraction.id) if doc.latest_extraction else None,
                "extraction_status": doc.latest_extraction.status if doc.latest_extraction else None,
            }
            for doc in documents
        }
        vendor_profile_snapshot = {
            "legal_name": vendor.legal_name,
            "registration_number": vendor.registration_number,
            "tax_id_number": vendor.tax_id_number,
            "address_line1": vendor.address_line1,
            "bank_account_holder_name": vendor.bank_account_holder_name,
            "bank_name": vendor.bank_name,
            "bank_routing_number": vendor.bank_routing_number,
            "business_type": vendor.business_type,
            "country_of_incorporation": vendor.country_of_incorporation,
            "updated_at": vendor.updated_at.isoformat() if vendor.updated_at else None,
        }

        # Check latest process run for idempotency (ONLY fully COMPLETED runs are cached)
        latest_run = db.scalar(
            select(OnboardingProcessRun)
            .where(OnboardingProcessRun.vendor_id == vendor_id)
            .order_by(desc(OnboardingProcessRun.created_at))
            .limit(1)
        )

        if (
            not force_reprocess
            and latest_run
            and latest_run.status == "COMPLETED"
            and latest_run.documents_snapshot == docs_snapshot
            and (latest_run.stage_results or {}).get("vendor_profile_snapshot") == vendor_profile_snapshot
        ):
            logger.info("Onboarding inputs unchanged for vendor %s. Returning cached run %s.", vendor_id, latest_run.id)
            return self._to_run_response(latest_run)

        # 3. Create persistent run record
        run = OnboardingProcessRun(
            vendor_id=vendor_id,
            status="IN_PROGRESS",
            trigger_source=trigger_source if not force_reprocess else "REPROCESS",
            total_documents=len(documents),
            documents_snapshot=docs_snapshot,
            stage_results={},
            document_breakdown=[],
            findings_summary={},
        )
        db.add(run)
        db.flush()

        stage_results: Dict[str, Any] = {
            "vendor_profile_snapshot": vendor_profile_snapshot,
        }
        doc_breakdown: List[Dict[str, Any]] = []
        evidence_findings: List[ValidationFinding] = []

        total_docs = len(documents)
        successful_docs = 0
        failed_docs = 0

        try:
            # ---------------------------------------------------------
            # Stage 1: Registration Validation
            # ---------------------------------------------------------
            stage_results["1_registration"] = {
                "status": "COMPLETED",
                "message": "Vendor profile verified in database.",
                "legal_name": vendor.legal_name,
                "business_type": vendor.business_type,
                "country": vendor.country_of_incorporation,
            }

            # ---------------------------------------------------------
            # Stage 2: Document Intake
            # ---------------------------------------------------------
            stage_results["2_document_intake"] = {
                "status": "COMPLETED",
                "total_documents": total_docs,
                "document_ids": [str(d.id) for d in documents],
            }

            # ---------------------------------------------------------
            # Stages 3, 4, 5: Classification, OCR & Structured Extraction
            # Process each document independently; continue if one fails
            # ---------------------------------------------------------
            classified_count = 0
            extracted_count = 0
            seen_categories = set()

            for doc in documents:
                file_display_name = doc.sanitized_filename or doc.original_filename
                doc_item: Dict[str, Any] = {
                    "document_id": str(doc.id),
                    "file_name": file_display_name,
                    "file_type": doc.mime_type,
                    "category": doc.document_category,
                    "declared_category": doc.document_category,
                    "predicted_category": None,
                    "classification_status": "PENDING",
                    "classification_confidence": None,
                    "extraction_status": "PENDING",
                    "extracted_fields_count": 0,
                    "average_confidence": None,
                    "eligible_for_verification": True,
                    "ineligible_reason_code": None,
                    "error": None,
                }

                # Step 3: Classification Execution
                cls_record = None
                try:
                    cls_record = doc.latest_classification
                    if not cls_record or force_reprocess:
                        cls_record = self.classification_service.classify_vendor_document(
                            db=db,
                            vendor_id=vendor_id,
                            document_id=str(doc.id),
                        )
                    
                    doc_item["classification_status"] = cls_record.status
                    doc_item["classification_confidence"] = cls_record.confidence_score
                    doc_item["predicted_category"] = cls_record.predicted_category
                    classified_count += 1
                except Exception as e:
                    logger.warning("Classification failed for document %s: %s", doc.id, type(e).__name__)
                    doc_item["classification_status"] = "FAILED"
                    doc_item["eligible_for_verification"] = False
                    doc_item["ineligible_reason_code"] = "DOCUMENT_CLASSIFICATION_FAILED"
                    doc_item["error"] = f"Classification execution failed ({type(e).__name__})"
                    failed_docs += 1
                    evidence_findings.append(
                        ValidationFinding(
                            rule_id="EVID_CLASSIFICATION_FAILED",
                            field="documents",
                            code="DOCUMENT_CLASSIFICATION_MISMATCH",
                            message=f"Document '{file_display_name}' could not be classified.",
                            severity=Severity.WARNING,
                            suggestion="Confirm the document is in a standard format and readable.",
                        )
                    )

                # Shared Classification Eligibility Assessment
                cls_elig = evaluate_classification_eligibility(
                    declared_category=doc.document_category,
                    classification=cls_record,
                    filename=file_display_name,
                )

                if cls_elig.is_confirmed:
                    # Satisfies mandatory category requirement and confirms evidence category
                    doc_item["category"] = cls_elig.effective_category
                    seen_categories.add(cls_elig.effective_category)
                else:
                    # Inconclusive, conflict, or failed: MUST NOT satisfy mandatory category
                    doc_item["category"] = doc.document_category
                    doc_item["eligible_for_verification"] = False
                    doc_item["ineligible_reason_code"] = cls_elig.reason_code
                    doc_item["error"] = cls_elig.explanation
                    evidence_findings.append(
                        ValidationFinding(
                            rule_id=f"EVID_{cls_elig.reason_code}",
                            field="documents",
                            code=cls_elig.reason_code,
                            message=cls_elig.explanation,
                            severity=Severity.WARNING,
                            suggestion="Ensure uploaded document content matches the declared statutory category.",
                        )
                    )

                # Step 4 & 5: OCR and Structured Information Extraction
                ext_record = None
                try:
                    ext_record = doc.latest_extraction
                    if not ext_record or force_reprocess:
                        ext_record = self.extraction_service.extract_document(
                            db=db,
                            vendor_id=vendor_id,
                            document_id=str(doc.id),
                        )

                    ext_elig = evaluate_extraction_eligibility(
                        extraction=ext_record,
                        filename=file_display_name,
                    )

                    doc_item["extraction_status"] = ext_elig.status
                    doc_item["extracted_fields_count"] = ext_elig.extracted_fields_count
                    doc_item["average_confidence"] = ext_elig.average_confidence

                    if not ext_elig.is_eligible:
                        doc_item["eligible_for_verification"] = False
                        doc_item["ineligible_reason_code"] = ext_elig.reason_code
                        doc_item["error"] = ext_elig.explanation
                        failed_docs += 1
                        evidence_findings.append(
                            ValidationFinding(
                                rule_id=f"EVID_{ext_elig.reason_code}",
                                field="documents",
                                code=ext_elig.reason_code,
                                message=ext_elig.explanation,
                                severity=Severity.WARNING,
                                suggestion="Upload an uncorrupted, high-resolution document.",
                            )
                        )
                    else:
                        extracted_count += 1
                        if cls_elig.is_confirmed:
                            successful_docs += 1
                            doc_item["eligible_for_verification"] = True
                            doc_item["ineligible_reason_code"] = None
                            doc_item["error"] = None
                        else:
                            failed_docs += 1

                except Exception as e:
                    logger.warning("Extraction failed for document %s: %s", doc.id, type(e).__name__)
                    doc_item["extraction_status"] = "FAILED"
                    doc_item["eligible_for_verification"] = False
                    doc_item["ineligible_reason_code"] = "CORRUPTED_DOCUMENT_EVIDENCE"
                    doc_item["error"] = f"Extraction process encountered an error ({type(e).__name__})"
                    failed_docs += 1
                    evidence_findings.append(
                        ValidationFinding(
                            rule_id="EVID_EXTRACTION_EXCEPTION",
                            field="documents",
                            code="CORRUPTED_DOCUMENT_EVIDENCE",
                            message=f"Document '{file_display_name}' processing encountered an error ({type(e).__name__}).",
                            severity=Severity.WARNING,
                            suggestion="Re-upload an uncorrupted PDF or image file.",
                        )
                    )

                doc_breakdown.append(doc_item)

            stage_results["3_classification"] = {
                "status": "COMPLETED" if failed_docs == 0 else "PARTIAL",
                "classified_documents": classified_count,
            }
            stage_results["4_ocr_extraction"] = {
                "status": "COMPLETED" if failed_docs == 0 else "PARTIAL",
                "extracted_documents": extracted_count,
            }
            stage_results["5_structured_extraction"] = {
                "status": "COMPLETED" if failed_docs == 0 else "PARTIAL",
                "total_fields_extracted": sum(d["extracted_fields_count"] for d in doc_breakdown),
            }

            # ---------------------------------------------------------
            # Stage 6: Extraction Confidence & Evidence Assessment
            # Check for missing mandatory document categories
            # ---------------------------------------------------------
            missing_categories = []
            for category, (finding_code, msg) in REQUIRED_DOCUMENT_CATEGORIES.items():
                if category not in seen_categories:
                    # Also check for alternate mappings (e.g. GST_CERTIFICATE vs TAX_CERTIFICATE)
                    if category == "TAX_CERTIFICATE" and any(
                        c in seen_categories for c in ("GST_CERTIFICATE", "PAN_CARD", "TAX_DOCUMENT")
                    ):
                        continue
                    missing_categories.append(category)
                    evidence_findings.append(
                        ValidationFinding(
                            rule_id=f"EVID_MISSING_{category}",
                            field="documents",
                            code=finding_code,
                            message=msg,
                            severity=Severity.WARNING,
                            suggestion="Upload the required compliance document to complete onboarding.",
                        )
                    )

            stage_results["6_evidence_assessment"] = {
                "status": "COMPLETED",
                "categories_present": list(seen_categories),
                "missing_categories": missing_categories,
            }

            # ---------------------------------------------------------
            # Stage 7: Cross-Document Verification
            # ---------------------------------------------------------
            verification_run_resp = self.verification_service.run_verification_for_vendor(
                db=db,
                vendor_id=vendor_id,
            )
            run.verification_run_id = verification_run_resp.id

            stage_results["7_cross_verification"] = {
                "status": "COMPLETED",
                "verification_run_id": verification_run_resp.id,
                "matches": verification_run_resp.matches,
                "confirmed_discrepancies": verification_run_resp.confirmed_discrepancies,
                "potential_discrepancies": verification_run_resp.potential_discrepancies,
                "missing_documents": verification_run_resp.missing_documents,
                "insufficient_evidence": verification_run_resp.insufficient_evidence,
            }

            # Map verification findings into validation evidence findings
            for finding in verification_run_resp.findings:
                if finding.result == "CONFIRMED_DISCREPANCY":
                    evidence_findings.append(
                        ValidationFinding(
                            rule_id=f"EVID_DISCREPANCY_{finding.field_name.upper()}",
                            field=finding.field_name,
                            code="DOCUMENT_VERIFICATION_DISCREPANCY",
                            message=f"Discrepancy confirmed for '{finding.field_name}': {finding.explanation}",
                            severity=Severity.WARNING,
                            suggestion="Verify profile information against uploaded statutory documentation.",
                        )
                    )
                elif finding.result == "POTENTIAL_DISCREPANCY":
                    evidence_findings.append(
                        ValidationFinding(
                            rule_id=f"EVID_POTENTIAL_{finding.field_name.upper()}",
                            field=finding.field_name,
                            code="LOW_CONFIDENCE_DOCUMENT_EVIDENCE",
                            message=f"Potential discrepancy noted for '{finding.field_name}': {finding.explanation}",
                            severity=Severity.WARNING,
                            suggestion="Review document quality and ensure high-confidence OCR extraction.",
                        )
                    )

            # ---------------------------------------------------------
            # Stage 8: Phase 1 Validation & Final Decision Integration
            # Pass evidence findings into decision service context
            # ---------------------------------------------------------
            decision_result = self.decision_service.run_decision_for_vendor(
                db=db,
                vendor_id=vendor_id,
                context={"document_evidence_findings": evidence_findings},
            )
            run.decision_id = decision_result.decision_id

            stage_results["8_decision"] = {
                "status": "COMPLETED",
                "decision_id": decision_result.decision_id,
                "decision_status": decision_result.status.value,
                "reason_codes": decision_result.reason_codes,
            }

            # Consolidated findings count summary
            findings_summary = {
                "matches": verification_run_resp.matches,
                "confirmed_discrepancies": verification_run_resp.confirmed_discrepancies,
                "potential_discrepancies": verification_run_resp.potential_discrepancies,
                "missing_documents": len(missing_categories),
                "unreadable_documents": sum(1 for d in doc_breakdown if d["extraction_status"] == "INSUFFICIENT_TEXT"),
                "failed_documents": failed_docs,
            }

            # Determine overall process run status
            if failed_docs > 0:
                run.status = "PARTIAL_FAILURE"
            else:
                run.status = "COMPLETED"

            run.total_documents = total_docs
            run.successful_documents = successful_docs
            run.failed_documents = failed_docs
            run.stage_results = stage_results
            run.document_breakdown = doc_breakdown
            run.findings_summary = findings_summary
            run.completed_at = datetime.now(timezone.utc)

            # Record high-level audit activity event
            pipeline_activity = VendorActivity(
                vendor_id=vendor_id,
                event_type="ONBOARDING_PIPELINE_EXECUTED",
                title="Onboarding Pipeline Executed",
                description=(
                    f"Automated 8-stage onboarding executed. "
                    f"Processed {total_docs} document(s) ({successful_docs} successful, {failed_docs} failed). "
                    f"Final decision: {decision_result.status.value}."
                ),
                status=decision_result.status.value,
            )
            db.add(pipeline_activity)
            db.commit()
            db.refresh(run)

            logger.info(
                "Onboarding process completed for vendor %s: run_id=%s, status=%s, decision=%s",
                vendor_id,
                run.id,
                run.status,
                decision_result.status.value,
            )
            return self._to_run_response(run)

        except Exception as e:
            db.rollback()
            logger.error("Onboarding pipeline failed critically for vendor %s: %s", vendor_id, type(e).__name__, exc_info=True)
            # Record failed run with sanitized error message (zero internal path/credential leakage)
            failed_run = OnboardingProcessRun(
                vendor_id=vendor_id,
                status="FAILED",
                trigger_source=trigger_source,
                total_documents=total_docs,
                successful_documents=successful_docs,
                failed_documents=total_docs - successful_docs,
                documents_snapshot=docs_snapshot,
                stage_results=stage_results,
                document_breakdown=doc_breakdown,
                findings_summary={"error_type": type(e).__name__},
                error_message=f"Critical pipeline failure: {type(e).__name__}",
                completed_at=datetime.now(timezone.utc),
            )
            db.add(failed_run)
            db.commit()
            db.refresh(failed_run)
            return self._to_run_response(failed_run)

    def get_latest_run(self, db: Session, vendor_id: str) -> Optional[OnboardingProcessRunResponse]:
        """Retrieves the most recent onboarding processing run for a vendor."""
        vendor = db.get(Vendor, str(vendor_id))
        if not vendor:
            raise VendorNotFoundError(f"Vendor with ID '{vendor_id}' not found.")

        run = db.scalar(
            select(OnboardingProcessRun)
            .where(OnboardingProcessRun.vendor_id == vendor_id)
            .order_by(desc(OnboardingProcessRun.created_at))
            .limit(1)
        )
        if not run:
            return None
        return self._to_run_response(run)

    def get_history(self, db: Session, vendor_id: str) -> OnboardingProcessHistoryResponse:
        """Retrieves the full append-only execution history of onboarding runs for a vendor."""
        vendor = db.get(Vendor, str(vendor_id))
        if not vendor:
            raise VendorNotFoundError(f"Vendor with ID '{vendor_id}' not found.")

        runs = db.scalars(
            select(OnboardingProcessRun)
            .where(OnboardingProcessRun.vendor_id == vendor_id)
            .order_by(desc(OnboardingProcessRun.created_at))
        ).all()

        return OnboardingProcessHistoryResponse(
            vendor_id=vendor_id,
            total_runs=len(runs),
            runs=[self._to_run_response(r) for r in runs],
        )


onboarding_orchestrator = OnboardingOrchestratorService()
