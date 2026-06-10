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

    # ── Embeddings (Voyage AI — Anthropic-recommended) ──
    # Blank → embedding writes skipped, persona_memory falls back to
    # recency-only recall in fetch_memory_recall. Add a key when ready
    # for similarity-based recall. Cost: $0.02/1M tokens; the pilot's
    # ~30 reports/week × ~400 tokens/thesis ≈ $0.00024/month (free tier
    # covers indefinitely).
    voyage_api_key: str = Field("", description="Voyage AI key for thesis embeddings")
    voyage_model: str = Field("voyage-3.5-lite",
                              description="1024-dim; persona_memory.embedding migrated to match")

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
    sentry_dsn: str = Field("", description="Sentry DSN for the tessera-worker project. Blank → Sentry disabled.")
    sentry_environment: str = Field("local", description="Tag attached to events (local / staging / production)")

    # ── Inter-service auth ──
    # Shared secret between Vercel cron and this worker. Vercel sends
    # `Authorization: Bearer ${WORKER_WEBHOOK_SECRET}`; we reject any /jobs/*
    # request without it. Blank = auth disabled (local dev only).
    worker_webhook_secret: str = Field("", description="Bearer secret for /jobs/* endpoints")
    # When deployed behind `--no-allow-unauthenticated`, Cloud Run validates
    # the IAM identity token BEFORE the request reaches this app. In that
    # mode set RELY_ON_IAM=true to skip the app-level bearer check
    # entirely — IAM is the only authentication layer, and the bearer
    # secret is irrelevant. The Authorization header still arrives carrying
    # the Google-signed JWT but we don't verify it again (Cloud Run already
    # did). Default false so local dev + `--allow-unauthenticated` deploys
    # continue to enforce the bearer.
    rely_on_iam: bool = Field(False, description="Skip bearer check; trust Cloud Run IAM")

    # ── SEC EDGAR ──
    # SEC requires a contact-bearing User-Agent on every request; non-conformant
    # requests get 403. Format: "Tessera Pilot you@example.com".
    sec_user_agent: str = Field("", description="User-Agent header for SEC EDGAR")


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
