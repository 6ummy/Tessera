"""FastAPI server entry point for HTTP-triggered jobs.

Cloud Run can invoke endpoints here via Cloud Scheduler or Vercel Cron webhooks.
For long-running batch (>60s), prefer Cloud Run Jobs invoked directly:
    python -m tessera_worker.jobs.<name>
"""

from __future__ import annotations

import sentry_sdk
from fastapi import FastAPI

from tessera_worker.config import get_settings
from tessera_worker.logging import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)

_settings = get_settings()
if _settings.sentry_dsn:
    sentry_sdk.init(
        dsn=_settings.sentry_dsn,
        environment=_settings.env,
        traces_sample_rate=0.1,
    )

app = FastAPI(title="Tessera Worker", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "env": _settings.env}


@app.post("/jobs/ingest-daily")
async def trigger_ingest_daily() -> dict[str, str]:
    """Trigger the daily ingestion pipeline. Vercel Cron calls this at 16:30 ET."""
    # TODO(Phase A, Week 1): wire to tessera_worker.jobs.ingest_daily.run()
    log.info("ingest_daily.triggered")
    return {"status": "queued", "job": "ingest_daily"}


@app.post("/jobs/persona-batch")
async def trigger_persona_batch() -> dict[str, str]:
    """Trigger the persona thesis batch after ingestion completes."""
    # TODO(Phase B, Week 2): wire to tessera_worker.jobs.persona_batch.run()
    log.info("persona_batch.triggered")
    return {"status": "queued", "job": "persona_batch"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("tessera_worker.main:app", host="0.0.0.0", port=8080, reload=False)
