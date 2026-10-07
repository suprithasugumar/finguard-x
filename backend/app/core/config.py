"""Application configuration and environment settings."""

import re
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """FinGuard-X runtime configuration.

    Reads from environment variables and .env file.
    SEC_USER_AGENT is deliberately validated lazily (R4), not at import time,
    so non-SEC tasks, migrations, and tests can run without SEC credentials.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core Identifiers & Reproducibility (R6)
    APP_NAME: str = "FinGuard-X"
    APP_ENV: str = "development"
    SEED: int = 42

    # Database URLs (PostgreSQL target)
    DATABASE_URL: str = "postgresql://druid:FoolishPassword@localhost:5432/finguard"
    TEST_DATABASE_URL: str = "postgresql://druid:FoolishPassword@localhost:5432/finguard_test"

    # SEC EDGAR Compliance (R4)
    # Declared user agent: <ApplicationName>/<Version> (<ContactEmail>)
    SEC_USER_AGENT: str = ""
    SEC_MAX_REQUESTS_PER_SECOND: float = 5.0

    # Logging
    LOG_LEVEL: str = "INFO"

    # Directory Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    RAW_DIR: Path = DATA_DIR / "raw"
    CACHE_DIR: Path = DATA_DIR / "cache"
    PROCESSED_DIR: Path = DATA_DIR / "processed"
    GOLD_DIR: Path = DATA_DIR / "gold"
    LOGS_DIR: Path = BASE_DIR / "logs"

    def ensure_directories(self) -> None:
        """Create local data/log directories if they do not exist."""
        for path in [
            self.RAW_DIR,
            self.CACHE_DIR,
            self.PROCESSED_DIR,
            self.GOLD_DIR,
            self.LOGS_DIR,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def validate_sec_user_agent(self) -> str:
        """Lazily validate SEC User-Agent compliance.

        Per SEC requirements (R4), the User-Agent must identify the application
        and provide a valid contact email: e.g., 'App/1.0 (contact@example.com)'.
        """
        ua = (self.SEC_USER_AGENT or "").strip()
        if not ua:
            raise ValueError(
                "SEC_USER_AGENT is not configured. SEC EDGAR API compliance (R4) requires "
                "a User-Agent in the format 'AppName/Version (contact_email@domain.com)'."
            )
        # Check for email-like pattern inside user agent
        email_pattern = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
        if not re.search(email_pattern, ua):
            raise ValueError(
                f"Invalid SEC_USER_AGENT: '{ua}'. Per SEC EDGAR rules, the User-Agent "
                "must contain a valid contact email address."
            )
        return ua


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings instance."""
    settings = Settings()
    settings.ensure_directories()
    return settings
