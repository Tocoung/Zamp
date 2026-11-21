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
from app.services.vendor_service import vendor_service, VendorServiceError
from app.core.security import EncryptionError

router = APIRouter()


@router.post(
    "",
    response_model=VendorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register Vendor",
    description="Validates and registers a new vendor. Encrypts banking data at rest and assigns initial SUBMITTED status.",
)
def create_vendor(
    vendor_in: VendorCreate,
    db: Session = Depends(get_db),
) -> VendorResponse:
    """Create and persist a new vendor record."""
    try:
        vendor = vendor_service.create_vendor(db=db, vendor_in=vendor_in)
        return VendorResponse.from_orm_model(vendor)
    except EncryptionError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Security error: Vendor data encryption failed. Submission aborted safely.",
        )
    except VendorServiceError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Persistence error: Failed to save vendor record. Database transaction has been rolled back.",
        )


@router.get(
    "",
    response_model=VendorPagination,
    status_code=status.HTTP_200_OK,
    summary="List Vendors (Paginated)",
    description="Returns a paginated list of vendor summaries with deterministic ordering. Excludes all banking data.",
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
    try:
        return VendorResponse.from_orm_model(vendor)
    except EncryptionError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Security error: Failed to safely decrypt vendor sensitive banking data.",
        )
