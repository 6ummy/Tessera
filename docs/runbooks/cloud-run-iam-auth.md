# Cloud Run IAM auth rollout

Status: rolling out 2026-06-09 via PR `feat/infra/cloud-run-iam-auth`.
Owner: 정우 (@6ummy).

## Why

The pre-rollout setup runs the worker as `--allow-unauthenticated` with
`WORKER_WEBHOOK_SECRET` as the only guard. That bearer is shared between
Vercel and Cloud Run, lives in two places, and was leaked into a debug
session on 2026-06-09 (rotated same day). The replacement:

- Cloud Run flips to `--no-allow-unauthenticated`. The only callers it
  accepts are GCP principals with `roles/run.invoker`.
- A new dedicated service account `tessera-vercel` holds that role and
  nothing else.
- Vercel's Edge proxies mint a per-call Google identity token using the
  SA's private key (via `jose` — Web-Crypto-native, Edge-compatible).
- The legacy bearer secret stays plumbed as a **fallback** so a partial
  rollout (Cloud Run flipped, Vercel env not yet populated, or vice
  versa) stays unbroken.

## One-time setup

Run these as a project owner (정우 or 준원). All commands assume
`gcloud config set project tessera-498200`.

### 1. Create the Vercel service account

```powershell
gcloud iam service-accounts create tessera-vercel `
    --display-name="Tessera Vercel Edge proxies" `
    --description="Mints identity tokens to invoke tessera-worker Cloud Run service" `
    --project=tessera-498200
```

### 2. Grant `roles/run.invoker` scoped to the worker service

Note: scoped at the service level, NOT project-level. Vercel SA can
only call `tessera-worker`, nothing else in the project.

```powershell
gcloud run services add-iam-policy-binding tessera-worker `
    --region=us-east1 `
    --member="serviceAccount:tessera-vercel@tessera-498200.iam.gserviceaccount.com" `
    --role="roles/run.invoker" `
    --project=tessera-498200
```

### 3. Generate + retrieve a JSON key

```powershell
gcloud iam service-accounts keys create tessera-vercel-key.json `
    --iam-account=tessera-vercel@tessera-498200.iam.gserviceaccount.com `
    --project=tessera-498200
```

This drops a `tessera-vercel-key.json` file into the current dir. DO NOT
commit it. Treat it like any other secret.

### 4. Base64-encode for Vercel env

Vercel's env editor doesn't handle multi-line PEM blocks cleanly, so we
wrap the whole JSON in base64:

```powershell
$json = Get-Content tessera-vercel-key.json -Raw
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))
$b64 | Set-Clipboard
```

The base64 string is now on the clipboard.

### 5. Set the Vercel env var

Vercel dashboard → project → Settings → Environment Variables → add:

- Name: `GCP_SA_KEY_B64`
- Value: (paste from clipboard)
- Environments: Production + Preview + Development

### 6. Redeploy Vercel

Trigger a Vercel redeploy so the new env var takes effect. The Edge
proxies will now mint identity tokens; legacy bearer is still tried
second so nothing breaks if the SA key is misformatted.

### 7. Flip the worker

```powershell
& C:\Users\jshin\Documents\Project\PennyMaker\apps\worker\scripts\deploy_cloud_run.ps1
```

The deploy script now uses `--no-allow-unauthenticated`. After it
finishes, the worker rejects unauthenticated calls with 403.

### 8. Sanity-check from both ends

**From outside (must fail):**
```powershell
curl https://tessera-worker-ffr7g3a76a-ue.a.run.app/health
# → 403 Forbidden  (good — unauthenticated)
```

**From the IAM identity (must succeed):**
```powershell
$token = gcloud auth print-identity-token `
    --impersonate-service-account=tessera-vercel@tessera-498200.iam.gserviceaccount.com `
    --audiences=https://tessera-worker-ffr7g3a76a-ue.a.run.app
curl https://tessera-worker-ffr7g3a76a-ue.a.run.app/health `
    -H "Authorization: Bearer $token"
# → 200 OK  (good — IAM token accepted)
```

**Vercel-served route (must succeed):**
```powershell
Invoke-RestMethod "https://<your-vercel-domain>/api/features/V?nocache=$(Get-Random)"
# → JSON with `features.fcf_yield` populated  (good — proxy minted token)
```

### 9. Delete the local key file

```powershell
Remove-Item tessera-vercel-key.json -Force
```

Cloud Run keeps no record of the key; Vercel holds the only copy.

## Rollback

If anything breaks, the fastest revert is to flip the worker back to
`--allow-unauthenticated` while keeping Vercel's IAM path intact. Both
auth modes coexist — the worker just accepts unauthenticated calls
again, and the IAM tokens stay valid:

```powershell
gcloud run services update tessera-worker `
    --region=us-east1 `
    --allow-unauthenticated `
    --project=tessera-498200
```

Or change the line in `deploy_cloud_run.ps1` from
`--no-allow-unauthenticated` back to `--allow-unauthenticated` and
redeploy.

## Key rotation

SA keys don't auto-expire. Rotate every 90 days:

```powershell
# 1. Mint a new key
gcloud iam service-accounts keys create new-key.json `
    --iam-account=tessera-vercel@tessera-498200.iam.gserviceaccount.com

# 2. Update Vercel env GCP_SA_KEY_B64 (steps 4–5 above), redeploy

# 3. After confirming Vercel works on the new key, delete the old one
gcloud iam service-accounts keys list `
    --iam-account=tessera-vercel@tessera-498200.iam.gserviceaccount.com
gcloud iam service-accounts keys delete <OLD_KEY_ID> `
    --iam-account=tessera-vercel@tessera-498200.iam.gserviceaccount.com
```

Set a calendar reminder. If a key is suspected leaked, rotate
immediately + audit Cloud Run access logs for unexpected callers.

## Cleanup of the legacy bearer

After 1-2 weeks of stable IAM auth, remove the bearer fallback:

1. Delete `WORKER_WEBHOOK_SECRET` Vercel env var
2. Delete `WORKER_WEBHOOK_SECRET` from Cloud Run `--set-secrets`
3. Delete the secret from GCP Secret Manager
4. Strip the bearer fallback branch from `apps/web/lib/gcp-auth.ts`

Not part of this PR — let the IAM path bake first.
