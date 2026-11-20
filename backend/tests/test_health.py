"""Tests for health check and diagnostic endpoints."""

import pytest
from unittest.mock import patch


def test_root_endpoint(client):
    """Test the root endpoint returns expected service metadata."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "service" in data
    assert "version" in data
    assert "documentation" in data


def test_healthz_endpoint(client):
    """Test liveness probe endpoint."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_endpoint_healthy(client):
    """Test the /api/v1/health endpoint when database is connected."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert "timestamp" in data
    assert "environment" in data
    assert "version" in data


def test_health_endpoint_degraded(client):
    """Test the /api/v1/health endpoint when database connectivity fails."""
    with patch("app.api.v1.endpoints.health.check_db_connection", return_value=False):
        response = client.get("/api/v1/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"] == "disconnected"
