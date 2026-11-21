"""Vendor management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.vendor import (
    VendorCreate,
    VendorUpdate,
    VendorResponse,
    VendorPagination,
    VendorSummary,
)
from app.schemas.activity import (
    VendorActivityItem,
    VendorActivityPagination,
)
from app.services.vendor_service import vendor_service, VendorServiceError
from app.core.security import EncryptionError, decrypt_account_number
from app.core.logging import logger
from app.validation import (
    ValidationResult,
    VendorValidationRequest,
    validation_engine,
)
from app.decision import (
    DecisionResult,
    DecisionHistoryPagination,
)
from app.services.decision_service import (
    decision_service,
    VendorNotFoundError,
    DecisionServiceError,
)

router = APIRouter()


@router.post(
    "/validate",
    response_model=ValidationResult,
    status_code=status.HTTP_200_OK,
    summary="Validate Vendor Submission",
    description="Deterministically validates a complete or partial vendor payload against required fields, format constraints, and consistency rules. Does not persist any records.",
)
def validate_vendor_payload(
    payload: VendorValidationRequest,
) -> ValidationResult:
    """Validate an unsaved vendor payload without persistence."""
    return validation_engine.validate_vendor(vendor_data=payload)


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
    status: str = Query(None, description="Filter by onboarding status (SUBMITTED, APPROVED, PENDING, REJECTED)"),
    search: str = Query(None, description="Search term matching company name, email, or country"),
    db: Session = Depends(get_db),
) -> VendorPagination:
    """Retrieve paginated vendor list with optional status and text filters."""
    vendors, total_count, total_pages = vendor_service.get_vendors_paginated(
        db=db, page=page, page_size=page_size, status=status, search=search
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


@router.post(
    "/{vendor_id}/validate",
    response_model=ValidationResult,
    status_code=status.HTTP_200_OK,
    summary="Validate Existing Vendor Record",
    description="Loads a stored vendor record, decrypts banking data internally solely for structural format checks, and runs the deterministic validation engine. Does not alter vendor status or write to the database.",
)
def validate_existing_vendor(
    vendor_id: str,
    db: Session = Depends(get_db),
) -> ValidationResult:
    """Validate an existing persisted vendor record."""
    vendor = vendor_service.get_vendor_by_id(db=db, vendor_id=vendor_id)
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor with ID '{vendor_id}' not found",
        )

    # Reconstruct data dictionary for engine execution
    vendor_dict = {
        "legal_name": vendor.legal_name,
        "trade_name": vendor.trade_name,
        "business_type": vendor.business_type,
        "country_of_incorporation": vendor.country_of_incorporation,
        "registration_number": vendor.registration_number,
        "contact_name": vendor.contact_name,
        "contact_email": vendor.contact_email,
        "contact_phone": vendor.contact_phone,
        "address_line1": vendor.address_line1,
        "address_line2": vendor.address_line2,
        "city": vendor.city,
        "state_province": vendor.state_province,
        "postal_code": vendor.postal_code,
        "address_country": vendor.address_country,
        "tax_id_type": vendor.tax_id_type,
        "tax_id_number": vendor.tax_id_number,
        "bank_account_holder_name": vendor.bank_account_holder_name,
        "bank_name": vendor.bank_name,
        "bank_routing_number": vendor.bank_routing_number,
        "bank_country": vendor.bank_country,
    }

    # Decrypt bank account number strictly in memory for structural checks
    if vendor.bank_account_number and str(vendor.bank_account_number).strip():
        try:
            decrypted_account = decrypt_account_number(
                vendor.bank_account_number,
                allow_legacy_plaintext=True,
            )
            vendor_dict["bank_account_number"] = decrypted_account
        except EncryptionError as e:
            logger.error(
                "Security/cryptography error decrypting bank account during validation: class=%s, vendor_id=%s",
                type(e).__name__,
                vendor.id,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Security or data integrity error: Sensitive banking data could not be safely decrypted for validation.",
            ) from e
        except Exception as e:
            logger.error(
                "Unexpected technical error decrypting bank account during validation: class=%s, vendor_id=%s",
                type(e).__name__,
                vendor.id,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Security or data integrity error: Sensitive banking data could not be safely decrypted for validation.",
            ) from e
    else:
        vendor_dict["bank_account_number"] = None

    return validation_engine.validate_vendor(
        vendor_data=vendor_dict,
        vendor_id=vendor.id,
        context={"is_stored_record": True, "stored_status": vendor.status},
    )


@router.put(
    "/{vendor_id}",
    response_model=VendorResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Vendor Details",
    description="Updates editable profile details for an existing vendor. Encrypts sensitive banking data if modified and logs a lifecycle update event.",
)
def update_vendor(
    vendor_id: str,
    vendor_in: VendorUpdate,
    db: Session = Depends(get_db),
) -> VendorResponse:
    """Update profile and registration details of an existing vendor."""
    try:
        updated = vendor_service.update_vendor(db=db, vendor_id=vendor_id, vendor_in=vendor_in)
        return VendorResponse.from_orm_model(updated)
    except VendorNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor with ID '{vendor_id}' not found",
        )
    except EncryptionError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Security error: Failed to safely encrypt updated banking data.",
        )
    except VendorServiceError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Persistence error: Failed to update vendor record. Transaction has been rolled back.",
        )


@router.get(
    "/{vendor_id}/activities",
    response_model=VendorActivityPagination,
    status_code=status.HTTP_200_OK,
    summary="List Vendor Lifecycle Activities",
    description="Returns a paginated list of lifecycle activity events for a vendor in deterministic chronological order.",
)
def list_vendor_activities(
    vendor_id: str,
    page: int = Query(1, ge=1, description="Page number starting at 1"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> VendorActivityPagination:
    """Retrieve chronologically ordered lifecycle events for a vendor."""
    vendor = vendor_service.get_vendor_by_id(db=db, vendor_id=vendor_id)
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor with ID '{vendor_id}' not found",
        )
    activities, total, total_pages = vendor_service.get_vendor_activities(
        db=db, vendor_id=vendor_id, page=page, page_size=page_size
    )
    items = [VendorActivityItem.model_validate(a) for a in activities]
    return VendorActivityPagination(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post(
    "/{vendor_id}/decide",
    response_model=DecisionResult,
    status_code=status.HTTP_200_OK,
    summary="Compute and Persist Vendor Decision",
    description="Runs validation once, evaluates deterministic decision rules, persists an audited decision snapshot, and updates vendor onboarding status transactionally.",
)
def compute_vendor_decision(
    vendor_id: str,
    db: Session = Depends(get_db),
) -> DecisionResult:
    """Evaluate and commit an explainable decision for a vendor."""
    try:
        return decision_service.run_decision_for_vendor(db=db, vendor_id=vendor_id)
    except VendorNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor with ID '{vendor_id}' not found",
        )
    except DecisionServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get(
    "/{vendor_id}/decision",
    response_model=DecisionResult,
    status_code=status.HTTP_200_OK,
    summary="Get Latest Vendor Decision",
    description="Retrieves the most recent decision result, reason codes, explanations, and recommendations for a vendor.",
)
def get_latest_vendor_decision(
    vendor_id: str,
    db: Session = Depends(get_db),
) -> DecisionResult:
    """Retrieve the latest decision result for a vendor."""
    try:
        decision = decision_service.get_latest_decision(db=db, vendor_id=vendor_id)
        if not decision:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No decision has been recorded for vendor '{vendor_id}'",
            )
        return decision
    except VendorNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor with ID '{vendor_id}' not found",
        )


@router.get(
    "/{vendor_id}/decision-history",
    response_model=DecisionHistoryPagination,
    status_code=status.HTTP_200_OK,
    summary="Get Vendor Decision History",
    description="Returns deterministically paginated decision history for a vendor.",
)
def get_vendor_decision_history(
    vendor_id: str,
    page: int = Query(1, ge=1, description="Page number starting at 1"),
    page_size: int = Query(10, ge=1, le=100, description="Records per page"),
    db: Session = Depends(get_db),
) -> DecisionHistoryPagination:
    """Retrieve decision audit history for a vendor."""
    try:
        items, total_count, total_pages = decision_service.get_decision_history(
            db=db, vendor_id=vendor_id, page=page, page_size=page_size
        )
        return DecisionHistoryPagination(
            items=items,
            total=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
    except VendorNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor with ID '{vendor_id}' not found",
        )
