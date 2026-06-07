# tessera-worker

Python batch workers for Tessera. Runs on Google Cloud Run (jobs + service).

## Layout

```
tessera_worker/
  config.py         Pydantic Settings — all env vars, single source
  db.py             SQLAlchemy engine + session scope
  logging.py        structlog JSON logging for Cloud Run
  main.py           FastAPI HTTP server (Vercel Cron triggers, /health)

  ingestors/        Phase A — pull from upstream sources into Neon
  features/         Price/momentum features + fundamentals quality features
                    (fcf_yield, PEG, EPS CAGR, debt/equity, margins)
  agents/           Phase B — persona LLM pipeline + chat
  risk/             Phase C — risk gateway + paper / live execution
  jobs/             One-shot Cloud Run Job entry points
```

## Run locally

```bash
# Install (one-time)
cd apps/worker
python -m venv .venv
source .venv/Scripts/activate  # Windows Git Bash

# tessera_worker depends on tessera_shared (Pydantic schemas).
# Install the shared package FIRST so pip can resolve the name dep.
pip install -e ../../packages/shared
pip install -e ".[dev]"

# Configure
cp .env.example .env
# edit .env with your Neon / Anthropic / Alpaca / etc.

# Boot the HTTP server
python -m tessera_worker.main
# → http://localhost:8080/health
```

## Run a one-shot job (Phase A+)

```bash
python -m tessera_worker.jobs.ingest_daily
python -m tessera_worker.jobs.ingest_daily --only features
python -m tessera_worker.jobs.persona_batch
```

`--only features` reads already-ingested Neon data (`ohlcv_1d` +
`fundamentals`) and upserts deterministic rows into `ticker_features`.
It rebuilds price/momentum history and writes latest fundamentals-derived
columns such as `fcf_yield`, `peg`, `eps_cagr_3y`, `debt_to_equity`,
`gross_margin`, `gross_margin_trend`, `market_cap_usd`, and
`operating_margin`.

## Tests

```bash
pytest                  # all
pytest tests/features/  # only feature builder property tests
```

## Deploy (Phase A end)

Built as a single container image. Cloud Run jobs invoke the module directly:

```bash
gcloud run jobs deploy tessera-ingest-daily \
  --source . \
  --command "python" \
  --args "-m,tessera_worker.jobs.ingest_daily" \
  --schedule "30 16 * * 1-5" \
  --region us-central1
```

(Schedule is 16:30 ET = ~21:30 UTC, weekdays only. Cron schedule may need tz adjustment.)
