/**
 * /api/features/[ticker] — proxies the latest `ticker_features` row
 * for one ticker from the Cloud Run worker.
 *
 * Used by the expandable position card on the persona detail sheet +
 * /proposals page: when a user clicks a position, the card expands to
 * show price returns, valuation, and quality metrics for that ticker.
 *
 * Edge runtime, 60s CDN cache — the underlying row only refreshes once
 * a day after the daily ingest cron, so aggressive caching is fine.
 */

import { NextResponse } from "next/server";
import { buildWorkerAuthHeader, workerBaseUrl } from "@/lib/gcp-auth";

export const runtime = "edge";
export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  { params }: { params: { ticker: string } },
) {
  const { ticker } = params;
  // Light validation — workers does the real universe check.
  if (!/^[A-Z./]{1,12}$/i.test(ticker)) {
    return NextResponse.json(
      { ok: false, error: `invalid ticker: ${ticker}` },
      { status: 400 },
    );
  }

  const base = workerBaseUrl();
  if (!base) {
    return NextResponse.json(
      {
        ok: false,
        error: "WORKER_WEBHOOK_URL not configured",
        ticker,
        features: null,
      },
      { status: 503 },
    );
  }

  const target = `${base}/api/features/${encodeURIComponent(ticker.toUpperCase())}`;
  const authHeader = await buildWorkerAuthHeader(base);

  try {
    const upstream = await fetch(target, {
      headers: { ...authHeader },
      signal: AbortSignal.timeout(10_000),
      next: { revalidate: 60 },
    });
    if (!upstream.ok) {
      const text = await upstream.text().catch(() => "");
      return NextResponse.json(
        { ok: false, status: upstream.status, body: text, ticker, features: null },
        { status: upstream.status === 404 ? 404 : 502 },
      );
    }
    return new NextResponse(upstream.body, {
      status: 200,
      headers: {
        "content-type": "application/json",
        "cache-control": "public, s-maxage=60, stale-while-revalidate=600",
      },
    });
  } catch (err) {
    return NextResponse.json(
      {
        ok: false,
        error: "worker_unreachable",
        detail: err instanceof Error ? err.message : String(err),
        ticker,
        features: null,
      },
      { status: 502 },
    );
  }
}
