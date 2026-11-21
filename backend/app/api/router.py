"""API Router aggregation module."""

from fastapi import APIRouter
from app.api.v1.endpoints import health, vendors, documents

api_router = APIRouter()

# Mount v1 endpoints
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(vendors.router, prefix="/vendors", tags=["Vendors"])
api_router.include_router(documents.router, tags=["Documents"])

# Future Phase Extension Mount Points:
# api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
# api_router.include_router(reviews.router, prefix="/reviews", tags=["Human Review"])
# api_router.include_router(audit.router, prefix="/audit", tags=["Audit Log"])
