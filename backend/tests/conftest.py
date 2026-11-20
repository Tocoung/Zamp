"""Pytest fixtures and test environment configuration."""

import os
import sys
from pathlib import Path
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Ensure backend root is on Python path
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.main import app
from app.core.config import settings, PROJECT_ROOT
from app.db.base import Base
from app.db.session import get_db, check_db_connection


@pytest.fixture(scope="session")
def test_db_path(tmp_path_factory) -> Path:
    """Creates a temporary, isolated SQLite database file path for the test session."""
    tmp_dir = tmp_path_factory.mktemp("zamp_test_data")
    return tmp_dir / "isolated_test_onboarding.db"


@pytest.fixture(scope="session")
def test_engine(test_db_path: Path):
    """Creates an isolated SQLAlchemy engine bound strictly to the temporary test database."""
    engine = create_engine(
        f"sqlite:///{test_db_path}",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="session")
def test_session_factory(test_engine):
    """Provides a sessionmaker bound to the isolated test engine."""
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def test_db_session(test_session_factory) -> Generator[Session, None, None]:
    """Yields an isolated database session per test function."""
    session = test_session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def client(test_engine, test_session_factory):
    """Provides a TestClient with dependency overrides bound to the isolated test database."""
    def _override_get_db():
        session = test_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
        
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def dev_db_file_path() -> Path:
    """Returns the resolved path of the development database to verify isolation."""
    return PROJECT_ROOT / "vendor_onboarding.db"
