"""Tests for configuration parsing, defaults, and validation."""

import pytest
from app.core.config import Settings


def test_default_settings():
    """Verify that default settings instantiate with expected properties."""
    settings = Settings()
    assert settings.PROJECT_NAME == "Zamp Vendor Onboarding Automation"
    assert settings.BACKEND_PORT == 8000
    assert settings.API_V1_PREFIX == "/api/v1"
    assert "http://localhost:5173" in settings.CORS_ORIGINS
    assert settings.DATABASE_URL.startswith("sqlite")


def test_cors_origins_parsing():
    """Verify comma-separated string parsing for CORS_ORIGINS."""
    settings = Settings(CORS_ORIGINS="http://test1.com, http://test2.com")
    assert settings.CORS_ORIGINS == ["http://test1.com", "http://test2.com"]

    settings_json = Settings(CORS_ORIGINS='["http://test3.com", "http://test4.com"]')
    assert settings_json.CORS_ORIGINS == ["http://test3.com", "http://test4.com"]
