"""Centralized configuration loaded from environment.

All secrets and runtime params live here. Imported once, reused everywhere.
Never read os.environ directly anywhere else in the codebase.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime config. Values come from env vars or .env (gitignored)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Environment ──
    env: str = Field("development", description="development | staging | production")
    log_level: str = Field("INFO")

    # ── Database ──
    database_url: str = Field(
        "postgresql://localhost:5432/tessera",
        description="Neon Postgres connection string. Format: postgresql://user:pass@host/db",
    )

    # ── LLM ──
    anthropic_api_key: str = Field("", description="Set at deploy time via Secret Manager")
    llm_model_screen: str = Field("claude-haiku-4-5")
    llm_model_thesis: str = Field("claude-sonnet-4-6")
    llm_model_review: str = Field("claude-opus-4-7")
    llm_max_daily_cost_usd: float = Field(20.0, description="Auto-pause batch if exceeded")

    # ── Brokerage ──
    alpaca_api_key: str = Field("")
    alpaca_api_secret: str = Field("")
    alpaca_base_url: str = Field("https://paper-api.alpaca.markets")

    # ── Market data ──
    fmp_api_key: str = Field("")
    fred_api_key: str = Field("")
    newsapi_api_key: str = Field("")

    # ── Object storage ──
    gcs_bucket_raw: str = Field("tessera-raw", description="GCS bucket for raw filings + LLM responses")

    # ── Feature flags ──
    feature_real_llm: bool = Field(False, description="Off → mock responses (dev). On → real Anthropic calls")
    feature_paper_execution: bool = Field(False)
    feature_live_trading: bool = Field(False, description="Never enable without explicit user OAuth + compliance review")

    # ── Observability ──
    sentry_dsn: str = Field("")


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
