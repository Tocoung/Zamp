"""FastAPI endpoints for vendor supporting document intake, retrieval, download, and deletion."""

from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.document import VendorDocumentResponse, VendorDocumentPagination, DocumentCategory
from app.services.document_service import (
    document_service,
    DocumentNotFoundError,
    DocumentServiceError,
)
from app.core.document_validator import DocumentValidationError
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
        # Read file contents into memory (bounded by 10 MB in document validator)
        content = await file.read()
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
