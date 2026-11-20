"""Database connectivity, engine configuration, and session management."""

from typing import Generator, Optional
from sqlalchemy import create_engine, text, Engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings, get_sanitized_database_url
from app.core.logging import logger

# Resolve database URL predictably (absolute path for relative SQLite URLs)
db_url = settings.resolved_database_url

# SQLite specific connect args for multi-threaded FastAPI request handling
connect_args = {}
if db_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

try:
    engine = create_engine(
        db_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception as e:
    sanitized_url = get_sanitized_database_url(db_url)
    logger.error(f"Failed to initialize database engine for {sanitized_url}: {type(e).__name__}")
    raise


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a scoped database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection(target_engine: Optional[Engine] = None) -> bool:
    """Verifies that the database engine can successfully execute a query.
    
    Args:
        target_engine: Optional Engine instance to test (defaults to app engine).
        
    Returns:
        True if the database responds to a SELECT 1 query; False otherwise.
    """
    eng = target_engine or engine
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connectivity check failed: {type(e).__name__}")
        return False
