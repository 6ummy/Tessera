# Vercel Cron — Tessera daily trigger

## What it does

Vercel pings `GET /api/cron/daily` on a schedule defined in
`apps/web/vercel.json`. The endpoint authenticates the request, then
fires a webhook to the deployed Cloud Run worker. The worker runs the
heavy ingestion + feature build (~30–90 seconds) and returns 202
immediately.

The endpoint itself never does the work — it must finish in <10 s
(Vercel Hobby function timeout).

## Schedule

```
30 21 * * 1-5
```
21:30 UTC, weekdays only (= 16:30 ET, after US market close).
Daylight-saving note: this fires 90 min after market close in winter,
30 min after in summer. Good enough — EOD data is final by 21:00 UTC
on both timezones.

## Required env vars (set in Vercel dashboard → Project → Environment)

| Var                     | Purpose |
| ----------------------- | ------- |
| `CRON_SECRET`           | Vercel sends this as `Authorization: Bearer …` on cron-triggered hits. Generate any 32+ char random string. |
| `WORKER_WEBHOOK_URL`    | URL of the Cloud Run service that runs the daily batch. Leave unset during Phase A (endpoint returns "noop" but still acks the cron). |
| `WORKER_WEBHOOK_SECRET` | Optional. If set, sent as `Authorization: Bearer …` to the worker, which should verify before doing work. |

## Manually testing the endpoint

Local dev (web app running on :3000):

```bash
# Set CRON_SECRET in apps/web/.env.local first
curl -sS -H "Authorization: Bearer $CRON_SECRET" http://localhost:3000/api/cron/daily | jq
```

Production (replace HOST):

```bash
curl -sS -H "Authorization: Bearer $CRON_SECRET" https://HOST/api/cron/daily | jq
```

## What the response means

```json
{ "ok": true, "triggeredAt": "...", "status": "noop", "reason": "..." }
```
Cron fired but worker URL not configured. Expected during Phase A.

```json
{ "ok": true, "triggeredAt": "...", "status": "queued", "workerStatus": 202 }
```
Worker accepted the job. It will run in the background.

```json
{ "ok": false, "status": "worker_unreachable", "error": "..." }
```
Worker didn't respond within 8s. Check Cloud Run logs.

## Local-machine alternative (no Cloud Run yet)

Until the worker is deployed, run the batch manually:

```bash
cd apps/worker
unset ANTHROPIC_API_KEY                              # Claude Code env only
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe \
    -m tessera_worker.jobs.ingest_daily
```

Or with selected steps:

```bash
python -m tessera_worker.jobs.ingest_daily --only ohlcv_equity features
python -m tessera_worker.jobs.ingest_daily --skip fundamentals
```
