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
    database_url: str = "postgresql+psycopg2://etf:etf_research_password@localhost:5432/etf_research"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Data provider
    tushare_token: str = ""

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

    # Constants
    api_v1_prefix: str = "/api/v1"
    project_name: str = "ETF Research Platform"

    @property
    def is_development(self) -> bool:
        """Return True if running in development mode."""
        return self.app_env.lower() == "development"


class AuthSettings(BaseSettings):
    """Authentication settings."""

    SECRET_KEY: str = "your-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
    NOTIFICATION_ENCRYPTION_KEY: str = ""

    # Multi-user credentials: username -> password
    USERS: dict[str, str] = {
        "admin": "admin123",
        "Aidan": "19880402",
        "Tee": "19790615",
        "Zack": "19911213",
        "Philip": "19900225",
    }

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
