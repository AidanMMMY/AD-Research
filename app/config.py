"""Application configuration using Pydantic Settings.

Loads configuration from environment variables and .env files.
Use `get_settings()` to retrieve a cached Settings instance.
"""

import logging
import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# P0-7 (2026-07-16): ``SECRET_KEY`` must not ship with the well-known
# placeholder that was previously hard-coded as the default in this
# file. The set of "known-bad" values covers both the original
# placeholder and a few variants seen in commits / tutorials so a
# stray ``AUTH_SECRET_KEY=secret`` / ``change-me`` no longer reaches a
# production process silently. The validation runs once at module
# import time (``auth_settings = AuthSettings()`` below) so a bad
# value prevents the process from starting.
#
# In development (``APP_ENV=development``) we log a warning instead of
# refusing to start — local Docker compose + pytest setups historically
# rely on the placeholder to keep ``.env`` files out of git.
_KNOWN_BAD_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "your-secret-key-change-in-production",
        "your-secret-key",
        "change-me",
        "changeme",
        "secret",
        "secret-key",
        "default-secret-key",
        "",
    }
)
_DEV_PLACEHOLDER_SECRET_KEY = "your-secret-key-change-in-production"


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

    # Macro data (free with registration, takes ~2 minutes)
    fred_api_key: str = ""     # https://fred.stlouisfed.org/docs/api/api_key.html (US macro: GDP/CPI/unemployment/yields)
    bls_api_key: str = ""      # https://data.bls.gov/registrationEngine/ (optional — public API works w/o key but rate-limited)
    bea_api_key: str = ""      # https://apps.bea.gov/API/signup/ (optional — same as BLS)

    # Binance / Crypto (public REST endpoints do not require API key)
    binance_api_key: str = ""        # https://www.binance.com/en/my/settings/api-management
    binance_api_secret: str = ""      # Needed only for account/trading endpoints (Phase 3)

    # Binance trading (Phase 3 – live trading)
    # Testnet: https://testnet.binance.vision/
    # Production: https://www.binance.com/
    binance_testnet_key: str = ""          # Testnet API key
    binance_testnet_secret: str = ""        # Testnet API secret
    binance_trading_enabled: bool = False   # Master switch — must be True for live orders
    binance_max_order_value_usdt: float = 100.0   # Max USDT per single order
    binance_max_daily_loss_usdt: float = 500.0     # Max daily realised loss before circuit-breaker
    binance_max_daily_orders: int = 20              # Max orders per calendar day
    binance_market_order_slippage: float = 0.001    # Slippage buffer for MARKET order risk checks (0.1%)

    # AI / LLM
    deepseek_api_key: str = ""   # https://platform.deepseek.com/

    # Per-user daily cap on the research-reports "生成摘要" on-demand
    # endpoint. Counted in Redis with a 24h TTL keyed by user + date.
    research_report_summarize_daily_limit: int = 100

    # Per-user daily cap on the news "/translate" on-demand endpoint.
    # Counted in Redis with a 24h TTL keyed by user + date. Same shape
    # as research_report_summarize_daily_limit so the two endpoints
    # can't surprise each other in the future.
    news_translate_daily_limit: int = 50

    # M22-3 (2026-07-05) — ``/api/v1/news/health`` returns an
    # ``ai_cleanup_24h`` block with the share of fetched articles
    # whose DeepSeek cleanup actually ran (``ai_cleanup_status =
    # 'cleaned'``). When ``cleaned_pct`` drops below this threshold
    # the dashboard flips the alert card on. Skipped (DeepSeek
    # unconfigured) rows are excluded from the denominator so an
    # entirely-off environment does not page anyone.
    news_ai_cleanup_alert_pct: float = 70.0

    # Xueqiu (雪球) cookie — raw "Cookie:" header value from a logged-in
    # browser session. Must include xq_a_token=...; u=...; device_id=...
    # The crawler is read-only and never attempts to log in.
    xueqiu_cookie: str = ""

    # SEC EDGAR — data.sec.gov requires a descriptive User-Agent per
    # https://www.sec.gov/os/accessing-edgar-data. Set this to a real
    # contact (name + email) so SEC can reach us if we misbehave;
    # their firewall rejects generic placeholders like
    # "admin@example.com". The default below is for local development
    # only — please override ``SEC_USER_AGENT`` in production / staging.
    sec_user_agent: str = "AlloyResearch research@alloy-research.local"

    # News crawler tuning
    xueqiu_per_minute: int = 30           # Per-instance rate limit
    xueqiu_batch_size: int = 50           # Symbols per scheduler tick
    xueqiu_posts_per_symbol: int = 20     # Posts per timeline page
    xueqiu_user_cache_ttl_days: int = 7   # How long to keep user profiles

    # WeChat RSS via wewe-rss (self-hosted). When ``wechat_rss_base_url``
    # is unset / unreachable the WeChat crawler is a silent no-op so the
    # rest of the news pipeline keeps running. ``wechat_rss_feed_id`` is
    # the comma-separated list of feed ids to subscribe to (one per
    # WeChat public account); see docs/dev-notes/20260704-wechat-rss-integration.md.
    wechat_rss_base_url: str = "http://localhost:4000"
    wechat_rss_feed_id: str = ""          # e.g. "MP_WXS_1234567890" (泽平宏观)
    wechat_rss_timeout_seconds: float = 10.0
    # AI marketing filter — set to False to disable the LLM re-classify
    # pass (the heuristic blocklist is always applied).
    wechat_marketing_filter_llm_enabled: bool = True

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

    # Deployment dashboard (Vercel-like admin page)
    github_token: str = ""          # GitHub personal access token for Actions API
    github_repo: str = ""           # e.g. "owner/repo-name"
    deploy_docker_socket: str = "/var/run/docker.sock"

    # CORS: comma-separated list of allowed origins. Empty falls back to a
    # localhost-only dev default (Vite + Next.js). For production set
    # CORS_ORIGINS to the exact frontend origin(s) — never use "*" with
    # credentials.
    cors_origins: str = ""

    # Constants
    api_v1_prefix: str = "/api/v1"
    project_name: str = "AlloyResearch"

    @property
    def cors_origins_list(self) -> list[str]:
        """Return parsed CORS origin list.

        Resolution order:
          1. CORS_ORIGINS env var (comma-separated, e.g.
             "https://app.example.com,https://admin.example.com").
             A bare "*" is accepted ONLY when APP_ENV=development, for
             local/test convenience. In production the wildcard is dropped
             silently.
          2. Development fallback — localhost Vite (5173) + Next.js (3000).
          3. Non-dev fallback — empty list (no cross-origin allowed).
        """
        if self.cors_origins.strip():
            origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        elif self.is_development:
            origins = ["http://localhost:5173", "http://localhost:3000"]
        else:
            origins = []

        # Wildcard is only legal in development.
        if "*" in origins and not self.is_development:
            origins = [o for o in origins if o != "*"]

        return origins

    @property
    def is_development(self) -> bool:
        """Return True if running in development mode."""
        return self.app_env.lower() == "development"


