"""Service layer managing deterministic vendor onboarding decisions and audit history."""

import math
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.vendor import Vendor
from app.models.decision import VendorDecision
from app.decision.models import (
    DecisionHistoryItem,
    DecisionReason,
    DecisionRecommendation,
    DecisionResult,
    DecisionStatus,
)
from app.decision.registry import decision_engine
from app.validation import validation_engine
from app.core.security import decrypt_account_number
from app.core.logging import logger


class DecisionServiceError(Exception):
    """Raised when decision processing or persistence fails."""
    pass


class VendorNotFoundError(DecisionServiceError):
    """Raised when the target vendor does not exist."""
    pass


class DecisionService:
    """Service orchestrating vendor decision evaluations and audit history persistence."""

    @staticmethod
    def run_decision_for_vendor(
        db: Session,
        vendor_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> DecisionResult:
        """Executes validation once, calculates deterministic decision, and persists history.
        
        Transactional Guarantee:
        The new VendorDecision record and the Vendor.status update occur in the
        same database transaction. If persistence fails, both are rolled back.
        
        Args:
            db: Active database session.
            vendor_id: Target vendor UUID.
            context: Optional contextual parameters.
            
        Returns:
            Structured DecisionResult.
            
        Raises:
            VendorNotFoundError: If vendor is not found.
            DecisionServiceError: If database persistence fails.
        """
        vendor = db.scalar(select(Vendor).where(Vendor.id == vendor_id))
        if not vendor:
            raise VendorNotFoundError(f"Vendor with ID '{vendor_id}' not found")

        # 1. Reconstruct vendor dictionary for validation
        vendor_dict = {
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

        # Decrypt bank account strictly in memory for structural validation
        try:
            plain_account = decrypt_account_number(
                vendor.bank_account_number,
                allow_legacy_plaintext=True,
            )
            vendor_dict["bank_account_number"] = plain_account
        except Exception as e:
            logger.error("Failed to decrypt account number for decision evaluation: %s", type(e).__name__)
            vendor_dict["bank_account_number"] = None

        # 2. Run validation engine EXACTLY ONCE
        validation_result = validation_engine.validate_vendor(
            vendor_data=vendor_dict,
            vendor_id=vendor.id,
            context={"is_stored_record": True, "stored_status": vendor.status},
        )

        # 3. Evaluate deterministic decision
        decision_result = decision_engine.evaluate(
            validation_result=validation_result,
            vendor_id=vendor.id,
            vendor_data=vendor_dict,
        )

        # 4. Construct persistent decision record
        explanation_payload = {
            "reasons": [r.model_dump() for r in decision_result.reasons],
            "recommendations": [rec.model_dump() for rec in decision_result.recommendations],
        }

        decision_record = VendorDecision(
            id=decision_result.decision_id,
            vendor_id=vendor.id,
            status=decision_result.status.value,
            decision_version=decision_result.decision_version,
            ruleset_version=decision_result.ruleset_version,
            validation_id=decision_result.validation_id,
            validation_snapshot=decision_result.validation_snapshot,
            reason_codes=decision_result.reason_codes,
            decision_explanation=explanation_payload,
            decided_at=decision_result.decided_at,
        )

        # 5. Transactional commit: persist decision record and update vendor status
        try:
            db.add(decision_record)
            vendor.status = decision_result.status.value
            db.commit()
            db.refresh(decision_record)
            db.refresh(vendor)
        except Exception as e:
            db.rollback()
            logger.error("Failed to persist vendor decision transaction: %s", type(e).__name__)
            raise DecisionServiceError(
                "Failed to persist decision and update vendor status. Database transaction has been rolled back."
            ) from e

        logger.info(
            "Vendor decision committed: vendor_id=%s, decision_id=%s, status=%s",
            vendor.id,
            decision_record.id,
            decision_record.status,
        )
        return decision_result

    @staticmethod
    def get_latest_decision(db: Session, vendor_id: str) -> Optional[DecisionResult]:
        """Retrieves the most recent decision record for a vendor."""
        vendor = db.scalar(select(Vendor).where(Vendor.id == vendor_id))
        if not vendor:
            raise VendorNotFoundError(f"Vendor with ID '{vendor_id}' not found")

        stmt = (
            select(VendorDecision)
            .where(VendorDecision.vendor_id == vendor_id)
            .order_by(VendorDecision.decided_at.desc(), VendorDecision.id.asc())
            .limit(1)
        )
        record = db.scalar(stmt)
        if not record:
            return None

        # Reconstruct DecisionResult from stored entity
        reasons = [
            DecisionReason.model_validate(r)
            for r in record.decision_explanation.get("reasons", [])
        ]
        recommendations = [
            DecisionRecommendation.model_validate(rec)
            for rec in record.decision_explanation.get("recommendations", [])
        ]

        return DecisionResult(
            decision_id=record.id,
            vendor_id=record.vendor_id,
            status=DecisionStatus(record.status),
            decision_version=record.decision_version,
            ruleset_version=record.ruleset_version,
            validation_id=record.validation_id,
            validation_status=record.validation_snapshot.get("validation_status", "UNKNOWN"),
            reason_codes=record.reason_codes or [],
            reasons=reasons,
            recommendations=recommendations,
            validation_snapshot=record.validation_snapshot,
            decided_at=record.decided_at,
        )

    @staticmethod
    def get_decision_history(
        db: Session,
        vendor_id: str,
        page: int = 1,
        page_size: int = 10,
    ) -> Tuple[List[DecisionHistoryItem], int, int]:
        """Retrieves deterministically paginated decision history for a vendor."""
        vendor = db.scalar(select(Vendor).where(Vendor.id == vendor_id))
        if not vendor:
            raise VendorNotFoundError(f"Vendor with ID '{vendor_id}' not found")

        page = max(1, page)
        page_size = max(1, min(page_size, 100))

        count_stmt = select(func.count(VendorDecision.id)).where(
            VendorDecision.vendor_id == vendor_id
        )
        total_count = db.scalar(count_stmt) or 0
        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0

        offset = (page - 1) * page_size
        stmt = (
            select(VendorDecision)
            .where(VendorDecision.vendor_id == vendor_id)
            .order_by(VendorDecision.decided_at.desc(), VendorDecision.id.asc())
            .offset(offset)
            .limit(page_size)
        )
        records = db.scalars(stmt).all()

        items = []
        for rec in records:
            reasons = [
                DecisionReason.model_validate(r)
                for r in rec.decision_explanation.get("reasons", [])
            ]
            recommendations = [
                DecisionRecommendation.model_validate(r)
                for r in rec.decision_explanation.get("recommendations", [])
            ]
            items.append(
                DecisionHistoryItem(
                    id=rec.id,
                    vendor_id=rec.vendor_id,
                    status=DecisionStatus(rec.status),
                    decision_version=rec.decision_version,
                    ruleset_version=rec.ruleset_version,
                    validation_id=rec.validation_id,
                    reason_codes=rec.reason_codes or [],
                    reasons=reasons,
                    recommendations=recommendations,
                    decided_at=rec.decided_at,
                )
            )

        return items, total_count, total_pages


decision_service = DecisionService()
