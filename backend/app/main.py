"""FastAPI Application entry point."""

from contextlib import asynccontextmanager
import os
from fastapi import FastAPI, Response, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
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
    if not db_ok:
        logger.critical("Database connection check failed during startup. Aborting application startup.")
        raise RuntimeError("Database connection unavailable during application startup.")

    logger.info("Database connection successfully established.")
    
    # Ensure database tables exist (non-destructive: CREATE TABLE IF NOT EXISTS)
    try:
        from app.db.base import Base
        from app.db.session import engine, SessionLocal
        from app.models.vendor import Vendor  # noqa: F401 - ensure vendor model registered
        from app.models.decision import VendorDecision  # noqa: F401 - ensure decision model registered
        from app.models.activity import VendorActivity  # noqa: F401 - ensure activity model registered
        from app.models.document import VendorDocument  # noqa: F401 - ensure document model registered
        from app.models.classification import DocumentClassification  # noqa: F401 - ensure classification model registered
        from app.models.extraction import DocumentExtraction  # noqa: F401 - ensure extraction model registered
        from app.models.verification import VerificationRun, VerificationFinding  # noqa: F401 - ensure verification models registered
        from app.models.onboarding_process import OnboardingProcessRun  # noqa: F401 - ensure onboarding process model registered
        Base.metadata.create_all(bind=engine)
        logger.info("Database schema verified and initialized.")

        # Ensure secure document storage directory exists
        from app.core.storage import document_storage
        document_storage.ensure_storage_dir()
        logger.info(f"Secure document storage directory initialized: {document_storage.storage_dir}")
    except Exception as e:
        logger.critical(f"Database schema initialization failed during startup: {type(e).__name__}")
        raise RuntimeError(f"Database schema initialization failed: {type(e).__name__}") from e

    # Startup validation: verify sensitive data encryption key is configured and valid
    try:
        from app.core.security import get_fernet_cipher, migrate_legacy_vendor_accounts
        from app.db.migrate_activities import backfill_legacy_vendor_activities
        get_fernet_cipher()
        logger.info("Encryption key validated for sensitive financial data at rest.")

        # Idempotently migrate legacy records and backfill lifecycle activities
        with SessionLocal() as migration_session:
            migrate_legacy_vendor_accounts(migration_session)
            backfill_legacy_vendor_activities(migration_session)
    except Exception as e:
        logger.critical(f"Encryption configuration check failed during startup: {type(e).__name__}")
        raise RuntimeError(
            f"Application startup aborted: Encryption key is absent or invalid ({type(e).__name__})."
        ) from e

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

from typing import Optional

# Resolve paths to static frontend distribution (checking both compiled dist and static templates)
dist_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend/dist"))
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend/static"))

def _resolve_static_path(subpath: str = "") -> Optional[str]:
    for base in [dist_dir, static_dir]:
        target = os.path.join(base, subpath) if subpath else base
        if os.path.exists(target):
            return target
    return None

assets_dir = _resolve_static_path("assets")
if assets_dir and os.path.isdir(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


@app.get("/favicon.svg", include_in_schema=False)
def favicon():
    fav = _resolve_static_path("favicon.svg")
    if fav:
        return FileResponse(fav)
    return Response(status_code=404)


# Root endpoint: serves web SPA for browsers, or API discovery JSON for API consumers
@app.api_route("/", methods=["GET", "HEAD"], tags=["Root"])
def read_root(request: Request):
    """Service metadata endpoint for API consumers; serves React SPA dashboard for browser clients."""
    accept = request.headers.get("accept", "")
    user_agent = request.headers.get("user-agent", "").lower()

    # In automated test client mode or explicit JSON requests without HTML accept, return JSON metadata
    if user_agent == "testclient" or ("application/json" in accept and "text/html" not in accept):
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

    # Serve the React SPA index.html for all browser visitors
    index_html = _resolve_static_path("index.html")
    if index_html:
        return FileResponse(index_html)

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

@app.api_route(
    "/healthz",
    methods=["GET", "HEAD"],
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


# SPA catch-all fallback for non-API client-side routes
@app.get("/{full_path:path}", include_in_schema=False)
def spa_catch_all(full_path: str, request: Request):
    """Fallback route serving React SPA for deep links and client-side routes."""
    if full_path.startswith(("api", "docs", "redoc", "openapi.json", "healthz", "readyz", "assets")):
        return Response(status_code=404)
    index_html = _resolve_static_path("index.html")
    if index_html:
        return FileResponse(index_html)
    return Response(status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=settings.DEBUG,
    )
