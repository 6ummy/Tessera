/**
 * /api/attribution/[personaId] — proxies the persona's ticker-level P&L
 * attribution from the Cloud Run worker. Same auth/cache pattern as the
 * other read proxies (Edge, IAM token, 60s CDN cache).
 */

import { NextResponse } from "next/server";
import { buildWorkerAuthHeader, workerBaseUrl } from "@/lib/gcp-auth";

export const runtime = "edge";
export const dynamic = "force-dynamic";

const VALID_PERSONAS = new Set(["warren", "cathie", "ray", "peter"]);
const VALID_PERIODS = new Set(["mtd", "7d", "30d"]);

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
  const periodRaw = url.searchParams.get("period") ?? "mtd";
  const period = VALID_PERIODS.has(periodRaw) ? periodRaw : "mtd";

  const base = workerBaseUrl();
  if (!base) {
    return NextResponse.json(
      { ok: false, error: "WORKER_WEBHOOK_URL not configured", rows: [] },
      { status: 503 },
    );
  }

  const target = `${base}/api/attribution/${personaId}?period=${period}`;
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
        { ok: false, status: upstream.status, body: text, rows: [] },
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
        rows: [],
      },
      { status: 502 },
    );
  }
}
