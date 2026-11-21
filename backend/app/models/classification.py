"""Database model for document classification results and explainable evidence."""

import uuid
from datetime import datetime
from sqlalchemy import String, Float, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.db.base import Base


class DocumentClassification(Base):
    """Stores deterministic classification results, confidence scores, and explainable signals."""

    __tablename__ = "document_classifications"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )

    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("vendor_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    vendor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("vendors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    predicted_category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="UNKNOWN",
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="CLASSIFIED",
        index=True,
    )

    confidence_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    # Safe explainability signals (matched keywords, headings, score breakdown; NO raw text or sensitive data)
    evidence: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    limitation_code: Mapped[str] = mapped_column(
        String(50),
        nullable=True,
    )

    classifier_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="1.0.0",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    document = relationship("VendorDocument", back_populates="classifications")
    vendor = relationship("Vendor")

    @property
    def declared_category(self) -> str:
        """Returns the user-declared document category from the associated document."""
        if self.document and hasattr(self.document, "document_category"):
            return self.document.document_category
        return "UNKNOWN"

    __table_args__ = (
        Index("ix_classifications_doc_created", "document_id", "created_at"),
        Index("ix_classifications_vendor_created", "vendor_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentClassification id={self.id} document_id={self.document_id} "
            f"predicted={self.predicted_category!r} status={self.status!r} "
            f"confidence={self.confidence_score:.2f}>"
        )
