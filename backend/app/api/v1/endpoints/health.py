"""Health check and diagnostic endpoints."""

from datetime import datetime, timezone
from fastapi import APIRouter, status, Response
from pydantic import BaseModel, Field

from app.core.config import settings
from app.db.session import check_db_connection

router = APIRouter()


class HealthResponse(BaseModel):
    """Schema for application health check."""
    status: str = Field(..., examples=["healthy"])
    timestamp: str = Field(..., examples=["2026-11-21T00:00:00Z"])
    environment: str = Field(..., examples=["development"])
    version: str = Field(..., examples=["0.1.0"])
    database: str = Field(..., examples=["connected"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Application & Database Health Check",
    description="Returns current status of API server, environment, and database connectivity.",
)
def get_health(response: Response) -> HealthResponse:
    """Verifies operational status of the service and underlying database."""
    is_db_connected = check_db_connection()
    db_status = "connected" if is_db_connected else "disconnected"

    if not is_db_connected:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="healthy" if is_db_connected else "degraded",
        timestamp=datetime.now(timezone.utc).isoformat(),
        environment=settings.ENVIRONMENT,
        version=settings.VERSION,
        database=db_status,
    )
