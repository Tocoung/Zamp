"""Vendor service layer encapsulating database transactions and business operations."""

import math
import uuid
from typing import Optional, Tuple, List
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.vendor import Vendor
from app.schemas.vendor import VendorCreate
from app.core.logging import logger


class VendorService:
    """Service class managing vendor persistence and query operations."""

    @staticmethod
    def create_vendor(db: Session, vendor_in: VendorCreate) -> Vendor:
        """Persists a new vendor record with initial SUBMITTED status.
        
        Note on security: Bank account number is stored in the database but
        is NEVER printed to application logs or console streams.
        """
        vendor_id = str(uuid.uuid4())
        
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
            bank_account_number=vendor_in.bank_account_number,
            bank_routing_number=vendor_in.bank_routing_number,
            bank_country=vendor_in.bank_country,
            status="SUBMITTED",
        )

        db.add(vendor)
        db.commit()
        db.refresh(vendor)

        logger.info(f"Vendor record created successfully: id={vendor.id}, legal_name={vendor.legal_name!r}")
        return vendor

    @staticmethod
    def get_vendor_by_id(db: Session, vendor_id: str) -> Optional[Vendor]:
        """Retrieves a single vendor by UUID."""
        stmt = select(Vendor).where(Vendor.id == vendor_id)
        return db.scalar(stmt)

    @staticmethod
    def get_vendors_paginated(
        db: Session, page: int = 1, page_size: int = 10
    ) -> Tuple[List[Vendor], int, int]:
        """Retrieves a paginated list of vendor records sorted by creation date descending.
        
        Returns:
            Tuple of (items, total_count, total_pages)
        """
        page = max(1, page)
        page_size = max(1, min(page_size, 100))

        # Count total records
        total_stmt = select(func.count(Vendor.id))
        total_count = db.scalar(total_stmt) or 0

        # Query page slice
        offset = (page - 1) * page_size
        query_stmt = (
            select(Vendor)
            .order_by(Vendor.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        vendors = list(db.scalars(query_stmt).all())
        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1

        return vendors, total_count, total_pages


vendor_service = VendorService()
