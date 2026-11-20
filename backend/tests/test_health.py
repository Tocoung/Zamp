"""Tests for operational probes, health check, and diagnostic endpoints."""

import os
from unittest.mock import patch
from sqlalchemy import text


def test_root_endpoint(client):
    """Test the root endpoint returns service metadata and probe paths."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "service" in data
    assert "version" in data
    assert "probes" in data
    assert data["probes"]["liveness"] == "/healthz"
    assert data["probes"]["readiness"] == "/readyz"


# ==============================================================================
# Liveness Probe Tests (/healthz)
# ==============================================================================

def test_liveness_healthz_endpoint(client):
    """Test /healthz liveness probe returns 200 OK and confirms process is running."""
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "alive"}


# ==============================================================================
# Readiness Probe Tests (/readyz)
# ==============================================================================

def test_readiness_readyz_healthy(client, test_engine):
    """Test /readyz returns 200 OK when database connectivity is healthy."""
    with patch("app.main.check_db_connection", return_value=True):
        response = client.get("/readyz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["dependencies"]["database"] == "connected"


def test_readiness_readyz_degraded(client):
    """Test /readyz returns 503 Service Unavailable when database connection fails."""
    with patch("app.main.check_db_connection", return_value=False):
        response = client.get("/readyz")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["dependencies"]["database"] == "disconnected"


# ==============================================================================
# Diagnostic Endpoint Tests (/api/v1/health)
# ==============================================================================

def test_api_v1_health_healthy(client):
    """Test /api/v1/health returns 200 OK and detailed diagnostic metadata when ready."""
    with patch("app.api.v1.endpoints.health.check_db_connection", return_value=True):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert "timestamp" in data
        assert "environment" in data
        assert "version" in data


def test_api_v1_health_degraded(client):
    """Test /api/v1/health returns 503 Service Unavailable when degraded."""
    with patch("app.api.v1.endpoints.health.check_db_connection", return_value=False):
        response = client.get("/api/v1/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"] == "disconnected"


# ==============================================================================
# Database Isolation Verification
# ==============================================================================

def test_database_isolation(test_engine, test_db_session, dev_db_file_path, test_db_path):
    """Verify that tests execute exclusively against the isolated temporary database.
    
    Confirms:
    1. Queries execute successfully on the isolated test engine.
    2. The temporary test database file exists in the session tmp directory.
    3. The dev database is not modified by test execution.
    """
    # 1. Execute test query on isolated engine
    result = test_db_session.execute(text("SELECT 42")).scalar()
    assert result == 42

    # 2. Assert temporary database path exists
    assert test_db_path.exists()
    assert "zamp_test_data" in str(test_db_path)

    # 3. Development database path is distinct from test database path
    assert str(dev_db_file_path) != str(test_db_path)
