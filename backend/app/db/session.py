"""Database engine and session management."""

from typing import Generator, Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import get_settings

_engine: Optional[Engine] = None
_SessionFactory: Optional[sessionmaker[Session]] = None


def get_engine(db_url: Optional[str] = None) -> Engine:
    """Return singleton or custom database engine."""
    global _engine
    if db_url is not None:
        return create_engine(
            db_url,
            pool_pre_ping=True,
            echo=False,
        )
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.DATABASE_URL,
            pool_pre_ping=True,
            echo=False,
        )
    return _engine


def get_session_factory(engine: Optional[Engine] = None) -> sessionmaker[Session]:
    """Return sessionmaker bound to engine."""
    global _SessionFactory
    if engine is not None:
        return sessionmaker(autocommit=False, autoflush=False, bind=engine)
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionFactory


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session."""
    session_factory = get_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
