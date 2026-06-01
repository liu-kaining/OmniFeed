"""Configuration management for OmniFeed.

All environment variables are defined in config/omnifeed.env.example.
GitHub Secrets setup guide: config/README.md
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent.parent

# Load config in priority order (later files override earlier ones)
for _env_file in (_ROOT / "config" / "omnifeed.env", _ROOT / ".env"):
    if _env_file.exists():
        load_dotenv(_env_file)


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in ("true", "1", "yes")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


# =============================================================================
# Environment variable names (single source of truth)
# =============================================================================

class Env:
    """All supported environment variable names."""

    # ETL
    DRY_RUN = "DRY_RUN"
    ETL_DAYS_BACK = "ETL_DAYS_BACK"
    ETL_MAX_FEED_ITEMS = "ETL_MAX_FEED_ITEMS"

    # FMP
    FMP_API_KEY = "FMP_API_KEY"
    FMP_BASE_URL = "FMP_BASE_URL"
    FMP_V4_BASE_URL = "FMP_V4_BASE_URL"
    FMP_V3_BASE_URL = "FMP_V3_BASE_URL"
    FMP_INSIDER_LIMIT = "FMP_INSIDER_LIMIT"
    FMP_NEWS_LIMIT = "FMP_NEWS_LIMIT"

    # Quiver
    QUIVER_API_KEY = "QUIVER_API_KEY"

    # LLM
    LLM_MODE = "LLM_MODE"
    LLM_API_KEY = "LLM_API_KEY"
    LLM_BASE_URL = "LLM_BASE_URL"
    LLM_MODEL = "LLM_MODEL"
    LLM_CHUNK_SIZE = "LLM_CHUNK_SIZE"
    LLM_MAX_FAILURES = "LLM_MAX_FAILURES"

    # R2
    R2_ACCOUNT_ID = "R2_ACCOUNT_ID"
    R2_ACCESS_KEY_ID = "R2_ACCESS_KEY_ID"
    R2_SECRET_ACCESS_KEY = "R2_SECRET_ACCESS_KEY"
    R2_BUCKET_NAME = "R2_BUCKET_NAME"

    # Turnstile
    TURNSTILE_SITE_KEY = "TURNSTILE_SITE_KEY"
    TURNSTILE_SECRET_KEY = "TURNSTILE_SECRET_KEY"

    # Frontend (used by scripts/generate_frontend_config.py)
    OMNIFEED_API_BASE = "OMNIFEED_API_BASE"
    OMNIFEED_FEEDS_BASE = "OMNIFEED_FEEDS_BASE"

    # Cloudflare deploy (GitHub Actions only)
    CLOUDFLARE_API_TOKEN = "CLOUDFLARE_API_TOKEN"
    CLOUDFLARE_ACCOUNT_ID = "CLOUDFLARE_ACCOUNT_ID"

    # Worker (wrangler secrets)
    ALLOWED_ORIGIN = "ALLOWED_ORIGIN"


# =============================================================================
# Config dataclasses
# =============================================================================

@dataclass(frozen=True)
class ETLConfig:
    """ETL pipeline runtime settings."""
    dry_run: bool = field(default_factory=lambda: _env_bool(Env.DRY_RUN))
    days_back: int = field(default_factory=lambda: _env_int(Env.ETL_DAYS_BACK, 7))
    max_feed_items: int = field(default_factory=lambda: _env_int(Env.ETL_MAX_FEED_ITEMS, 500))


@dataclass(frozen=True)
class FMPConfig:
    """Financial Modeling Prep API configuration."""
    api_key: str = field(default_factory=lambda: os.getenv(Env.FMP_API_KEY, ""))
    base_url: str = field(
        default_factory=lambda: os.getenv(
            Env.FMP_BASE_URL, "https://financialmodelingprep.com/stable"
        )
    )
    v4_base_url: str = field(
        default_factory=lambda: os.getenv(
            Env.FMP_V4_BASE_URL, "https://financialmodelingprep.com/api/v4"
        )
    )
    v3_base_url: str = field(
        default_factory=lambda: os.getenv(
            Env.FMP_V3_BASE_URL, "https://financialmodelingprep.com/api/v3"
        )
    )
    insider_limit: int = field(default_factory=lambda: _env_int(Env.FMP_INSIDER_LIMIT, 100))
    news_limit: int = field(default_factory=lambda: _env_int(Env.FMP_NEWS_LIMIT, 100))

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError(f"{Env.FMP_API_KEY} environment variable is required")


@dataclass(frozen=True)
class QuiverConfig:
    """Quiver Quantitative API configuration (optional)."""
    api_key: str = field(default_factory=lambda: os.getenv(Env.QUIVER_API_KEY, ""))


@dataclass(frozen=True)
class LLMConfig:
    """LLM gateway configuration."""
    mode: Literal["SDK_MODE", "DIRECT_HTTP_MODE"] = field(
        default_factory=lambda: os.getenv(Env.LLM_MODE, "SDK_MODE")  # type: ignore
    )
    api_key: str = field(default_factory=lambda: os.getenv(Env.LLM_API_KEY, ""))
    base_url: str = field(
        default_factory=lambda: os.getenv(Env.LLM_BASE_URL, "https://api.deepseek.com/v1")
    )
    model: str = field(default_factory=lambda: os.getenv(Env.LLM_MODEL, "deepseek-chat"))
    chunk_size: int = field(default_factory=lambda: _env_int(Env.LLM_CHUNK_SIZE, 10))
    max_failures: int = field(default_factory=lambda: _env_int(Env.LLM_MAX_FAILURES, 3))

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError(f"{Env.LLM_API_KEY} environment variable is required")
        if self.mode not in ("SDK_MODE", "DIRECT_HTTP_MODE"):
            raise ValueError(f"{Env.LLM_MODE} must be SDK_MODE or DIRECT_HTTP_MODE")


@dataclass(frozen=True)
class R2Config:
    """Cloudflare R2 storage configuration."""
    account_id: str = field(default_factory=lambda: os.getenv(Env.R2_ACCOUNT_ID, ""))
    access_key_id: str = field(default_factory=lambda: os.getenv(Env.R2_ACCESS_KEY_ID, ""))
    secret_access_key: str = field(default_factory=lambda: os.getenv(Env.R2_SECRET_ACCESS_KEY, ""))
    bucket_name: str = field(
        default_factory=lambda: os.getenv(Env.R2_BUCKET_NAME, "omnifeed-bucket")
    )
    endpoint_url: str = ""

    def __post_init__(self) -> None:
        if not self.account_id:
            raise ValueError(f"{Env.R2_ACCOUNT_ID} environment variable is required")
        if not self.access_key_id:
            raise ValueError(f"{Env.R2_ACCESS_KEY_ID} environment variable is required")
        if not self.secret_access_key:
            raise ValueError(f"{Env.R2_SECRET_ACCESS_KEY} environment variable is required")
        object.__setattr__(
            self,
            "endpoint_url",
            f"https://{self.account_id}.r2.cloudflarestorage.com",
        )


@dataclass(frozen=True)
class TurnstileConfig:
    """Cloudflare Turnstile configuration."""
    secret_key: str = field(default_factory=lambda: os.getenv(Env.TURNSTILE_SECRET_KEY, ""))
    site_key: str = field(default_factory=lambda: os.getenv(Env.TURNSTILE_SITE_KEY, ""))


@dataclass(frozen=True)
class FrontendConfig:
    """Frontend runtime config (generated into frontend/config.js)."""
    api_base: str = field(default_factory=lambda: os.getenv(Env.OMNIFEED_API_BASE, "/api"))
    feeds_base: str = field(default_factory=lambda: os.getenv(Env.OMNIFEED_FEEDS_BASE, ""))
    turnstile_site_key: str = field(default_factory=lambda: os.getenv(Env.TURNSTILE_SITE_KEY, ""))


@dataclass(frozen=True)
class AppConfig:
    """Main application configuration — aggregates all sub-configs."""
    etl: ETLConfig = field(default_factory=ETLConfig)
    fmp: FMPConfig = field(default_factory=FMPConfig)
    quiver: QuiverConfig = field(default_factory=QuiverConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    r2: R2Config = field(default_factory=R2Config)
    turnstile: TurnstileConfig = field(default_factory=TurnstileConfig)
    frontend: FrontendConfig = field(default_factory=FrontendConfig)

    @property
    def dry_run(self) -> bool:
        return self.etl.dry_run


def load_config() -> AppConfig:
    """Load application configuration from environment."""
    return AppConfig()


def is_dry_run() -> bool:
    """Return True when ETL should skip R2 writes."""
    return _env_bool(Env.DRY_RUN)


# Default whitelist of high-volume US stocks (used when R2 whitelist is empty)
DEFAULT_TICKERS: list[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK.B",
    "UNH", "JNJ", "V", "PG", "JPM", "MA", "HD", "ABBV", "MRK", "PEP",
    "COST", "AVGO", "LLY", "KO", "WMT", "TMO", "CSCO", "MCD", "ABT",
    "CRM", "ACN", "DHR", "NKE", "ORCL", "TXN", "PM", "UPS", "QCOM",
    "NEE", "BMY", "INTC", "AMD", "PYPL", "GILD", "F", "GM", "BA",
    "PLTR", "SOFI", "COIN", "MARA", "RIOT",
]
