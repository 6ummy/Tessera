/**
 * /api/portfolio/[personaId] — proxies the persona's latest REAL paper
 * portfolio snapshot (positions + cash) from the Cloud Run worker.
 * Hypothetical backfill rows are never served by this route.
 */

import { NextResponse } from "next/server";
import { buildWorkerAuthHeader, workerBaseUrl } from "@/lib/gcp-auth";

export const runtime = "edge";
export const dynamic = "force-dynamic";

const VALID_PERSONAS = new Set(["warren", "cathie", "ray", "peter", "michael"]);

export async function GET(
  _req: Request,
  { params }: { params: { personaId: string } },
) {
  const { personaId } = params;
  if (!VALID_PERSONAS.has(personaId)) {
    return NextResponse.json(
      { ok: false, error: `unknown persona: ${personaId}` },
      { status: 400 },
    );
  }

  const base = workerBaseUrl();
  if (!base) {
    return NextResponse.json(
      { ok: false, error: "WORKER_WEBHOOK_URL not configured", positions: [] },
      { status: 503 },
    );
  }

  const target = `${base}/api/portfolio/${personaId}`;
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
        { ok: false, status: upstream.status, body: text, positions: [] },
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
        positions: [],
      },
      { status: 502 },
    );
  }
}
