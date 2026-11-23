"""Database model for end-to-end onboarding orchestration runs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from sqlalchemy import String, Integer, DateTime, ForeignKey, Index, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.db.base import Base


class OnboardingProcessRun(Base):
    """Represents a discrete execution of the end-to-end vendor onboarding workflow."""

    __tablename__ = "onboarding_process_runs"

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
        default="IN_PROGRESS",  # IN_PROGRESS, COMPLETED, PARTIAL_FAILURE, FAILED
        index=True,
    )

    trigger_source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="MANUAL",  # MANUAL, RETRY, REPROCESS, API
    )

    total_documents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    successful_documents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    failed_documents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Reference to downstream verification run
    verification_run_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("vendor_verifications.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Reference to downstream Phase 1 decision
    decision_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("vendor_decisions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Structured execution results for each of the 8 workflow stages
    stage_results: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    # Per-document status, classification, extraction, confidence, and errors
    document_breakdown: Mapped[List[Any]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    # Snapshot of document IDs, categories, and content hashes at execution time
    documents_snapshot: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    # Consolidated findings count and summary (privacy-safe)
    findings_summary: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    # Optional error message or failure reason for the overall pipeline
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    vendor = relationship("Vendor", backref="onboarding_runs")
    verification_run = relationship("VerificationRun")
    decision = relationship("VendorDecision")

    __table_args__ = (
        Index("idx_onboarding_vendor_created", "vendor_id", "created_at"),
        Index("idx_onboarding_status", "status"),
    )
