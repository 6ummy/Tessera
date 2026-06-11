# Runbook — Grafana cost dashboard + Voyage embeddings on prod

Operator console steps for the two Phase C observability items
(improvement plan Step 3-⑤). Everything repo-side is already in place;
this is the ~20 minutes of console work only the operator can do.

---

## 1. Grafana Cloud — LLM cost dashboard (~15 min)

Source of truth is the `llm_call_log` table in Neon — every Anthropic
call (thesis, construction, chat) logs cost/tokens/latency there. The
dashboard JSON lives at **`docs/grafana/llm-cost-dashboard.json`**.

### 1-1. Create a read-only DB role (Neon SQL editor)

Don't hand Grafana the owner `DATABASE_URL`. One-time:

```sql
CREATE ROLE grafana_ro WITH LOGIN PASSWORD '<generate-a-long-password>';
GRANT CONNECT ON DATABASE neondb TO grafana_ro;        -- adjust db name
GRANT USAGE ON SCHEMA public TO grafana_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana_ro;
```

### 1-2. Grafana Cloud setup

1. https://grafana.com → free tier sign-up (1 user is plenty).
2. **Connections → Data sources → Add → PostgreSQL**:
   - Host: the Neon host from `DATABASE_URL` (`...neon.tech:5432`)
   - Database / User: from step 1-1 (`grafana_ro`)
   - TLS/SSL Mode: `require`
3. **Dashboards → New → Import** → upload
   `docs/grafana/llm-cost-dashboard.json` → map the `DS_NEON` input to
   the datasource from step 2.

Panels: spend today vs $5 cap · chat pool vs $2 cap · month-to-date ·
failed calls (7d) · daily cost stacked by stage (30d) · cost by persona
(7d) · calls/tokens/latency table.

### 1-3. Alerts (optional but recommended — Plan §9 thresholds)

Grafana Alerting → New alert rule on the "Spend today" query:
- ≥ $5/day → notify (info), ≥ $10 → warning, ≥ $20 → page.
Contact point: email (free) or Slack webhook if/when the team has one.
The in-app hard pause (`check_daily_budget`) remains the safety net —
these alerts just fire earlier.

> Not in this dashboard: `cross_validated()` disagreement tracking. That
> signal lives in Cloud Run structured logs, not the DB — needs a
> log-based metric (GCP Logging → metric → Grafana GCP datasource).
> Tracked separately in Plan §5.

---

## 2. Voyage embeddings on prod (~5 min)

Without `VOYAGE_API_KEY` on Cloud Run, `persona_memory` recall falls
back to recency. `persona_memory` now has enough rows for similarity
recall to beat recency (Plan §5 Week 5 item).

```powershell
# 1. Get a key at https://dash.voyageai.com (free tier: 200M tokens/mo —
#    pilot usage is ~500K/mo, $0 indefinitely)

# 2. Create the secret (one-time)
gcloud secrets create VOYAGE_API_KEY --replication-policy=automatic --project tessera-498200
echo -n "pa-XXXX..." | gcloud secrets versions add VOYAGE_API_KEY --data-file=- --project tessera-498200

# 3. Grant the worker SA access (one-time)
gcloud secrets add-iam-policy-binding VOYAGE_API_KEY --project tessera-498200 `
  --member="serviceAccount:tessera-worker@tessera-498200.iam.gserviceaccount.com" `
  --role="roles/secretmanager.secretAccessor"

# 4. Append to the --set-secrets line in apps/worker/scripts/deploy_cloud_run.ps1:
#      ,VOYAGE_API_KEY=VOYAGE_API_KEY:latest
#    (commit via PR) then redeploy:
.\apps\worker\scripts\deploy_cloud_run.ps1
```

**Verify**: open a chat with any persona about a ticker they've covered
before and check worker logs for a `sim=0.xx` recall tag (similarity
path) instead of `recency`. Compare whether the surfaced past theses are
more topical — that was the acceptance test written in Plan §5 Week 5.
