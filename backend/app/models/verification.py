"""Database models for cross-document verification runs and discrepancy findings."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.db.base import Base


class VerificationRun(Base):
    """Represents a discrete execution of cross-document validation for a vendor."""

    __tablename__ = "vendor_verifications"

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
        default="NOT_RUN",
        index=True,
    )

    ruleset_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="1.0.0",
    )

    total_comparisons: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    matches: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    confirmed_discrepancies: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    potential_discrepancies: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    insufficient_evidence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    missing_documents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    unsupported_documents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    summary_notes: Mapped[str] = mapped_column(
        String(1000),
        nullable=True,
    )

    meta: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    vendor = relationship("Vendor", back_populates="verifications")
    findings = relationship(
        "VerificationFinding",
        back_populates="verification_run",
        cascade="all, delete-orphan",
        order_by="VerificationFinding.created_at",
    )

    __table_args__ = (
        Index("ix_verifications_vendor_created", "vendor_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<VerificationRun id={self.id} vendor_id={self.vendor_id} "
            f"status={self.status!r} comparisons={self.total_comparisons} "
            f"discrepancies={self.confirmed_discrepancies}>"
        )


class VerificationFinding(Base):
    """Represents an individual cross-source comparison result within a verification run."""

    __tablename__ = "verification_findings"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )

    verification_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("vendor_verifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    field_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    comparison_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    result: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="INFO",
    )

    explanation: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )

    similarity_score: Mapped[float] = mapped_column(
        Float,
        nullable=True,
    )

    comparison_summary: Mapped[str] = mapped_column(
        String(500),
        nullable=True,
    )

    # Serialized evidence sources list
    evidence_sources: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    verification_run = relationship("VerificationRun", back_populates="findings")

    __table_args__ = (
        Index("ix_findings_run_result", "verification_run_id", "result"),
    )

    def __repr__(self) -> str:
        return (
            f"<VerificationFinding id={self.id} field={self.field_name!r} "
            f"result={self.result!r} severity={self.severity!r}>"
        )
