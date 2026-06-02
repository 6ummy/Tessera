"""FastAPI server entry point for HTTP-triggered jobs.

Cloud Run can invoke endpoints here via Cloud Scheduler or Vercel Cron webhooks.
For long-running batch (>60s), prefer Cloud Run Jobs invoked directly:
    python -m tessera_worker.jobs.<name>

Auth model:
  - /health is public (Cloud Run liveness probe + uptime checks)
  - /jobs/*  requires `Authorization: Bearer ${WORKER_WEBHOOK_SECRET}`
    which Vercel's cron route forwards (see apps/web/app/api/cron/daily/route.ts).
    Cloud Run is deployed --allow-unauthenticated, so this bearer is the only
    thing between the public internet and our jobs.
"""

from __future__ import annotations

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, status

from tessera_worker.config import get_settings
from tessera_worker.logging import configure_logging, get_logger
from tessera_worker.observability import init_sentry

configure_logging()
log = get_logger(__name__)

_settings = get_settings()
init_sentry()

app = FastAPI(title="Tessera Worker", version="0.1.0")


def _require_webhook_auth(authorization: str | None) -> None:
    """Reject /jobs/* requests without the shared bearer secret.

    Blank secret on the worker = auth disabled (local dev only). Production
    deploy always sets WORKER_WEBHOOK_SECRET via Secret Manager.
    """
    expected = _settings.worker_webhook_secret
    if not expected:
        # No secret configured -> open mode for local dev. Cloud Run always has one.
        return
    if authorization != f"Bearer {expected}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="bad or missing bearer",
        )


@app.get("/health")
async def health() -> dict[str, str]:
    """Public liveness probe."""
    return {"status": "ok", "env": _settings.env}


@app.post("/jobs/ingest-daily")
async def trigger_ingest_daily(
    background: BackgroundTasks,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    """Trigger the daily ingestion pipeline. Vercel Cron calls this at 16:30 ET.

    Runs in the background so we can return 202 immediately (Vercel cron has
    a short fetch timeout, and the real ingest takes ~7 minutes).
    """
    _require_webhook_auth(authorization)
    # Lazy import: the jobs module pulls in pandas/sqlalchemy/etc., and we don't
    # want that cost on every cold start of /health.
    from tessera_worker.jobs.ingest_daily import run as run_ingest

    def _job() -> None:
        try:
            results = run_ingest()
            log.info("ingest_daily.bg_done",
                     passed=sum(r.ok for r in results),
                     failed=sum(not r.ok for r in results))
        except Exception:
            log.exception("ingest_daily.bg_failed")
            raise  # let Sentry capture

    background.add_task(_job)
    log.info("ingest_daily.queued")
    return {"status": "queued", "job": "ingest_daily"}


@app.post("/jobs/persona-batch")
async def trigger_persona_batch(
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    """Trigger the persona thesis batch after ingestion completes."""
    _require_webhook_auth(authorization)
    # TODO(Phase B, Week 2): wire to tessera_worker.jobs.persona_batch.run()
    log.info("persona_batch.triggered")
    return {"status": "queued", "job": "persona_batch"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("tessera_worker.main:app", host="0.0.0.0", port=8080, reload=False)
