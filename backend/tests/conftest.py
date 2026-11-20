"""Pytest fixtures and test environment configuration."""

import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure backend root is on Python path
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.main import app
from app.core.config import settings


@pytest.fixture(scope="session")
def client():
    """Provides a TestClient instance for API integration testing."""
    with TestClient(app) as test_client:
        yield test_client
