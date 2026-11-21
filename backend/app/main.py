"""FastAPI Application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import logger
from app.db.session import check_db_connection
from app.api.router import api_router


class LivenessResponse(BaseModel):
    """Schema for Kubernetes/container liveness probe."""
    status: str = Field(..., examples=["alive"])


class ReadinessDependencies(BaseModel):
    """Dependency status breakdown for readiness probe."""
    database: str = Field(..., examples=["connected", "disconnected"])


class ReadinessResponse(BaseModel):
    """Schema for Kubernetes/container readiness probe."""
    status: str = Field(..., examples=["ready", "not_ready"])
    dependencies: ReadinessDependencies


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown routines."""
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION} [{settings.ENVIRONMENT}]")
    
    # Startup validation: verify database connectivity
    db_ok = check_db_connection()
    if db_ok:
        logger.info("Database connection successfully established.")
        # Ensure database tables exist (safe initialization: CREATE TABLE IF NOT EXISTS)
        try:
            from app.db.base import Base
            from app.db.session import engine
            import app.models  # noqa: F401 - registers models
            Base.metadata.create_all(bind=engine)
            logger.info("Database schema verified and initialized.")
        except Exception as e:
            logger.error(f"Error during schema initialization: {e}")
    else:
        logger.warning("Database connection failed during startup. Operating in degraded mode.")

    yield

    logger.info("Shutting down application...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "Automated Vendor Onboarding Engine API with AI-ready architecture. "
        "Provides dedicated liveness (/healthz), readiness (/readyz), and diagnostic endpoints."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure Cross-Origin Resource Sharing (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root endpoint
@app.get("/", tags=["Root"])
def read_root():
    """Service metadata and root discovery endpoint."""
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "online",
        "documentation": "/docs",
        "api_prefix": settings.API_V1_PREFIX,
        "probes": {
            "liveness": "/healthz",
            "readiness": "/readyz",
            "diagnostics": f"{settings.API_V1_PREFIX}/health",
        },
    }


# ==============================================================================
# Operational Probes (Liveness & Readiness)
# ==============================================================================

@app.get(
    "/healthz",
    response_model=LivenessResponse,
    status_code=status.HTTP_200_OK,
    tags=["Probes"],
    summary="Liveness Probe",
    description="Confirms that the FastAPI application process is alive and responsive to HTTP traffic.",
)
def healthz() -> LivenessResponse:
    """Liveness probe: returns 200 OK if the process is running."""
    return LivenessResponse(status="alive")


@app.get(
    "/readyz",
    response_model=ReadinessResponse,
    tags=["Probes"],
    summary="Readiness Probe",
    description=(
        "Checks whether critical application dependencies (e.g., primary database) "
        "are available to accept client traffic. Returns 200 OK when ready; 503 Service Unavailable when degraded."
    ),
)
def readyz(response: Response) -> ReadinessResponse:
    """Readiness probe: checks critical dependency connectivity."""
    db_ok = check_db_connection()
    
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            status="not_ready",
            dependencies=ReadinessDependencies(database="disconnected"),
        )

    response.status_code = status.HTTP_200_OK
    return ReadinessResponse(
        status="ready",
        dependencies=ReadinessDependencies(database="connected"),
    )


# Mount API v1 router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=settings.DEBUG,
    )
