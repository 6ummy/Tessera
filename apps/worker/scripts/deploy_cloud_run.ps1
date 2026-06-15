# Build worker image with Cloud Build, push to Artifact Registry,
# deploy to Cloud Run. Idempotent - run any time to ship a new revision.
#
# Prereqs (one-time): see Tessera/docs/runbooks/cloud-run-deploy.md
#   - gcloud auth login
#   - gcloud config set project tessera-498200
#   - APIs enabled, Artifact Registry repo "tessera" exists, service account
#     tessera-worker@tessera-498200.iam.gserviceaccount.com exists
#   - Secret Manager populated with the 9 secrets used in --set-secrets below

$ErrorActionPreference = "Continue"

$PROJECT  = "tessera-498200"
$REGION   = "us-east1"
$REPO     = "tessera"
$IMAGE    = "$REGION-docker.pkg.dev/$PROJECT/$REPO/worker"
$SERVICE  = "tessera-worker"
$SA       = "tessera-worker@$PROJECT.iam.gserviceaccount.com"
# Build context = REPO ROOT (not apps/worker/) because the Dockerfile needs
# to COPY both packages/shared/ and apps/worker/ — they're sibling dirs under
# the monorepo root. The Dockerfile path is given relative to that root.
$REPO_ROOT  = "C:\Users\jshin\Documents\Project\PennyMaker"
$DOCKERFILE = "apps/worker/Dockerfile"

$TAG = (Get-Date -Format "yyyyMMdd-HHmmss")
$IMAGE_TAGGED = "${IMAGE}:${TAG}"

Write-Output "==> Building image $IMAGE_TAGGED via Cloud Build"
Set-Location $REPO_ROOT
# cloudbuild.yaml at repo root passes -f apps/worker/Dockerfile to docker
# build, so the build context is the repo root and the Dockerfile can COPY
# both packages/shared/ and apps/worker/.
& gcloud builds submit `
    --config=cloudbuild.yaml `
    --substitutions="_IMAGE_TAG=${IMAGE_TAGGED}" `
    --project $PROJECT `
    .
if ($LASTEXITCODE -ne 0) { Write-Error "Cloud Build failed"; exit 1 }

Write-Output ""
Write-Output "==> Deploying $SERVICE to Cloud Run"
# no-cpu-throttling: legacy mitigation for the BackgroundTask batch path
# (ingest/persona_batch ran AFTER the 202 and got reaped when the instance
# idled — CS-8). The structural fix shipped 2026-06-13: those batches now
# run as Cloud Run JOBS (deploy_cloud_run_jobs.ps1 + docs/runbooks/
# cloud-run-jobs.md). This Service still serves the HTTP surface (/api/*,
# chat) and keeps the /jobs/* endpoints as a manual fallback; the flag
# stays harmless and cheap (scales to zero).
& gcloud run deploy $SERVICE `
    --image $IMAGE_TAGGED `
    --region $REGION `
    --platform managed `
    --service-account $SA `
    --no-allow-unauthenticated `
    --cpu 1 `
    --memory 1Gi `
    --min-instances 0 `
    --max-instances 2 `
    --timeout 3600 `
    --no-cpu-throttling `
    --set-env-vars "ENV=production,LOG_LEVEL=INFO,SENTRY_ENVIRONMENT=production,FEATURE_REAL_LLM=true,FEATURE_PAPER_EXECUTION=true,FEATURE_LIVE_TRADING=false,GCS_BUCKET_RAW=tessera-raw,LLM_MAX_DAILY_COST_USD=5.0,LLM_MAX_DAILY_COST_CHAT_USD=2.0,ALPACA_BASE_URL=https://paper-api.alpaca.markets,RELY_ON_IAM=true" `
    --set-secrets "DATABASE_URL=DATABASE_URL:latest,ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,ALPACA_API_KEY=ALPACA_API_KEY:latest,ALPACA_API_SECRET=ALPACA_API_SECRET:latest,FMP_API_KEY=FMP_API_KEY:latest,FRED_API_KEY=FRED_API_KEY:latest,NEWSAPI_API_KEY=NEWSAPI_API_KEY:latest,SENTRY_DSN=SENTRY_DSN:latest,WORKER_WEBHOOK_SECRET=WORKER_WEBHOOK_SECRET:latest,SEC_USER_AGENT=SEC_USER_AGENT:latest,VOYAGE_API_KEY=VOYAGE_API_KEY:latest"
# Optional: chat memory uses Voyage embeddings if VOYAGE_API_KEY is set.
# Create the secret once with:
#   gcloud secrets create VOYAGE_API_KEY --replication-policy=automatic --project tessera-498200
#   echo -n "pa-…" | gcloud secrets versions add VOYAGE_API_KEY --data-file=- --project tessera-498200
# Then add `,VOYAGE_API_KEY=VOYAGE_API_KEY:latest` to the --set-secrets line above.
# Without it, chat still works — `fetch_memory_recall` falls back to recency-only.

if ($LASTEXITCODE -ne 0) { Write-Error "Cloud Run deploy failed"; exit 1 }

$URL = & gcloud run services describe $SERVICE --region $REGION --format="value(status.url)"
Write-Output ""
Write-Output "==> Deployed."
Write-Output "    Service URL:  $URL"
Write-Output "    Health:       $URL/health  (will 403 - auth required, that's expected)"
Write-Output "    Image tag:    $TAG"
Write-Output "    Full image:   $IMAGE_TAGGED"
Write-Output ""
Write-Output "To deploy the SAME image to Cloud Run JOBS (reuses the build above):"
Write-Output "    .\apps\worker\scripts\deploy_cloud_run_jobs.ps1 -ImageTag `"$TAG`""
Write-Output ""
# WORKER_WEBHOOK_URL must be the BASE service URL (no /jobs/... path):
# gcp-auth.ts strips any path anyway, each Vercel route appends its own,
# and the IAM identity-token audience must match the bare service URL.
# Both URL styles Cloud Run prints (ffr7g3a76a-ue.a.run.app and
# <project-number>.<region>.run.app) point at the same service - if Vercel
# already holds one of them, no change is needed after a redeploy.
Write-Output "Vercel WORKER_WEBHOOK_URL should be the BASE URL (no path):  $URL"
Write-Output "(if Vercel already has a working base URL for this service, leave it)"
