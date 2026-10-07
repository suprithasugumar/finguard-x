"""Tests for Alembic migrations round-trip on PostgreSQL test database."""

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from backend.app.core.config import get_settings


def test_alembic_downgrade_upgrade_roundtrip(test_db_url: str, db_engine):
    """Verify that Alembic migrations cleanly downgrade to base and re-upgrade to head on PostgreSQL."""
    settings = get_settings()
    ini_path = settings.BASE_DIR / "alembic.ini"
    assert ini_path.exists(), f"alembic.ini not found at {ini_path}"

    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)

    # 1. Downgrade to base
    with db_engine.connect() as conn:
        alembic_cfg.attributes["connection"] = conn
        command.downgrade(alembic_cfg, "base")
        conn.commit()

    inspector = inspect(db_engine)
    tables_after_downgrade = set(inspector.get_table_names())
    assert "companies" not in tables_after_downgrade
    assert "filings" not in tables_after_downgrade
    assert "request_log" not in tables_after_downgrade

    # 2. Upgrade to head
    with db_engine.connect() as conn:
        alembic_cfg.attributes["connection"] = conn
        command.upgrade(alembic_cfg, "head")
        conn.commit()

    inspector = inspect(db_engine)
    tables_after_upgrade = set(inspector.get_table_names())
    assert "companies" in tables_after_upgrade
    assert "filings" in tables_after_upgrade
    assert "request_log" in tables_after_upgrade
    assert "alembic_version" in tables_after_upgrade

    # 3. Second round-trip to verify idempotency
    with db_engine.connect() as conn:
        alembic_cfg.attributes["connection"] = conn
        command.downgrade(alembic_cfg, "base")
        conn.commit()

    inspector = inspect(db_engine)
    assert "companies" not in set(inspector.get_table_names())

    with db_engine.connect() as conn:
        alembic_cfg.attributes["connection"] = conn
        command.upgrade(alembic_cfg, "head")
        conn.commit()

    inspector = inspect(db_engine)
    assert "companies" in set(inspector.get_table_names())
