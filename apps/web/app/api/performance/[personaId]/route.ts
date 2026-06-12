/**
 * /api/performance/[personaId] — proxies the persona's paper-track
 * equity curve + headline metrics from the Cloud Run worker.
 *
 * Same auth/cache pattern as /api/reports: Edge runtime, IAM identity
 * token (or bearer fallback), 60s CDN cache — the curve only gains one
 * point per nightly ingest, so freshness needs are loose.
 */

import { NextResponse } from "next/server";
import { buildWorkerAuthHeader, workerBaseUrl } from "@/lib/gcp-auth";

export const runtime = "edge";
export const dynamic = "force-dynamic";

const VALID_PERSONAS = new Set(["warren", "cathie", "ray", "peter"]);

export async function GET(
  req: Request,
  { params }: { params: { personaId: string } },
) {
  const { personaId } = params;
  if (!VALID_PERSONAS.has(personaId)) {
    return NextResponse.json(
      { ok: false, error: `unknown persona: ${personaId}` },
      { status: 400 },
    );
  }

  const url = new URL(req.url);
  const days = url.searchParams.get("days") ?? "400";

  const base = workerBaseUrl();
  if (!base) {
    return NextResponse.json(
      { ok: false, error: "WORKER_WEBHOOK_URL not configured", series: [] },
      { status: 503 },
    );
  }

  const target = `${base}/api/performance/${personaId}?days=${encodeURIComponent(days)}`;
  const authHeader = await buildWorkerAuthHeader(base);

  try {
    const upstream = await fetch(target, {
      headers: { ...authHeader },
      signal: AbortSignal.timeout(15_000),
      next: { revalidate: 60 },
    });
    if (!upstream.ok) {
      const text = await upstream.text().catch(() => "");
      return NextResponse.json(
        { ok: false, status: upstream.status, body: text, series: [] },
        { status: 502 },
      );
    }
    return new NextResponse(upstream.body, {
      status: 200,
      headers: {
        "content-type": "application/json",
        "cache-control": "public, s-maxage=60, stale-while-revalidate=300",
      },
    });
  } catch (err) {
    return NextResponse.json(
      {
        ok: false,
        error: "worker_unreachable",
        detail: err instanceof Error ? err.message : String(err),
        series: [],
      },
      { status: 502 },
    );
  }
}
