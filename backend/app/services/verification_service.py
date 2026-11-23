"""Service layer coordinating cross-document verification execution, persistence, and decision integration."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from app.models.vendor import Vendor
from app.models.document import VendorDocument
from app.models.extraction import DocumentExtraction
from app.models.verification import VerificationRun, VerificationFinding
from app.models.activity import VendorActivity
from app.schemas.verification import (
    EvidenceSource,
    FindingResult,
    FindingSeverity,
    VerificationFindingResponse,
    VerificationHistoryResponse,
    VerificationRunResponse,
    VerificationRunStatus,
    VerificationRunSummary,
)
from app.verification.engine import verification_engine
from app.core.security import decrypt_account_number, EncryptionError
from app.core.logging import logger


class VerificationServiceError(Exception):
    """Raised when cross-document verification evaluation or persistence fails."""
    pass


class VendorNotFoundError(VerificationServiceError):
    """Raised when the target vendor does not exist."""
    pass


class VerificationService:
    """Service orchestrating cross-document verification runs, database transactions, and history."""

    @staticmethod
    def _to_run_response(run: VerificationRun) -> VerificationRunResponse:
        """Converts a VerificationRun model into a VerificationRunResponse schema."""
        findings_responses: List[VerificationFindingResponse] = []
        for f in (run.findings or []):
            sources = []
            if f.evidence_sources:
                for s in f.evidence_sources:
                    if isinstance(s, dict):
                        sources.append(EvidenceSource.model_validate(s))
                    elif isinstance(s, EvidenceSource):
                        sources.append(s)

            findings_responses.append(
                VerificationFindingResponse(
                    id=f.id,
                    verification_run_id=f.verification_run_id,
                    field_name=f.field_name,
                    comparison_type=f.comparison_type,
                    result=FindingResult(f.result),
                    severity=FindingSeverity(f.severity),
                    explanation=f.explanation,
                    similarity_score=f.similarity_score,
                    comparison_summary=f.comparison_summary,
                    evidence_sources=sources,
                    created_at=f.created_at,
                )
            )

        return VerificationRunResponse(
            id=run.id,
            vendor_id=run.vendor_id,
            status=VerificationRunStatus(run.status),
            ruleset_version=run.ruleset_version,
            total_comparisons=run.total_comparisons,
            matches=run.matches,
            confirmed_discrepancies=run.confirmed_discrepancies,
            potential_discrepancies=run.potential_discrepancies,
            insufficient_evidence=run.insufficient_evidence,
            missing_documents=run.missing_documents,
            unsupported_documents=run.unsupported_documents,
            summary_notes=run.summary_notes,
            meta=run.meta or {},
            created_at=run.created_at,
            findings=findings_responses,
        )

    @staticmethod
    def _to_summary(run: VerificationRun) -> VerificationRunSummary:
        """Converts a VerificationRun model into a lightweight VerificationRunSummary schema."""
        return VerificationRunSummary(
            id=run.id,
            vendor_id=run.vendor_id,
            status=VerificationRunStatus(run.status),
            ruleset_version=run.ruleset_version,
            total_comparisons=run.total_comparisons,
            matches=run.matches,
            confirmed_discrepancies=run.confirmed_discrepancies,
            potential_discrepancies=run.potential_discrepancies,
            insufficient_evidence=run.insufficient_evidence,
            missing_documents=run.missing_documents,
            unsupported_documents=run.unsupported_documents,
            summary_notes=run.summary_notes,
            meta=run.meta or {},
            created_at=run.created_at,
        )

    @classmethod
    def run_verification_for_vendor(
        cls,
        db: Session,
        vendor_id: str,
    ) -> VerificationRunResponse:
        """Executes cross-document verification, records findings and activity, and commits atomically.
        
        Guarantees:
        - Atomicity: The new VerificationRun and VerificationFinding records, VendorActivity,
          and any vendor status adjustment are committed together in a single transaction.
        - Privacy: Bank account numbers are decrypted strictly in memory and are masked
          (••••••••1234) before persistence into findings, summaries, and activity logs.
        - Safety: Low-confidence OCR, missing documents, or unreadable evidence NEVER auto-rejects
          the vendor. If confirmed or potential discrepancies are found for an APPROVED vendor,
          the vendor is routed to PENDING for human review.
        """
        vendor = db.scalar(select(Vendor).where(Vendor.id == vendor_id))
        if not vendor:
            raise VendorNotFoundError(f"Vendor with ID '{vendor_id}' not found.")

        # 1. Build in-memory vendor profile dictionary
        vendor_dict: Dict[str, Any] = {
            "legal_name": vendor.legal_name,
            "trade_name": vendor.trade_name,
            "business_type": vendor.business_type,
            "country_of_incorporation": vendor.country_of_incorporation,
            "registration_number": vendor.registration_number,
            "contact_name": vendor.contact_name,
            "contact_email": vendor.contact_email,
            "contact_phone": vendor.contact_phone,
            "address_line1": vendor.address_line1,
            "address_line2": vendor.address_line2,
            "city": vendor.city,
            "state_province": vendor.state_province,
            "postal_code": vendor.postal_code,
            "address_country": vendor.address_country,
            "tax_id_type": vendor.tax_id_type,
            "tax_id_number": vendor.tax_id_number,
            "bank_account_holder_name": vendor.bank_account_holder_name,
            "bank_name": vendor.bank_name,
            "bank_routing_number": vendor.bank_routing_number,
            "bank_country": vendor.bank_country,
        }

        # 2. Decrypt bank account strictly in memory
        if vendor.bank_account_number and str(vendor.bank_account_number).strip():
            try:
                vendor_dict["bank_account_number"] = decrypt_account_number(
                    vendor.bank_account_number,
                    allow_legacy_plaintext=True,
                )
            except EncryptionError as e:
                logger.error(
                    "Security/cryptography error decrypting bank account during verification: vendor_id=%s",
                    vendor.id,
                )
                raise VerificationServiceError(
                    "Security error: Sensitive banking data could not be safely decrypted for verification."
                ) from e
            except Exception as e:
                logger.error(
                    "Technical error decrypting bank account during verification: vendor_id=%s, err=%s",
                    vendor.id,
                    type(e).__name__,
                )
                raise VerificationServiceError(
                    "Data integrity error: Failed to decrypt banking information for verification."
                ) from e
        else:
            vendor_dict["bank_account_number"] = None

        # 3. Retrieve all active documents and their extractions
        documents = list(
            db.scalars(
                select(VendorDocument)
                .where(VendorDocument.vendor_id == vendor.id)
                .order_by(VendorDocument.created_at.asc())
            ).all()
        )

        extractions = list(
            db.scalars(
                select(DocumentExtraction)
                .where(DocumentExtraction.vendor_id == vendor.id)
                .order_by(DocumentExtraction.created_at.asc())
            ).all()
        )

        # 4. Run verification engine
        summary, evaluated_findings = verification_engine.evaluate(
            vendor=vendor,
            vendor_dict=vendor_dict,
            documents=documents,
            extractions=extractions,
        )

        # 5. Build database records
        run_record = VerificationRun(
            id=summary.id,
            vendor_id=vendor.id,
            status=summary.status.value,
            ruleset_version=summary.ruleset_version,
            total_comparisons=summary.total_comparisons,
            matches=summary.matches,
            confirmed_discrepancies=summary.confirmed_discrepancies,
            potential_discrepancies=summary.potential_discrepancies,
            insufficient_evidence=summary.insufficient_evidence,
            missing_documents=summary.missing_documents,
            unsupported_documents=summary.unsupported_documents,
            summary_notes=summary.summary_notes,
            meta=summary.meta,
            created_at=summary.created_at,
        )

        finding_records: List[VerificationFinding] = []
        for ef in evaluated_findings:
            serialized_sources = [s.model_dump() for s in ef.evidence_sources]
            finding_records.append(
                VerificationFinding(
                    id=str(uuid.uuid4()),
                    verification_run_id=run_record.id,
                    field_name=ef.field_name,
                    comparison_type=ef.comparison_type.value,
                    result=ef.result.value,
                    severity=ef.severity.value,
                    explanation=ef.explanation,
                    similarity_score=ef.similarity_score,
                    comparison_summary=ef.comparison_summary,
                    evidence_sources=serialized_sources,
                    created_at=summary.created_at,
                )
            )

        # 6. Check decision status interaction (Section 8)
        # If an APPROVED vendor now has confirmed discrepancies, potential discrepancies,
        # or missing documents, transition to PENDING (never REJECTED).
        status_updated = False
        old_status = vendor.status
        if vendor.status == "APPROVED" and (
            summary.confirmed_discrepancies > 0
            or summary.potential_discrepancies > 0
            or summary.missing_documents > 0
        ):
            vendor.status = "PENDING"
            status_updated = True

        # 7. Record lifecycle activity event (length <= 255)
        desc_text = (
            f"Verification: {summary.matches} matches, "
            f"{summary.confirmed_discrepancies} confirmed disc, "
            f"{summary.potential_discrepancies} potential disc, "
            f"{summary.missing_documents} missing docs."
        )[:255]

        activity = VendorActivity(
            vendor_id=vendor.id,
            event_type="VERIFICATION_EXECUTED",
            title="Cross-Document Verification Executed",
            description=desc_text,
            status=vendor.status,
        )

        # 8. Commit atomically
        try:
            db.add(run_record)
            for fr in finding_records:
                db.add(fr)
            db.add(activity)
            if status_updated:
                db.add(vendor)
            db.commit()
            db.refresh(run_record)
        except Exception as e:
            db.rollback()
            logger.error("Failed to persist verification transaction: %s", type(e).__name__)
            raise VerificationServiceError(
                "Database error: Failed to persist verification results and update audit trail."
            ) from e

        logger.info(
            "Verification committed: vendor_id=%s, run_id=%s, status=%s, matches=%d, discrepancies=%d",
            vendor.id,
            run_record.id,
            run_record.status,
            run_record.matches,
            run_record.confirmed_discrepancies,
        )

        # Return full response
        # Set findings explicitly on run_record so helper can serialize
        run_record.findings = finding_records
        return cls._to_run_response(run_record)

    @classmethod
    def get_latest_verification(
        cls,
        db: Session,
        vendor_id: str,
    ) -> Optional[VerificationRunResponse]:
        """Retrieves the most recent verification run and its detailed findings for a vendor."""
        vendor = db.scalar(select(Vendor).where(Vendor.id == vendor_id))
        if not vendor:
            raise VendorNotFoundError(f"Vendor with ID '{vendor_id}' not found.")

        latest_run = db.scalar(
            select(VerificationRun)
            .where(VerificationRun.vendor_id == vendor.id)
            .order_by(VerificationRun.created_at.desc())
            .limit(1)
        )
        if not latest_run:
            return None

        # Fetch findings
        findings = list(
            db.scalars(
                select(VerificationFinding)
                .where(VerificationFinding.verification_run_id == latest_run.id)
                .order_by(VerificationFinding.created_at.asc())
            ).all()
        )
        latest_run.findings = findings
        return cls._to_run_response(latest_run)

    @classmethod
    def get_verification_history(
        cls,
        db: Session,
        vendor_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> VerificationHistoryResponse:
        """Retrieves paginated verification execution history for a vendor."""
        vendor = db.scalar(select(Vendor).where(Vendor.id == vendor_id))
        if not vendor:
            raise VendorNotFoundError(f"Vendor with ID '{vendor_id}' not found.")

        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        offset = (page - 1) * page_size

        total = db.scalar(
            select(func.count(VerificationRun.id))
            .where(VerificationRun.vendor_id == vendor.id)
        ) or 0

        runs = list(
            db.scalars(
                select(VerificationRun)
                .where(VerificationRun.vendor_id == vendor.id)
                .order_by(VerificationRun.created_at.desc())
                .offset(offset)
                .limit(page_size)
            ).all()
        )

        items = [cls._to_summary(r) for r in runs]
        return VerificationHistoryResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=items,
        )

    @classmethod
    def get_verification_run(
        cls,
        db: Session,
        vendor_id: str,
        run_id: str,
    ) -> Optional[VerificationRunResponse]:
        """Retrieves a specific verification run by ID for a vendor."""
        vendor = db.scalar(select(Vendor).where(Vendor.id == vendor_id))
        if not vendor:
            raise VendorNotFoundError(f"Vendor with ID '{vendor_id}' not found.")

        run = db.scalar(
            select(VerificationRun)
            .where(
                VerificationRun.id == run_id,
                VerificationRun.vendor_id == vendor.id,
            )
        )
        if not run:
            return None

        findings = list(
            db.scalars(
                select(VerificationFinding)
                .where(VerificationFinding.verification_run_id == run.id)
                .order_by(VerificationFinding.created_at.asc())
            ).all()
        )
        run.findings = findings
        return cls._to_run_response(run)
