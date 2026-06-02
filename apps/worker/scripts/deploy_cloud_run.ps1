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
$WORKER_DIR = "C:\Users\jshin\Documents\Project\PennyMaker\apps\worker"

$TAG = (Get-Date -Format "yyyyMMdd-HHmmss")
$IMAGE_TAGGED = "${IMAGE}:${TAG}"

Write-Output "==> Building image $IMAGE_TAGGED via Cloud Build"
Set-Location $WORKER_DIR
& gcloud builds submit `
    --tag $IMAGE_TAGGED `
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
    --allow-unauthenticated `
    --cpu 1 `
    --memory 1Gi `
    --min-instances 0 `
    --max-instances 2 `
    --timeout 3600 `
    --set-env-vars "ENV=production,LOG_LEVEL=INFO,SENTRY_ENVIRONMENT=production,FEATURE_REAL_LLM=false,FEATURE_PAPER_EXECUTION=false,FEATURE_LIVE_TRADING=false,GCS_BUCKET_RAW=tessera-raw,LLM_MAX_DAILY_COST_USD=5.0,ALPACA_BASE_URL=https://paper-api.alpaca.markets" `
    --set-secrets "DATABASE_URL=DATABASE_URL:latest,ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,ALPACA_API_KEY=ALPACA_API_KEY:latest,ALPACA_API_SECRET=ALPACA_API_SECRET:latest,FMP_API_KEY=FMP_API_KEY:latest,FRED_API_KEY=FRED_API_KEY:latest,NEWSAPI_API_KEY=NEWSAPI_API_KEY:latest,SENTRY_DSN=SENTRY_DSN:latest,WORKER_WEBHOOK_SECRET=WORKER_WEBHOOK_SECRET:latest,SEC_USER_AGENT=SEC_USER_AGENT:latest"

if ($LASTEXITCODE -ne 0) { Write-Error "Cloud Run deploy failed"; exit 1 }

$URL = & gcloud run services describe $SERVICE --region $REGION --format="value(status.url)"
Write-Output ""
Write-Output "==> Deployed."
Write-Output "    Service URL: $URL"
Write-Output "    Health:      $URL/health  (will 403 - auth required, that's expected)"
Write-Output ""
Write-Output "Next: set WORKER_WEBHOOK_URL in Vercel to:  $URL/jobs/ingest-daily"
