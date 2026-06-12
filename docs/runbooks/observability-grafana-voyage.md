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

### 1-2b. Sentry alert — paper engine error → page within 5 min (~3 min setup)

The worker now explicitly captures paper-engine failures to Sentry
(`capture_exception` on a persona ledger failure, `capture_message` when
a held position can't be priced — both were previously swallowed by the
per-persona isolation and never reached Sentry). One-time console step
to turn captures into a page:

1. sentry.io → **tessera-worker** project → **Alerts → Create Alert →
   Issues**.
2. Condition: "A new issue is created" OR "an issue changes state from
   resolved to unresolved"; filter `message:paper_engine` (or leave
   unfiltered — the project is errors-only and low-volume).
3. Action: notify your email immediately. Action interval: 5 minutes.
4. Name: `paper-engine-page`.

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

**Verify** (corrected 2026-06-12 — the original instruction said "open a
chat", which can never show the tag): memory recall lives in the **thesis
prompt assembly** (`prompt_assembler.fetch_memory_recall`), NOT in chat —
`agents/chat.py` doesn't call recall at all (pgvector chat memory is
Phase D scope). So the `sim=0.xx` tag appears in the **weekly persona
batch** logs (Fri 22:00 UTC), where each research prompt recalls similar
past theses from `persona_memory`:

```powershell
gcloud logging read "resource.labels.service_name=tessera-worker AND textPayload:sim=" --freshness=2d --limit 5
# similarity path firing → lines tagged sim=0.xx
# key missing/unreachable → lines tagged recency (fallback)
```

Note: only `persona_memory` rows with a non-NULL embedding are
similarity-searchable. Rows written while the key was absent stay
recency-only; ~100 rows were already embedded from local runs as of
2026-06-12, and every new batch embeds its own rows going forward.
