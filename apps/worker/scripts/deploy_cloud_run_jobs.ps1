# Create/update the Cloud Run JOBS for the long-running batches.
#
# Why Jobs and not the Service's /jobs/* BackgroundTasks: the Service path
# runs the batch AFTER returning 202, so an idle-reaped instance kills it
# mid-run — case study CS-8 (2026-06-12: the weekly batch died at 23:02
# with cathie half-done). Cloud Run Jobs run a container to completion
# regardless of request lifecycle; that's what batch is for.
#
# This reuses the SAME image as the Service (apps/worker/Dockerfile already
# ships the CLI modules) — we only override the container command. Run
# deploy_cloud_run.ps1 first (or pass -ImageTag) so the image exists.
#
# After this script: create the Cloud Scheduler triggers + grant IAM per
# docs/runbooks/cloud-run-jobs.md, then disable the Vercel crons. Until
# that cutover the existing Vercel → Service path still runs (no double-run
# until Scheduler is enabled), so this script is safe to run anytime.

param(
    # Reuse an already-built image. Accepts either form:
    #   - bare tag suffix:  "20260615-002125"  (what deploy_cloud_run.ps1
    #                       prints; the most common case)
    #   - full reference:   "us-east1-docker.pkg.dev/.../worker:20260615-002125"
    # The script normalizes both into the correct `gcloud run jobs deploy
    # --image` argument. Default empty: build a fresh image via Cloud
    # Build, push, and deploy with that.
    #
    # Pre-2026-06-15 footgun (since fixed here): the script passed
    # $ImageTag through to --image verbatim. A bare tag like
    # "20260615-002125" got interpreted by gcloud as a Docker Hub library
    # image, producing the cryptic "Image 'mirror.gcr.io/library/<tag>'
    # not found" error. Both forms now Just Work.
    [string]$ImageTag = ""
)

$ErrorActionPreference = "Continue"

$PROJECT = "tessera-498200"
$REGION  = "us-east1"
$REPO    = "tessera"
$IMAGE   = "$REGION-docker.pkg.dev/$PROJECT/$REPO/worker"
$SA      = "tessera-worker@$PROJECT.iam.gserviceaccount.com"
$REPO_ROOT = "C:\Users\jshin\Documents\Project\PennyMaker"

# Jobs share the Service's env + secrets exactly (same code, same config).
# RESEND_API_KEY must exist in Secret Manager before deploying (runbook
# firebase-auth.md §6) or this fails on the missing secret. FEATURE_FCM_PUSH
# needs the worker SA granted firebasecloudmessaging on tessera-641a5.
# EMAIL_FROM defaults to the resend.dev sandbox (owner-only); override via
# --update-env-vars once a domain is verified.
# Notification email sender — change to a verified-domain address after
# Resend domain verification (sandbox delivers only to the Resend owner).
# Must match EMAIL_FROM on Vercel + the Service deploy script.
$EMAIL_FROM = "Convt <alerts@convt.xyz>"
$ENV_VARS = "ENV=production,LOG_LEVEL=INFO,SENTRY_ENVIRONMENT=production,FEATURE_REAL_LLM=true,FEATURE_PAPER_EXECUTION=true,FEATURE_LIVE_TRADING=false,FEATURE_FCM_PUSH=false,FEATURE_EMAIL_NOTIFY=true,GCS_BUCKET_RAW=tessera-raw,LLM_MAX_DAILY_COST_USD=5.0,LLM_MAX_DAILY_COST_CHAT_USD=2.0,ALPACA_BASE_URL=https://paper-api.alpaca.markets,EMAIL_FROM=$EMAIL_FROM"
$SECRETS = "DATABASE_URL=DATABASE_URL:latest,ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,ALPACA_API_KEY=ALPACA_API_KEY:latest,ALPACA_API_SECRET=ALPACA_API_SECRET:latest,FMP_API_KEY=FMP_API_KEY:latest,FRED_API_KEY=FRED_API_KEY:latest,NEWSAPI_API_KEY=NEWSAPI_API_KEY:latest,SENTRY_DSN=SENTRY_DSN:latest,SEC_USER_AGENT=SEC_USER_AGENT:latest,VOYAGE_API_KEY=VOYAGE_API_KEY:latest,RESEND_API_KEY=RESEND_API_KEY:latest,UNSUBSCRIBE_SECRET=UNSUBSCRIBE_SECRET:latest"
# Note: no WORKER_WEBHOOK_SECRET / RELY_ON_IAM — Jobs have no HTTP surface,
# so the inter-service auth knobs are irrelevant here.

# Resolve $ImageTag into a full image reference $imageRef.
if (-not $ImageTag) {
    # No arg → build a fresh image. Tag is today's UTC timestamp; the
    # Cloud Build substitution variable receives the FULL reference so
    # both the build push and the deploy below point at the same digest.
    $TAG = (Get-Date -Format "yyyyMMdd-HHmmss")
    $imageRef = "${IMAGE}:${TAG}"
    Write-Output "==> Building image $imageRef via Cloud Build"
    Set-Location $REPO_ROOT
    & gcloud builds submit --config=cloudbuild.yaml --substitutions="_IMAGE_TAG=${imageRef}" --project $PROJECT .
    if ($LASTEXITCODE -ne 0) { Write-Error "Cloud Build failed"; exit 1 }
} elseif ($ImageTag -match "/") {
    # Full reference passed (contains a path separator) → use as-is.
    $imageRef = $ImageTag
    Write-Output "==> Reusing already-built image $imageRef (full reference)"
} else {
    # Bare tag passed (e.g. "20260615-002125") → prepend the Artifact
    # Registry path. This is the friendly path and matches the form
    # deploy_cloud_run.ps1 prints when it finishes.
    $imageRef = "${IMAGE}:${ImageTag}"
    Write-Output "==> Reusing already-built image $imageRef (tag: $ImageTag)"
}

# Each Job overrides the container command to run a module CLI to
# completion. --task-timeout caps a stuck run; --max-retries 0 because the
# batches are idempotent at the step level but NOT at the cost level (a
# blind retry would re-pay LLM calls) — we'd rather fail and alert.
foreach ($job in @(
    @{ Name = "tessera-ingest-daily";  Module = "tessera_worker.jobs.ingest_daily";  Timeout = "1800s" },
    @{ Name = "tessera-persona-batch"; Module = "tessera_worker.jobs.persona_batch"; Timeout = "1800s" }
)) {
    Write-Output ""
    Write-Output "==> Deploying Job $($job.Name)  →  python -m $($job.Module)"
    & gcloud run jobs deploy $job.Name `
        --image $imageRef `
        --region $REGION `
        --service-account $SA `
        --cpu 1 `
        --memory 1Gi `
        --task-timeout $job.Timeout `
        --max-retries 0 `
        --command python `
        --args="-m,$($job.Module)" `
        --set-env-vars $ENV_VARS `
        --set-secrets $SECRETS
    if ($LASTEXITCODE -ne 0) { Write-Error "Job deploy failed: $($job.Name)"; exit 1 }
}

Write-Output ""
Write-Output "==> Jobs deployed. Verify each runs to completion BEFORE wiring schedulers:"
Write-Output "    gcloud run jobs execute tessera-persona-batch --region $REGION --wait"
Write-Output "    gcloud run jobs execute tessera-ingest-daily  --region $REGION --wait"
Write-Output ""
Write-Output "Then follow docs/runbooks/cloud-run-jobs.md to add Cloud Scheduler"
Write-Output "triggers and disable the Vercel crons (avoid double-runs)."
