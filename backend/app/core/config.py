"""Application configuration module using Pydantic Settings."""

import os
from pathlib import Path
from typing import List, Union, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

# Project directory paths
# config.py -> core -> app -> backend -> project_root
BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def get_sanitized_database_url(url: str) -> str:
    """Return a masked database connection string safe for logging.
    
    Hides credentials while retaining dialect, driver, host, and database name.
    """
    try:
        parsed = make_url(url)
        return parsed.render_as_string(hide_password=True)
    except Exception:
        return "sqlite:///[sanitized]" if "sqlite" in str(url) else "database://[sanitized]"


class Settings(BaseSettings):
    """Central configuration for backend services."""

    PROJECT_NAME: str = "Zamp Vendor Onboarding Automation"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Server settings
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    API_V1_PREFIX: str = "/api/v1"

    # CORS Configuration
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, tuple)):
            return list(v)
        raise ValueError("Invalid format for CORS_ORIGINS")

    # Database connection URL
    # Default: Relative SQLite URL, resolved deterministically against PROJECT_ROOT
    DATABASE_URL: str = "sqlite:///./vendor_onboarding.db"

    # Data Encryption at rest (Fernet 32-byte URL-safe base64 key)
    # Must be set in environment. Never logged or exposed.
    VENDOR_DATA_ENCRYPTION_KEY: Optional[str] = None

    # Document storage & encryption settings
    DOCUMENT_STORAGE_DIR: str = "data/documents"
    MAX_DOCUMENT_FILE_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB maximum upload size
    DOCUMENT_ENCRYPTION_KEY: Optional[str] = None  # Optional dedicated key; falls back to VENDOR_DATA_ENCRYPTION_KEY

    @property
    def resolved_document_storage_dir(self) -> Path:
        """Resolve document storage directory predictably against project root.
        
        Guarantees that files are placed securely outside the frontend or webroot directories.
        """
        raw_path = Path(self.DOCUMENT_STORAGE_DIR)
        if not raw_path.is_absolute():
            return (PROJECT_ROOT / raw_path).resolve()
        return raw_path.resolve()

    @property
    def resolved_database_url(self) -> str:
        """Resolve relative SQLite database paths predictably to the project root directory.
        
        Guarantees that SQLite file location is deterministic regardless of the
        terminal working directory (e.g. running from project root vs backend/ directory).
        """
        url_str = self.DATABASE_URL
        if url_str.startswith("sqlite") and not url_str.startswith("sqlite:///:memory:"):
            prefix = "sqlite:///"
            if url_str.startswith(prefix):
                raw_path = url_str[len(prefix):]
                # If path is relative (does not start with a leading slash on POSIX)
                if not raw_path.startswith("/"):
                    normalized_path = (PROJECT_ROOT / raw_path).resolve()
                    return f"sqlite:///{normalized_path}"
        return url_str

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


def get_settings() -> Settings:
    """Instantiate and return settings singleton."""
    return Settings()


settings = get_settings()
