"""Tests for configuration parsing, defaults, validation, and security sanitization."""

import pytest
from pydantic import ValidationError
from app.core.config import Settings, PROJECT_ROOT, get_sanitized_database_url


def test_default_settings():
    """Verify default settings instantiate with expected values."""
    settings = Settings()
    assert settings.PROJECT_NAME == "Zamp Vendor Onboarding Automation"
    assert settings.BACKEND_PORT == 8000
    assert settings.API_V1_PREFIX == "/api/v1"
    assert "http://localhost:5173" in settings.CORS_ORIGINS
    assert settings.DATABASE_URL.startswith("sqlite")


def test_cors_origins_parsing():
    """Verify string and JSON array parsing for CORS_ORIGINS."""
    settings_csv = Settings(CORS_ORIGINS="http://test1.com, http://test2.com")
    assert settings_csv.CORS_ORIGINS == ["http://test1.com", "http://test2.com"]

    settings_json = Settings(CORS_ORIGINS='["http://test3.com", "http://test4.com"]')
    assert settings_json.CORS_ORIGINS == ["http://test3.com", "http://test4.com"]


def test_sqlite_relative_path_resolution():
    """Verify relative SQLite paths resolve predictably against PROJECT_ROOT."""
    # 1. Standard relative path
    settings_rel = Settings(DATABASE_URL="sqlite:///./test_custom.db")
    expected_path = (PROJECT_ROOT / "test_custom.db").resolve()
    assert settings_rel.resolved_database_url == f"sqlite:///{expected_path}"

    # 2. In-memory path preserved
    settings_mem = Settings(DATABASE_URL="sqlite:///:memory:")
    assert settings_mem.resolved_database_url == "sqlite:///:memory:"

    # 3. Absolute path preserved
    settings_abs = Settings(DATABASE_URL="sqlite:////var/data/app.db")
    assert settings_abs.resolved_database_url == "sqlite:////var/data/app.db"


def test_sanitized_database_url():
    """Verify that credentials are fully masked from database URLs."""
    # 1. PostgreSQL URL with user & password
    sensitive_pg_url = "postgresql+psycopg2://admin:super_secret_password@db.internal:5432/zamp_prod"
    sanitized_pg = get_sanitized_database_url(sensitive_pg_url)
    assert "super_secret_password" not in sanitized_pg
    assert "***" in sanitized_pg
    assert "db.internal:5432/zamp_prod" in sanitized_pg

    # 2. SQLite file URL
    sqlite_url = "sqlite:////tmp/vendor_onboarding.db"
    sanitized_sqlite = get_sanitized_database_url(sqlite_url)
    assert "sqlite" in sanitized_sqlite


def test_configuration_validation_error():
    """Verify that invalid configuration values raise a Pydantic ValidationError."""
    with pytest.raises(ValidationError):
        Settings(BACKEND_PORT="not_a_valid_port")
