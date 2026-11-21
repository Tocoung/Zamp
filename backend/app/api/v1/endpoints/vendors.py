"""Vendor management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.vendor import (
    VendorCreate,
    VendorResponse,
    VendorPagination,
    VendorSummary,
)
from app.services.vendor_service import vendor_service

router = APIRouter()


@router.post(
    "",
    response_model=VendorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register Vendor",
    description="Validates and registers a new vendor. Generates UUID and initial SUBMITTED status.",
)
def create_vendor(
    vendor_in: VendorCreate,
    db: Session = Depends(get_db),
) -> VendorResponse:
    """Create and persist a new vendor record."""
    vendor = vendor_service.create_vendor(db=db, vendor_in=vendor_in)
    return VendorResponse.from_orm_model(vendor)


@router.get(
    "",
    response_model=VendorPagination,
    status_code=status.HTTP_200_OK,
    summary="List Vendors (Paginated)",
    description="Returns a paginated list of vendor summaries without sensitive banking numbers.",
)
def list_vendors(
    page: int = Query(1, ge=1, description="Page number starting at 1"),
    page_size: int = Query(10, ge=1, le=100, description="Number of records per page"),
    db: Session = Depends(get_db),
) -> VendorPagination:
    """Retrieve paginated vendor list."""
    vendors, total_count, total_pages = vendor_service.get_vendors_paginated(
        db=db, page=page, page_size=page_size
    )
    items = [VendorSummary.model_validate(v) for v in vendors]
    return VendorPagination(
        items=items,
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{vendor_id}",
    response_model=VendorResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Vendor Details",
    description="Retrieves complete vendor details with masked bank account number.",
)
def get_vendor(
    vendor_id: str,
    db: Session = Depends(get_db),
) -> VendorResponse:
    """Retrieve full details of a specific vendor."""
    vendor = vendor_service.get_vendor_by_id(db=db, vendor_id=vendor_id)
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor with ID '{vendor_id}' not found",
        )
    return VendorResponse.from_orm_model(vendor)
