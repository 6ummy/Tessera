/**
 * /api/proposals/[personaId] — most-recent thesis for one persona,
 * proxied from the Cloud Run worker and reshaped as a Proposal-like
 * object (uniform shape across stock-pickers + Ray).
 *
 * Edge runtime, 60s CDN cache (same cadence as /api/reports).
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
      {
        ok: false,
        error: "WORKER_WEBHOOK_URL not configured",
        personaId,
        positions: [],
      },
      { status: 503 },
    );
  }

  const target = `${base}/api/proposals/${personaId}`;
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
        { ok: false, status: upstream.status, body: text, personaId,
          positions: [] },
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
        personaId,
        positions: [],
      },
      { status: 502 },
    );
  }
}
