"""Vendor data model for persistent record management."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.db.base import Base


class Vendor(Base):
    """Vendor entity storing company, contact, address, tax, and banking details."""

    __tablename__ = "vendors"

    # Primary key: UUID string
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )

    # A. Identity and company information
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    trade_name: Mapped[str] = mapped_column(String(255), nullable=True)
    business_type: Mapped[str] = mapped_column(String(50), nullable=False)
    country_of_incorporation: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    registration_number: Mapped[str] = mapped_column(String(100), nullable=False)

    # B. Contact information
    contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    contact_phone: Mapped[str] = mapped_column(String(50), nullable=False)

    # C. Registered address
    address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line2: Mapped[str] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state_province: Mapped[str] = mapped_column(String(100), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    address_country: Mapped[str] = mapped_column(String(100), nullable=False)

    # D. Tax information
    tax_id_type: Mapped[str] = mapped_column(String(50), nullable=False)
    tax_id_number: Mapped[str] = mapped_column(String(100), nullable=False)

    # E. Banking information
    bank_account_holder_name: Mapped[str] = mapped_column(String(255), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(255), nullable=False)
    bank_account_number: Mapped[str] = mapped_column(String(255), nullable=False)
    bank_routing_number: Mapped[str] = mapped_column(String(50), nullable=False)
    bank_country: Mapped[str] = mapped_column(String(100), nullable=False)

    # F. System metadata & onboarding status
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="SUBMITTED",
        index=True,
    )
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

    # Decisions history relationship
    decisions = relationship(
        "VendorDecision",
        back_populates="vendor",
        cascade="all, delete-orphan",
        order_by="desc(VendorDecision.decided_at)",
    )

    # Lifecycle activity history relationship
    activities = relationship(
        "VendorActivity",
        back_populates="vendor",
        cascade="all, delete-orphan",
        order_by="asc(VendorActivity.created_at)",
    )

    __table_args__ = (
        Index("ix_vendors_country_reg", "country_of_incorporation", "registration_number"),
        Index("ix_vendors_tax_jurisdiction", "country_of_incorporation", "tax_id_type", "tax_id_number"),
    )

    def __repr__(self) -> str:
        return f"<Vendor id={self.id} legal_name={self.legal_name!r} status={self.status!r}>"
