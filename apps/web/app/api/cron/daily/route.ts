/**
 * Vercel Cron trigger for the daily ingestion + feature build.
 *
 * Schedule: 21:30 UTC, weekdays only (≈ 16:30 ET, after US market close).
 * See apps/web/vercel.json for the cron declaration.
 *
 * Auth: Vercel sends `Authorization: Bearer ${CRON_SECRET}` on cron-triggered
 * invocations when CRON_SECRET is configured in project env. We reject any
 * request that doesn't carry that secret — prevents external/manual hits.
 *
 * What it does:
 *   - If WORKER_WEBHOOK_URL is set: POST to the deployed Cloud Run worker.
 *     The worker runs the heavy job asynchronously and returns 202.
 *   - If WORKER_WEBHOOK_URL is NOT set: return 200 with a noop payload so
 *     the cron is alive but acknowledges nothing happened (Phase A pre-deploy).
 *
 * This endpoint MUST stay fast — Vercel Hobby has a 10s function timeout.
 * Heavy work always lives behind the webhook (Cloud Run, 60-min jobs).
 */

import { NextResponse } from "next/server";
import { buildWorkerAuthHeader, workerBaseUrl } from "@/lib/gcp-auth";

export const runtime = "edge"; // tiny payload, no Node APIs needed
export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const auth = req.headers.get("authorization") ?? "";
  const cronSecret = process.env.CRON_SECRET;
  if (!cronSecret) {
    // Mis-configured deploy: refuse rather than running an unauthenticated trigger
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
    // Phase A: worker not deployed yet. Acknowledge the cron without doing work.
    return NextResponse.json({
      ok: true,
      triggeredAt,
      status: "noop",
      reason: "WORKER_WEBHOOK_URL not configured — daily batch must be run manually",
    });
  }

  // The original WORKER_WEBHOOK_URL may have been set with a trailing
  // /jobs/ingest-daily for historical reasons; workerBaseUrl() strips
  // that, so re-append explicitly here.
  const target = `${base}/jobs/ingest-daily`;
  const authHeader = await buildWorkerAuthHeader(base);
  try {
    const r = await fetch(target, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...authHeader,
      },
      body: JSON.stringify({ triggeredAt, source: "vercel-cron" }),
      // Vercel edge has a per-fetch timeout; keep this short.
      signal: AbortSignal.timeout(8_000),
    });
    return NextResponse.json({
      ok: r.ok,
      triggeredAt,
      status: "queued",
      workerStatus: r.status,
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

// Allow POST for manual local testing: same auth required.
export const POST = GET;
