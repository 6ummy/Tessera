/**
 * /api/reports/[personaId] — proxies the latest N reports for one
 * persona from the Cloud Run worker.
 *
 * Same auth pattern as /api/chat (Bearer via WORKER_WEBHOOK_SECRET).
 * Edge runtime, cached for 60s at the CDN so 4-persona fan-out from
 * the persona-detail-sheet doesn't hammer the worker on every page open.
 */

import { NextResponse } from "next/server";

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
  const limit = url.searchParams.get("limit") ?? "5";

  const workerUrl = process.env.WORKER_WEBHOOK_URL;
  if (!workerUrl) {
    return NextResponse.json(
      { ok: false, error: "WORKER_WEBHOOK_URL not configured", reports: [] },
      { status: 503 },
    );
  }

  const base = workerUrl.replace(/\/jobs\/[^/]+\/?$/, "").replace(/\/$/, "");
  const target = `${base}/api/reports/${personaId}?limit=${encodeURIComponent(limit)}`;
  const secret = process.env.WORKER_WEBHOOK_SECRET;

  try {
    const upstream = await fetch(target, {
      headers: { ...(secret ? { authorization: `Bearer ${secret}` } : {}) },
      signal: AbortSignal.timeout(15_000),
      // Edge cache: persona reports refresh weekly (Fri 22:00 UTC after
      // persona_batch). 60s s-maxage is generous; user-facing freshness
      // doesn't need to be tighter.
      next: { revalidate: 60 },
    });
    if (!upstream.ok) {
      const text = await upstream.text().catch(() => "");
      return NextResponse.json(
        { ok: false, status: upstream.status, body: text, reports: [] },
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
        reports: [],
      },
      { status: 502 },
    );
  }
}
