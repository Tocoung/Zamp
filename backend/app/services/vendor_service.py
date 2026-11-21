"""Vendor service layer encapsulating database transactions and business operations."""

import math
import uuid
from typing import Optional, Tuple, List
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.vendor import Vendor
from app.schemas.vendor import VendorCreate
from app.core.logging import logger
from app.core.security import encrypt_account_number


class VendorServiceError(Exception):
    """Raised when vendor persistence or retrieval operations fail."""
    pass


class VendorService:
    """Service class managing vendor persistence and query operations."""

    @staticmethod
    def create_vendor(db: Session, vendor_in: VendorCreate) -> Vendor:
        """Persists a new vendor record with initial SUBMITTED status.
        
        Security: Bank account number is encrypted at rest using Fernet
        (AES-128-CBC + HMAC-SHA256) and is NEVER logged to application logs.
        Transaction is committed safely; rollback is guaranteed on any failure.
        """
        vendor_id = str(uuid.uuid4())
        
        # Authenticated encryption at rest
        encrypted_account = encrypt_account_number(vendor_in.bank_account_number)

        vendor = Vendor(
            id=vendor_id,
            legal_name=vendor_in.legal_name,
            trade_name=vendor_in.trade_name,
            business_type=vendor_in.business_type,
            country_of_incorporation=vendor_in.country_of_incorporation,
            registration_number=vendor_in.registration_number,
            contact_name=vendor_in.contact_name,
            contact_email=vendor_in.contact_email,
            contact_phone=vendor_in.contact_phone,
            address_line1=vendor_in.address_line1,
            address_line2=vendor_in.address_line2,
            city=vendor_in.city,
            state_province=vendor_in.state_province,
            postal_code=vendor_in.postal_code,
            address_country=vendor_in.address_country,
            tax_id_type=vendor_in.tax_id_type,
            tax_id_number=vendor_in.tax_id_number,
            bank_account_holder_name=vendor_in.bank_account_holder_name,
            bank_name=vendor_in.bank_name,
            bank_account_number=encrypted_account,
            bank_routing_number=vendor_in.bank_routing_number,
            bank_country=vendor_in.bank_country,
            status="SUBMITTED",
        )

        try:
            db.add(vendor)
            db.commit()
            db.refresh(vendor)
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to persist vendor record: {type(e).__name__}")
            raise VendorServiceError("Database persistence failed. Transaction has been rolled back.") from e

        logger.info(f"Vendor record created successfully: id={vendor.id}, legal_name={vendor.legal_name!r}")
        return vendor

    @staticmethod
    def get_vendor_by_id(db: Session, vendor_id: str) -> Optional[Vendor]:
        """Retrieves a single vendor by UUID."""
        stmt = select(Vendor).where(Vendor.id == vendor_id)
        return db.scalar(stmt)

    @staticmethod
    def get_vendors_paginated(
        db: Session,
        page: int = 1,
        page_size: int = 10,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[Vendor], int, int]:
        """Retrieves a paginated list of vendor records with optional filtering.
        
        Ordering: Uses stable composite sort (created_at DESC, id ASC) to guarantee
        strictly deterministic pagination across page boundaries.
        
        Returns:
            Tuple of (items, total_count, total_pages)
        """
        page = max(1, page)
        page_size = max(1, min(page_size, 100))

        # Base filter expressions
        filters = []
        if status and status.strip().upper() != "ALL":
            filters.append(Vendor.status == status.strip().upper())
        if search and search.strip():
            search_term = f"%{search.strip().lower()}%"
            filters.append(
                func.lower(Vendor.legal_name).like(search_term)
                | func.lower(Vendor.contact_email).like(search_term)
                | func.lower(Vendor.country_of_incorporation).like(search_term)
            )

        # Count total records matching filters
        total_stmt = select(func.count(Vendor.id))
        if filters:
            total_stmt = total_stmt.where(*filters)
        total_count = db.scalar(total_stmt) or 0

        # Query page slice with deterministic ordering
        offset = (page - 1) * page_size
        query_stmt = (
            select(Vendor)
            .order_by(Vendor.created_at.desc(), Vendor.id.asc())
            .offset(offset)
            .limit(page_size)
        )
        if filters:
            query_stmt = query_stmt.where(*filters)

        vendors = list(db.scalars(query_stmt).all())
        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1

        return vendors, total_count, total_pages


vendor_service = VendorService()
