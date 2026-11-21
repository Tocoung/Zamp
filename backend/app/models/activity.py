"""Vendor activity model for lightweight lifecycle execution history."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.db.base import Base


class VendorActivity(Base):
    """Tracks discrete lifecycle events for a vendor record."""

    __tablename__ = "vendor_activities"

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

    # Event classification: VENDOR_SUBMITTED, VENDOR_UPDATED, DECISION_EXECUTED, DECISION_REEVALUATED
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    # Human-readable title: "Vendor Registration Submitted", "Decision Executed", etc.
    title: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Safe summary description (Strictly NO bank accounts, encryption tokens, or passwords)
    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Status transition or current snapshot: SUBMITTED, APPROVED, PENDING, REJECTED
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    # Relationships
    vendor = relationship("Vendor", back_populates="activities")

    __table_args__ = (
        Index("ix_activities_vendor_time", "vendor_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<VendorActivity id={self.id} vendor_id={self.vendor_id} event_type={self.event_type!r} status={self.status!r}>"
