"""Database model for document OCR and structured information extraction results."""

import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.db.base import Base


class DocumentExtraction(Base):
    """Stores structured OCR and information extraction results with field-level provenance."""

    __tablename__ = "document_extractions"

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

    document_category_used: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="COMPLETED",
        index=True,
    )

    # Structured fields JSON: dictionary of field_name -> ExtractedField object dict
    fields: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    extracted_fields_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    extraction_engine_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="1.0.0",
    )

    limitation_code: Mapped[str] = mapped_column(
        String(50),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    document = relationship("VendorDocument", back_populates="extractions")
    vendor = relationship("Vendor")

    __table_args__ = (
        Index("ix_extractions_doc_created", "document_id", "created_at"),
        Index("ix_extractions_vendor_created", "vendor_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentExtraction id={self.id} document_id={self.document_id} "
            f"category={self.document_category_used!r} status={self.status!r} "
            f"fields_count={self.extracted_fields_count}>"
        )
