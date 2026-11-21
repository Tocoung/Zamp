"""Safe, idempotent migration and backfill of vendor lifecycle activities."""

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.vendor import Vendor
from app.models.decision import VendorDecision
from app.models.activity import VendorActivity
from app.core.logging import logger


def backfill_legacy_vendor_activities(session: Session) -> int:
    """Idempotently populates lifecycle activities for historical vendors that lack them.
    
    Safe & non-destructive:
    - Never mutates vendor or decision records.
    - Only generates activities for vendors with zero existing activity rows.
    - Preserves original timestamps from vendor.created_at and decision.decided_at.
    """
    vendors = list(session.scalars(select(Vendor)).all())
    backfilled_count = 0

    for vendor in vendors:
        existing_activities = session.scalar(
            select(func.count(VendorActivity.id)).where(VendorActivity.vendor_id == vendor.id)
        ) or 0

        if existing_activities == 0:
            # 1. Initial submission event
            sub_act = VendorActivity(
                vendor_id=vendor.id,
                event_type="VENDOR_SUBMITTED",
                title="Vendor Registration Submitted",
                description="Initial vendor registration submitted with status SUBMITTED.",
                status="SUBMITTED",
                created_at=vendor.created_at,
            )
            session.add(sub_act)

            # 2. Replay historical decisions in chronological order
            decisions = list(
                session.scalars(
                    select(VendorDecision)
                    .where(VendorDecision.vendor_id == vendor.id)
                    .order_by(VendorDecision.decided_at.asc(), VendorDecision.id.asc())
                ).all()
            )

            for idx, dec in enumerate(decisions):
                if idx == 0:
                    dec_act = VendorActivity(
                        vendor_id=vendor.id,
                        event_type="DECISION_EXECUTED",
                        title="Deterministic Decision Executed",
                        description=f"Initial automated evaluation: status assigned is {dec.status}.",
                        status=dec.status,
                        created_at=dec.decided_at,
                    )
                else:
                    dec_act = VendorActivity(
                        vendor_id=vendor.id,
                        event_type="DECISION_REEVALUATED",
                        title="Decision Re-evaluated",
                        description=f"Automated re-evaluation complete: status assigned is {dec.status} (iteration #{idx + 1}).",
                        status=dec.status,
                        created_at=dec.decided_at,
                    )
                session.add(dec_act)

            backfilled_count += 1

    if backfilled_count > 0:
        session.commit()
        logger.info(f"Backfilled lifecycle activity history for {backfilled_count} historical vendor(s).")
    return backfilled_count
