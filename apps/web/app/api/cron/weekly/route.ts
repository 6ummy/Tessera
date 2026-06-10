/**
 * Vercel Cron trigger for the weekly persona thesis batch.
 *
 * Schedule: 22:00 UTC every Friday (~17:00 ET, after US close + 30-min
 * grace for the daily ingest to finish at 21:30 UTC). See apps/web/vercel.json.
 *
 * Why weekly, not daily — 2026-06-04 decision:
 *   Daily would cost ~4 personas × 30 tickers × $0.02 × 5d/wk ≈ $72/mo.
 *   Weekly costs ~$5–7/mo, sufficient for the paper-pilot stage.
 *   Daily can be re-enabled when Phase F live mode launches.
 *
 * Auth: Vercel sends `Authorization: Bearer ${CRON_SECRET}` on cron-
 * triggered invocations. We reject anything without it.
 *
 * What it does: POST to the Cloud Run worker's /jobs/persona-batch endpoint.
 * The worker returns 202 immediately and runs the batch + canary in the
 * background (~5–10 min).
 */

import { NextResponse } from "next/server";
import { buildWorkerAuthHeader, workerBaseUrl } from "@/lib/gcp-auth";

export const runtime = "edge";
export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const auth = req.headers.get("authorization") ?? "";
  const cronSecret = process.env.CRON_SECRET;
  if (!cronSecret) {
    return NextResponse.json(
      { ok: false, error: "CRON_SECRET not set on the server" },
      { status: 500 },
    );
  }
  if (auth !== `Bearer ${cronSecret}`) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }

  const base = workerBaseUrl();
  const triggeredAt = new Date().toISOString();

  if (!base) {
    return NextResponse.json({
      ok: true,
      triggeredAt,
      status: "noop",
      reason:
        "WORKER_WEBHOOK_URL not configured — weekly persona batch must be run manually",
    });
  }

  // The weekly batch lives at /jobs/persona-batch (not /jobs/ingest-daily).
  const personaBatchUrl = `${base}/jobs/persona-batch`;
  const authHeader = await buildWorkerAuthHeader(base);

  try {
    const r = await fetch(personaBatchUrl, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...authHeader,
      },
      body: JSON.stringify({ triggeredAt, source: "vercel-cron-weekly" }),
      signal: AbortSignal.timeout(8_000),
    });
    return NextResponse.json({
      ok: r.ok,
      triggeredAt,
      status: "queued",
      workerStatus: r.status,
      target: personaBatchUrl,
    });
  } catch (err) {
    return NextResponse.json({
      ok: false,
      triggeredAt,
      status: "worker_unreachable",
      error: err instanceof Error ? err.message : String(err),
    }, { status: 502 });
  }
}

export const POST = GET;
