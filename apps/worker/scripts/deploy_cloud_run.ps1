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
    --set-env-vars "ENV=production,LOG_LEVEL=INFO,SENTRY_ENVIRONMENT=production,FEATURE_REAL_LLM=true,FEATURE_PAPER_EXECUTION=false,FEATURE_LIVE_TRADING=false,GCS_BUCKET_RAW=tessera-raw,LLM_MAX_DAILY_COST_USD=5.0,ALPACA_BASE_URL=https://paper-api.alpaca.markets,RELY_ON_IAM=true" `
    --set-secrets "DATABASE_URL=DATABASE_URL:latest,ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,ALPACA_API_KEY=ALPACA_API_KEY:latest,ALPACA_API_SECRET=ALPACA_API_SECRET:latest,FMP_API_KEY=FMP_API_KEY:latest,FRED_API_KEY=FRED_API_KEY:latest,NEWSAPI_API_KEY=NEWSAPI_API_KEY:latest,SENTRY_DSN=SENTRY_DSN:latest,WORKER_WEBHOOK_SECRET=WORKER_WEBHOOK_SECRET:latest,SEC_USER_AGENT=SEC_USER_AGENT:latest"
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
Write-Output "    Service URL: $URL"
Write-Output "    Health:      $URL/health  (will 403 - auth required, that's expected)"
Write-Output ""
Write-Output "Next: set WORKER_WEBHOOK_URL in Vercel to:  $URL/jobs/ingest-daily"
