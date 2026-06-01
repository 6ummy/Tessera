"""Sentry initialization — call once at process start.

Cost guard (Phase B): errors only, no performance traces, no profiling.
Free tier (5K errors/mo) is plenty for our scale; perf would burn quota fast.
"""

from __future__ import annotations

import sentry_sdk

from tessera_worker.config import get_settings


def init_sentry() -> bool:
    """Initialize Sentry if SENTRY_DSN is set. Returns True if initialized."""
    settings = get_settings()
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        # Cost guard — errors only. No perf traces, no profiling.
        traces_sample_rate=0.0,
        profiles_sample_rate=0.0,
        # Don't send PII (defaults False, but be explicit for a public OSS repo)
        send_default_pii=False,
        # Drop redundant breadcrumbs we don't need
        max_breadcrumbs=50,
    )
    return True
