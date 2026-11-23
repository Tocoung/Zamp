"""Cross-document verification and discrepancy detection API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.verification import (
    VerificationHistoryResponse,
    VerificationRunResponse,
)
from app.services.verification_service import (
    VerificationService,
    VerificationServiceError,
    VendorNotFoundError,
)

router = APIRouter(prefix="/vendors", tags=["Cross-Document Verification"])


@router.post(
    "/{vendor_id}/verification",
    response_model=VerificationRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Execute Cross-Document Verification",
    description="Runs cross-document validation comparing vendor profile data against extracted document evidence and cross-checking document extractions.",
)
def run_vendor_verification(
    vendor_id: str,
    db: Session = Depends(get_db),
) -> VerificationRunResponse:
    """Executes cross-document verification for a vendor."""
    try:
        return VerificationService.run_verification_for_vendor(db=db, vendor_id=vendor_id)
    except VendorNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except VerificationServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get(
    "/{vendor_id}/verification/latest",
    response_model=VerificationRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Latest Verification Run",
    description="Retrieves the most recent verification run results and findings for a vendor.",
)
def get_latest_vendor_verification(
    vendor_id: str,
    db: Session = Depends(get_db),
) -> VerificationRunResponse:
    """Retrieves the latest verification execution for a vendor."""
    try:
        result = VerificationService.get_latest_verification(db=db, vendor_id=vendor_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No verification run has been executed for vendor '{vendor_id}'.",
            )
        return result
    except VendorNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except VerificationServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get(
    "/{vendor_id}/verification/history",
    response_model=VerificationHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Verification History",
    description="Retrieves paginated historical verification executions for a vendor.",
)
def get_vendor_verification_history(
    vendor_id: str,
    page: int = Query(1, ge=1, description="Page number starting at 1"),
    page_size: int = Query(10, ge=1, le=100, description="Records per page"),
    db: Session = Depends(get_db),
) -> VerificationHistoryResponse:
    """Retrieves paginated verification execution history for a vendor."""
    try:
        return VerificationService.get_verification_history(
            db=db,
            vendor_id=vendor_id,
            page=page,
            page_size=page_size,
        )
    except VendorNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except VerificationServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get(
    "/{vendor_id}/verification/{run_id}",
    response_model=VerificationRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Specific Verification Run",
    description="Retrieves a specific verification run by ID for a vendor.",
)
def get_vendor_verification_run(
    vendor_id: str,
    run_id: str,
    db: Session = Depends(get_db),
) -> VerificationRunResponse:
    """Retrieves a specific verification execution by run ID."""
    try:
        result = VerificationService.get_verification_run(
            db=db,
            vendor_id=vendor_id,
            run_id=run_id,
        )
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Verification run '{run_id}' not found for vendor '{vendor_id}'.",
            )
        return result
    except VendorNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except VerificationServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
