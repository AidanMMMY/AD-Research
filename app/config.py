"""Application configuration using Pydantic Settings.

Loads configuration from environment variables and .env files.
Use `get_settings()` to retrieve a cached Settings instance.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+psycopg2://etf:etf_research_password@localhost:5432/ad_research"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Data provider
    tushare_token: str = ""

    # US market data providers (free tiers sufficient for hobby use)
    finnhub_api_key: str = ""   # https://finnhub.io/register (60 req/min free)
    tiingo_api_key: str = ""    # https://www.tiingo.com/account/token (1k/day free)
    fmp_api_key: str = ""       # https://site.financialmodelingprep.com (250/day free)

    # AI / LLM
    deepseek_api_key: str = ""   # https://platform.deepseek.com/

    # Application
    app_env: str = "development"
    log_level: str = "INFO"

    # SMTP / Email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True

    # Notification encryption (used by NotificationService to encrypt
    # sensitive webhook/email credentials at rest). Kept here rather than
    # AuthSettings because it is not an authentication concern.
    notification_encryption_key: str = ""

    # Constants
    api_v1_prefix: str = "/api/v1"
    project_name: str = "AD-Research"

    @property
    def is_development(self) -> bool:
        """Return True if running in development mode."""
        return self.app_env.lower() == "development"


class AuthSettings(BaseSettings):
    """Authentication settings loaded from environment variables.

    Never commit plaintext passwords to source control. Set these via
    environment variables or a secrets manager in production.
    """

    SECRET_KEY: str = "your-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = ""

    model_config = SettingsConfigDict(
        env_prefix="AUTH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


auth_settings = AuthSettings()


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    The instance is cached to avoid re-reading environment variables
    on every call.
    """
    return Settings()
