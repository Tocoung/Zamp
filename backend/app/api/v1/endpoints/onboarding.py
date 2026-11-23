"""End-to-end onboarding orchestration API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.onboarding_process import (
    OnboardingProcessHistoryResponse,
    OnboardingProcessRunResponse,
)
from app.services.onboarding_orchestrator_service import (
    onboarding_orchestrator,
    VendorNotFoundError,
    OnboardingOrchestratorError,
)

router = APIRouter(prefix="/vendors", tags=["Onboarding Orchestration"])


@router.post(
    "/{vendor_id}/process-onboarding",
    response_model=OnboardingProcessRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute End-to-End Onboarding Process",
    description="Coordinates document intake, classification, OCR extraction, evidence provenance, cross-document verification, and Phase 1 validation/decisioning into an integrated workflow.",
)
def process_vendor_onboarding(
    vendor_id: str,
    force_reprocess: bool = Query(False, description="Whether to force reprocessing even if documents and profile are unchanged"),
    db: Session = Depends(get_db),
) -> OnboardingProcessRunResponse:
    """Executes the complete 8-stage onboarding pipeline for a vendor."""
    try:
        return onboarding_orchestrator.process_vendor_onboarding(
            db=db,
            vendor_id=vendor_id,
            force_reprocess=force_reprocess,
        )
    except VendorNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except OnboardingOrchestratorError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected pipeline failure: {type(e).__name__}",
        )


@router.get(
    "/{vendor_id}/onboarding-process/latest",
    response_model=OnboardingProcessRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Latest Onboarding Process Run",
    description="Retrieves the most recent end-to-end onboarding processing run details and stage breakdown.",
)
def get_latest_onboarding_process(
    vendor_id: str,
    db: Session = Depends(get_db),
) -> OnboardingProcessRunResponse:
    """Retrieves the latest onboarding run for a vendor."""
    try:
        run = onboarding_orchestrator.get_latest_run(db=db, vendor_id=vendor_id)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No onboarding processing runs found for vendor '{vendor_id}'.",
            )
        return run
    except VendorNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "/{vendor_id}/onboarding-process/history",
    response_model=OnboardingProcessHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Onboarding Process Run History",
    description="Retrieves the full append-only execution history of onboarding processing runs for a vendor.",
)
def get_onboarding_process_history(
    vendor_id: str,
    db: Session = Depends(get_db),
) -> OnboardingProcessHistoryResponse:
    """Retrieves the onboarding execution history for a vendor."""
    try:
        return onboarding_orchestrator.get_history(db=db, vendor_id=vendor_id)
    except VendorNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
