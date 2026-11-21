"""Vendor document model for persistent supporting document tracking."""

import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.db.base import Base


class VendorDocument(Base):
    """Stores metadata for uploaded vendor supporting documents."""

    __tablename__ = "vendor_documents"

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

    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    sanitized_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    document_category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="OTHER",
        index=True,
    )
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    upload_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="UPLOADED",
        index=True,
    )
    document_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    vendor = relationship("Vendor", back_populates="documents")

    __table_args__ = (
        Index("ix_documents_vendor_category", "vendor_id", "document_category"),
        Index("ix_documents_vendor_created", "vendor_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<VendorDocument id={self.id} vendor_id={self.vendor_id} "
            f"category={self.document_category!r} filename={self.sanitized_filename!r} "
            f"status={self.upload_status!r}>"
        )
