"""FastAPI endpoints for vendor supporting document intake, retrieval, download, and deletion."""

from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.document import VendorDocumentResponse, VendorDocumentPagination, DocumentCategory
from app.schemas.classification import (
    DocumentClassificationResponse,
    DocumentClassificationHistoryPagination,
)
from app.services.document_service import (
    document_service,
    DocumentNotFoundError,
    DocumentServiceError,
)
from app.services.classification_service import (
    classification_service,
    ClassificationServiceError,
    ClassificationNotFoundError,
)
from app.core.document_validator import DocumentValidationError, DocumentSizeExceededError, read_upload_file_bounded
from app.core.config import settings
from app.services.vendor_service import VendorNotFoundError
from app.core.logging import logger

router = APIRouter(prefix="/vendors/{vendor_id}/documents", tags=["documents"])


@router.post(
    "",
    response_model=VendorDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload Supporting Document",
    description="Uploads and securely encrypts a supporting compliance document (PDF, PNG, JPEG, up to 10 MB).",
)
async def upload_document(
    vendor_id: str,
    file: UploadFile = File(..., description="Document file binary payload"),
    document_category: Optional[str] = Form(
        None,
        description="Optional category: CERTIFICATE_OF_INCORPORATION, TAX_CERTIFICATE, BANK_PROOF, ADDRESS_PROOF, OTHER",
    ),
    db: Session = Depends(get_db),
) -> VendorDocumentResponse:
    """Upload, validate, encrypt, and associate a supporting document with a vendor."""
    try:
        # Bounded streaming read in fixed chunks (stops immediately if max size exceeded)
        content = await read_upload_file_bounded(
            file=file,
            max_size_bytes=settings.MAX_DOCUMENT_FILE_SIZE_BYTES,
        )
    except DocumentSizeExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Failed to read uploaded file stream: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read uploaded file stream.",
        )

    try:
        doc = document_service.upload_vendor_document(
            db=db,
            vendor_id=vendor_id,
            filename=file.filename,
            declared_content_type=file.content_type,
            content=content,
            category=document_category,
        )
        return VendorDocumentResponse.model_validate(doc)
    except VendorNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor with ID '{vendor_id}' not found.",
        )
    except DocumentSizeExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(e),
        )
    except DocumentValidationError as e:
        detail_msg = str(e)
        status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if "exceeds maximum allowed limit" in detail_msg else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail_msg)
    except DocumentServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get(
    "",
    response_model=VendorDocumentPagination,
    status_code=status.HTTP_200_OK,
    summary="List Vendor Documents",
    description="Returns a paginated list of uploaded document metadata for a vendor in deterministic order.",
)
def list_documents(
    vendor_id: str,
    category: Optional[str] = Query(None, description="Optional document category filter"),
    page: int = Query(1, ge=1, description="Page number starting at 1"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> VendorDocumentPagination:
    """List document metadata for a vendor."""
    try:
        docs, total, total_pages = document_service.list_vendor_documents(
            db=db,
            vendor_id=vendor_id,
            category=category,
            page=page,
            page_size=page_size,
        )
        items = [VendorDocumentResponse.model_validate(d) for d in docs]
        return VendorDocumentPagination(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
    except VendorNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor with ID '{vendor_id}' not found.",
        )


@router.get(
    "/{document_id}",
    response_model=VendorDocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Document Metadata",
    description="Returns metadata for an individual document belonging to the specified vendor.",
)
def get_document(
    vendor_id: str,
    document_id: str,
    db: Session = Depends(get_db),
) -> VendorDocumentResponse:
    """Retrieve metadata for a specific document."""
    try:
        doc = document_service.get_document_metadata(
            db=db, vendor_id=vendor_id, document_id=document_id
        )
        return VendorDocumentResponse.model_validate(doc)
    except DocumentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found for vendor '{vendor_id}'.",
        )


@router.get(
    "/{document_id}/content",
    status_code=status.HTTP_200_OK,
    summary="Download Document Content",
    description="Securely retrieves, decrypts, and streams the document contents with safe download headers.",
)
def download_document_content(
    vendor_id: str,
    document_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve and stream decrypted document binary contents."""
    try:
        doc, content = document_service.retrieve_document_content(
            db=db, vendor_id=vendor_id, document_id=document_id
        )
        # Safe Content-Disposition and MIME handling
        # Enforce attachment download to prevent inline script execution
        headers = {
            "Content-Disposition": f'attachment; filename="{doc.sanitized_filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store, no-cache, must-revalidate, private",
        }
        return Response(content=content, media_type=doc.mime_type, headers=headers)
    except DocumentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found for vendor '{vendor_id}'.",
        )
    except DocumentServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Supporting Document",
    description="Deletes a supporting document record and safely removes the encrypted file from storage.",
)
def delete_document(
    vendor_id: str,
    document_id: str,
    db: Session = Depends(get_db),
):
    """Delete a document record and clean up its stored encrypted file."""
    try:
        document_service.delete_vendor_document(
            db=db, vendor_id=vendor_id, document_id=document_id
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except DocumentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found for vendor '{vendor_id}'.",
        )
    except DocumentServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post(
    "/{document_id}/classify",
    response_model=DocumentClassificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Classify Supporting Document",
    description=(
        "Deterministically analyzes digital text layer to predict document category and produce explainable evidence. "
        "Returns a rule-based heuristic match score [0.00 - 1.00] measuring matched signals, not a statistical probability "
        "or authenticity verification."
    ),
)
def classify_document(
    vendor_id: str,
    document_id: str,
    db: Session = Depends(get_db),
) -> DocumentClassificationResponse:
    """Run deterministic content classification on an uploaded document."""
    try:
        classification = classification_service.classify_document(
            db=db, vendor_id=vendor_id, document_id=document_id
        )
        return DocumentClassificationResponse.model_validate(classification)
    except VendorNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor '{vendor_id}' not found.",
        )
    except DocumentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found for vendor '{vendor_id}'.",
        )
    except ClassificationServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get(
    "/{document_id}/classification",
    response_model=DocumentClassificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Latest Document Classification",
    description="Retrieves the most recent classification result and explainability signals for a document.",
)
def get_document_classification(
    vendor_id: str,
    document_id: str,
    db: Session = Depends(get_db),
) -> DocumentClassificationResponse:
    """Retrieve the latest classification for a document."""
    try:
        classification = classification_service.get_latest_classification(
            db=db, vendor_id=vendor_id, document_id=document_id
        )
        if not classification:
            raise ClassificationNotFoundError(f"No classification found for document '{document_id}'.")
        return DocumentClassificationResponse.model_validate(classification)
    except DocumentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found for vendor '{vendor_id}'.",
        )
    except ClassificationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No classification found for document '{document_id}'.",
        )
    except ClassificationServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get(
    "/{document_id}/classification-history",
    response_model=DocumentClassificationHistoryPagination,
    status_code=status.HTTP_200_OK,
    summary="Get Document Classification History",
    description="Retrieves chronological history of all classification runs for a document.",
)
def get_document_classification_history(
    vendor_id: str,
    document_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> DocumentClassificationHistoryPagination:
    """Retrieve paginated classification history for a document."""
    try:
        items, total, total_pages = classification_service.get_classification_history(
            db=db, vendor_id=vendor_id, document_id=document_id, page=page, page_size=page_size
        )
        return DocumentClassificationHistoryPagination(
            items=[DocumentClassificationResponse.model_validate(c) for c in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
    except DocumentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found for vendor '{vendor_id}'.",
        )
    except ClassificationServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