class AuthSettings(BaseSettings):
    """Authentication settings loaded from environment variables.

    Never commit plaintext passwords to source control. Set these via
    environment variables or a secrets manager in production.

    P0-7: the ``SECRET_KEY`` field has no safe hard-coded default. A
    bare ``your-secret-key-change-in-production`` placeholder would let
    a misconfigured deployment mint tokens with a publicly-known key,
    so we ship ``SECRET_KEY=""`` and refuse to construct the settings
    object if the resolved value is one of the well-known placeholders.
    """

    SECRET_KEY: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = ""

    model_config = SettingsConfigDict(
        env_prefix="AUTH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def _enforce_secret_key(cls, value: str) -> str:
        # Default to "development" when APP_ENV is unset so local
        # ``python -c "from app.main import app"`` smoke tests keep
        # working with the historical dev placeholder.
        app_env = os.environ.get("APP_ENV", "development")
        is_dev = app_env.lower() == "development"
        # In development we allow the empty default + the historical
        # dev placeholder so the project still boots locally without a
        # pre-configured ``.env``. In production (or any other env) the
        # placeholder is rejected outright.
        if value == _DEV_PLACEHOLDER_SECRET_KEY and is_dev:
            logger.warning(
                "[config] AUTH_SECRET_KEY is the development placeholder. "
                "This is allowed only because APP_ENV=development; production "
                "deployments MUST override AUTH_SECRET_KEY."
            )
            return value
        if value == _DEV_PLACEHOLDER_SECRET_KEY and not is_dev:
            raise RuntimeError(
                "AUTH_SECRET_KEY is the development placeholder but "
                f"APP_ENV={app_env!r}. Refusing to start. Set AUTH_SECRET_KEY "
                "to a high-entropy random string (>= 32 bytes)."
            )
        if not value:
            if is_dev:
                # Default ``""`` when AUTH_SECRET_KEY is unset + dev mode.
                # We synthesize the dev placeholder so JWT signing keeps
                # working through the rest of the app without manual env
                # tweaks. The warning still fires because the property
                # *value* is unsafe.
                logger.warning(
                    "[config] AUTH_SECRET_KEY is unset; using the development "
                    "placeholder. Set AUTH_SECRET_KEY to a high-entropy random "
                    "string before going to production."
                )
                return _DEV_PLACEHOLDER_SECRET_KEY
            raise RuntimeError(
                "AUTH_SECRET_KEY is unset. Refusing to start. Set "
                "AUTH_SECRET_KEY to a high-entropy random string (>= 32 bytes)."
            )
        # Any other known-bad value (e.g. "secret", "changeme") is
        # rejected in every environment.
        if value in (_KNOWN_BAD_SECRET_KEYS - {_DEV_PLACEHOLDER_SECRET_KEY}):
            raise RuntimeError(
                "AUTH_SECRET_KEY matches a well-known placeholder "
                f"({sorted(_KNOWN_BAD_SECRET_KEYS)!r}). Refusing to start "
                "with an insecure JWT signing key. Set AUTH_SECRET_KEY to a "
                "high-entropy random string (>= 32 bytes)."
            )
        if len(value) < 32:
            raise RuntimeError(
                "AUTH_SECRET_KEY is too short (< 32 chars). Use a high-entropy "
                "random string such as `python -c \"import secrets; print(secrets.token_urlsafe(48))\"`."
            )
        return value


# Pydantic v2 calls ``model_validator`` / ``field_validator`` AFTER the
# value has been sourced from env / .env. We use ``model_post_init__``
# on the constructed instance so the safety check runs after env merge
# but before any caller can read ``auth_settings.SECRET_KEY``.
_orig_init = AuthSettings.__init__


def _auth_settings_init(self, **data):  # type: ignore[no-untyped-def]
    _orig_init(self, **data)
    self.__dict__["SECRET_KEY"] = AuthSettings._enforce_secret_key(self.SECRET_KEY)


AuthSettings.__init__ = _auth_settings_init  # type: ignore[assignment]


auth_settings = AuthSettings()


class PushSettings(BaseSettings):
    """APNs & push notification configuration."""

    apns_key_path: str = ""       # Path to .p8 private key
    apns_key_id: str = ""         # Key ID from Apple Developer
    apns_team_id: str = ""        # Apple Developer Team ID
    apns_topic: str = ""          # App Bundle ID
    apns_use_sandbox: bool = True  # Use sandbox for dev, production for release

    model_config = SettingsConfigDict(
        env_prefix="APNS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


push_settings = PushSettings()


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    The instance is cached to avoid re-reading environment variables
    on every call.
    """
    return Settings()
