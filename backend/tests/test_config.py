"""Tests for application configuration and lazy SEC compliance validation."""

import pytest

from backend.app.core.config import Settings, get_settings


def test_settings_initialization():
    """Verify default settings can be loaded without error even if env is minimal."""
    settings = get_settings()
    assert settings.APP_NAME == "FinGuard-X"
    assert settings.SEED == 42
    assert settings.DATA_DIR.exists()
    assert settings.RAW_DIR.exists()
    assert settings.CACHE_DIR.exists()
    assert settings.PROCESSED_DIR.exists()
    assert settings.GOLD_DIR.exists()
    assert settings.LOGS_DIR.exists()


def test_lazy_sec_user_agent_validation_success():
    """Valid User-Agent with app name and email passes validation."""
    valid_settings = Settings(SEC_USER_AGENT="FinGuardX-Research/1.0 (researcher@university.edu)")
    validated = valid_settings.validate_sec_user_agent()
    assert "researcher@university.edu" in validated


def test_lazy_sec_user_agent_validation_empty():
    """Empty or whitespace User-Agent raises descriptive ValueError on demand."""
    empty_settings = Settings(SEC_USER_AGENT="")
    with pytest.raises(ValueError, match="SEC_USER_AGENT is not configured"):
        empty_settings.validate_sec_user_agent()


def test_lazy_sec_user_agent_validation_missing_email():
    """User-Agent without an email address fails lazy validation per R4."""
    invalid_settings = Settings(SEC_USER_AGENT="FinGuardX-Research/1.0")
    with pytest.raises(ValueError, match="must contain a valid contact email"):
        invalid_settings.validate_sec_user_agent()
