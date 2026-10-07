"""Tests for session generation and logging utilities."""

from backend.app.core.logging import logger, setup_logging
from backend.app.db.session import get_db, get_engine, get_session_factory


def test_session_generator():
    """Verify get_db session dependency lifecycle."""
    session_gen = get_db()
    session = next(session_gen)
    assert session is not None
    assert session.is_active
    try:
        session_gen.send(None)
    except StopIteration:
        pass


def test_custom_engine_and_factory():
    """Verify get_engine and get_session_factory can accept custom parameters."""
    eng = get_engine()
    assert eng is not None
    factory = get_session_factory(eng)
    assert factory is not None


def test_logging_setup():
    """Verify logger setup produces active logger."""
    log = setup_logging()
    assert log is not None
    logger.info("Test logging message")
