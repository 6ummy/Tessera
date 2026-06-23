# Runbook — Cloud Run Jobs for the batch pipelines

Migrates the two long-running batches (daily ingest, weekly persona
batch) off the Cloud Run **Service** BackgroundTask path — which dies
when the instance is idle-reaped (case study CS-8) — onto Cloud Run
**Jobs**, triggered by Cloud Scheduler. The Service stays for the HTTP
surface (`/api/*`, chat); only the batch triggers move.

**Safe to do incrementally.** Deploying the Jobs and test-running them
changes nothing about the live path. The cutover (step 4) is the only
step that changes behavior, and it's reversible.

Prereqs: `gcloud auth login`, `gcloud config set project tessera-498200`.
All commands are PowerShell (this team's shell — CS-9).

---

## 1. Deploy the Jobs (~5 min)

```powershell
cd C:\Users\jshin\Documents\Project\PennyMaker
# reuse the image the Service deploy just built, or omit -ImageTag to build fresh
.\apps\worker\scripts\deploy_cloud_run_jobs.ps1
```

Creates/updates `tessera-ingest-daily` and `tessera-persona-batch`
(same image + env + secrets as the Service; command overridden to
`python -m tessera_worker.jobs.<name>`).

## 2. Test-run to completion (~10 min) — DO THIS before scheduling

```powershell
gcloud run jobs execute tessera-persona-batch --region us-east1 --wait
gcloud run jobs execute tessera-ingest-daily  --region us-east1 --wait
```

`--wait` blocks until the execution finishes and returns non-zero on
failure. A Job runs to completion regardless of HTTP lifecycle, so the
CS-8 mid-run death cannot happen. Verify rows landed (persona batch →
`analyst_reports`; ingest → fresh `ohlcv_1d` / features).

## 3. Cloud Scheduler triggers (~5 min, one-time)

Scheduler invokes a Job execution via the Run Admin API using the
worker SA with an OIDC token. Grant the SA permission to run jobs first:

```powershell
gcloud projects add-iam-policy-binding tessera-498200 `
  --member="serviceAccount:tessera-worker@tessera-498200.iam.gserviceaccount.com" `
  --role="roles/run.developer"

# Daily ingest — 21:30 UTC weekdays (was vercel.json "30 21 * * 1-5")
gcloud scheduler jobs create http tessera-ingest-daily-trigger `
  --location=us-east1 `
  --schedule="30 21 * * 1-5" `
  --time-zone="Etc/UTC" `
  --uri="https://us-east1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/tessera-498200/jobs/tessera-ingest-daily:run" `
  --http-method=POST `
  --oauth-service-account-email="tessera-worker@tessera-498200.iam.gserviceaccount.com"

# Weekly persona batch — 22:00 UTC Friday (was "0 22 * * 5")
gcloud scheduler jobs create http tessera-persona-batch-trigger `
  --location=us-east1 `
  --schedule="0 22 * * 5" `
  --time-zone="Etc/UTC" `
  --uri="https://us-east1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/tessera-498200/jobs/tessera-persona-batch:run" `
  --http-method=POST `
  --oauth-service-account-email="tessera-worker@tessera-498200.iam.gserviceaccount.com"
```

(`roles/run.developer` includes `run.jobs.run`. If you prefer least
privilege, a custom role with just `run.jobs.run` + `run.executions.get`
also works.)

## 4. Cutover — disable the Vercel crons (the behavior change)

Until now BOTH the Vercel cron (→ Service BackgroundTask) and the new
Scheduler (→ Job) would fire → double batch, double LLM spend. Remove
the Vercel crons so the Job is the only trigger:

- Edit `apps/web/vercel.json` → delete the two `crons` entries (PR).
  The cron *routes* (`/api/cron/daily`, `/api/cron/weekly`) can stay as
  manual-trigger fallbacks; they just won't be scheduled.
- Redeploy web (Vercel auto-deploys on merge to main).

**Order matters**: enable Scheduler (step 3) and remove Vercel crons
(step 4) in the same change window. If step 4 lands before step 3, a
night's batch is skipped (recoverable — run step 2 manually). If step 3
lands before step 4, one night double-runs (wasteful but harmless;
`report_id` idempotency means the paper engine won't double-execute).

## Rollback

Re-add the Vercel crons (revert the vercel.json PR) and pause the
Scheduler jobs:

```powershell
gcloud scheduler jobs pause tessera-persona-batch-trigger --location=us-east1
gcloud scheduler jobs pause tessera-ingest-daily-trigger  --location=us-east1
```

The Service `/jobs/*` endpoints are untouched throughout, so the old
path is always one revert away.

## Manual run (anytime, no Scheduler)

```powershell
gcloud run jobs execute tessera-persona-batch --region us-east1 --wait
```

This replaces the old "run it locally" fallback — it runs in the cloud
with prod secrets, to completion.

## Persona offloading — pause the weekly batch, keep data fresh

The weekly persona batch is the only expensive pipeline (Sonnet calls).
Because each pipeline has its OWN Scheduler trigger, you can suspend just
the persona theses — for cost, or while the web Service is offlined —
WITHOUT stopping the daily price/data ingest:

```powershell
gcloud scheduler jobs pause  tessera-persona-batch-trigger --location=us-east1   # stop weekly theses
gcloud scheduler jobs resume tessera-persona-batch-trigger --location=us-east1   # resume
gcloud scheduler jobs list --location=us-east1                                   # ENABLED / PAUSED
```

`tessera-ingest-daily-trigger` stays ENABLED, so OHLCV / features / paper
marks keep updating and the dashboard + chart stay live; only NEW persona
theses pause (existing books keep being marked nightly). Jobs are
independent of the Service, so this is unaffected by scaling the web
Service to zero — that's the point of the Jobs path over the old Vercel
cron → Service one. Resuming picks up the next scheduled Friday; to catch
up immediately, run the manual command above.
