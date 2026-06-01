"""Configuration management for OmniFeed.

This module handles loading configuration from environment variables
and .env files for all components of the system.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv


# Load .env file if it exists
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


@dataclass(frozen=True)
class FMPConfig:
    """Financial Modeling Prep API configuration."""
    api_key: str = field(default_factory=lambda: os.getenv("FMP_API_KEY", ""))
    base_url: str = "https://financialmodelingprep.com/api/v3"

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError("FMP_API_KEY environment variable is required")


@dataclass(frozen=True)
class LLMConfig:
    """LLM gateway configuration."""
    mode: Literal["SDK_MODE", "DIRECT_HTTP_MODE"] = field(
        default_factory=lambda: os.getenv("LLM_MODE", "SDK_MODE")  # type: ignore
    )
    api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    base_url: str = field(
        default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    )
    model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "deepseek-chat"))
    chunk_size: int = 10  # Number of events per LLM batch

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError("LLM_API_KEY environment variable is required")


@dataclass(frozen=True)
class R2Config:
    """Cloudflare R2 storage configuration."""
    account_id: str = field(default_factory=lambda: os.getenv("R2_ACCOUNT_ID", ""))
    access_key_id: str = field(default_factory=lambda: os.getenv("R2_ACCESS_KEY_ID", ""))
    secret_access_key: str = field(default_factory=lambda: os.getenv("R2_SECRET_ACCESS_KEY", ""))
    bucket_name: str = field(
        default_factory=lambda: os.getenv("R2_BUCKET_NAME", "omnifeed-bucket")
    )
    endpoint_url: str = ""

    def __post_init__(self) -> None:
        if not self.account_id:
            raise ValueError("R2_ACCOUNT_ID environment variable is required")
        object.__setattr__(
            self,
            "endpoint_url",
            f"https://{self.account_id}.r2.cloudflarestorage.com",
        )


@dataclass(frozen=True)
class TurnstileConfig:
    """Cloudflare Turnstile configuration for bot protection."""
    secret_key: str = field(default_factory=lambda: os.getenv("TURNSTILE_SECRET_KEY", ""))
    site_key: str = field(default_factory=lambda: os.getenv("TURNSTILE_SITE_KEY", ""))


@dataclass(frozen=True)
class AppConfig:
    """Main application configuration."""
    fmp: FMPConfig = field(default_factory=FMPConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    r2: R2Config = field(default_factory=R2Config)
    turnstile: TurnstileConfig = field(default_factory=TurnstileConfig)


def load_config() -> AppConfig:
    """Load application configuration from environment."""
    return AppConfig()


# Default whitelist of high-volume US stocks
DEFAULT_TICKERS: list[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK.B",
    "UNH", "JNJ", "V", "PG", "JPM", "MA", "HD", "ABBV", "MRK", "PEP",
    "COST", "AVGO", "LLY", "KO", "WMT", "TMO", "CSCO", "MCD", "ABT",
    "CRM", "ACN", "DHR", "NKE", "ORCL", "TXN", "PM", "UPS", "QCOM",
    "NEE", "BMY", "INTC", "AMD", "PYPL", "GILD", "F", "GM", "BA",
    "PLTR", "SOFI", "COIN", "MARA", "RIOT",
]
