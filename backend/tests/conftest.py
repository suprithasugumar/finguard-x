"""Pytest configuration and database fixtures for FinGuard-X."""

import os
from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models import Base


@pytest.fixture(scope="session")
def test_db_url() -> str:
    """Return test database URL from settings or environment."""
    settings = get_settings()
    url = os.environ.get("TEST_DATABASE_URL") or settings.TEST_DATABASE_URL
    assert "test" in url.lower() or "finguard_test" in url, f"Safety check: not a test DB: {url}"
    return url


@pytest.fixture(scope="session")
def db_engine(test_db_url: str):
    """Create engine bound to the PostgreSQL test database."""
    engine = create_engine(test_db_url, pool_pre_ping=True)
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    """Provide a transactional database session rolled back after each test."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()
