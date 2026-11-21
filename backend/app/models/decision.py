"""Vendor decision data model for audit history and explainability."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, JSON, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.db.base import Base


class VendorDecision(Base):
    """Stores deterministic onboarding decisions, reason codes, and validation snapshots."""

    __tablename__ = "vendor_decisions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )

    vendor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("vendors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )  # APPROVED, PENDING, REJECTED

    decision_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="1.0.0",
    )

    ruleset_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="1.0.0",
    )

    validation_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )

    # Serialized evidence snapshot (sanitized findings, strictly zero raw banking data)
    validation_snapshot: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )

    # Stable reason codes list: ["ACCOUNT_HOLDER_NAME_MISMATCH", ...]
    reason_codes: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
    )

    # Detailed structured explanation: reasons, recommendations
    decision_explanation: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )

    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    vendor = relationship("Vendor", back_populates="decisions")

    __table_args__ = (
        Index("ix_decisions_vendor_time", "vendor_id", "decided_at"),
    )

    def __repr__(self) -> str:
        return f"<VendorDecision id={self.id} vendor_id={self.vendor_id} status={self.status!r} version={self.decision_version}>"
