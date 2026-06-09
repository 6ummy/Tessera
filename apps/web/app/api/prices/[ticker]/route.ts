/**
 * /api/prices/[ticker]?range=20y — proxies long-horizon close price
 * series from the Cloud Run worker.
 *
 * Returns a downsampled timeseries (~250 points). Used by the expandable
 * position card to render a 20-year price line.
 *
 * Edge runtime, 5-minute CDN cache — daily OHLCV updates after the
 * 21:30 UTC cron, so we can be generous here.
 */

import { NextResponse } from "next/server";

export const runtime = "edge";
export const dynamic = "force-dynamic";

const ALLOWED_RANGES = new Set(["1y", "5y", "10y", "20y", "max"]);

export async function GET(
  req: Request,
  { params }: { params: { ticker: string } },
) {
  const { ticker } = params;
  if (!/^[A-Z./]{1,12}$/i.test(ticker)) {
    return NextResponse.json(
      { ok: false, error: `invalid ticker: ${ticker}` },
      { status: 400 },
    );
  }

  const url = new URL(req.url);
  const requested = (url.searchParams.get("range") || "20y").toLowerCase();
  const range = ALLOWED_RANGES.has(requested) ? requested : "20y";

  const workerUrl = process.env.WORKER_WEBHOOK_URL;
  if (!workerUrl) {
    return NextResponse.json(
      { ok: false, error: "WORKER_WEBHOOK_URL not configured", ticker, points: [] },
      { status: 503 },
    );
  }

  const base = workerUrl.replace(/\/jobs\/[^/]+\/?$/, "").replace(/\/$/, "");
  const target = `${base}/api/prices/${encodeURIComponent(ticker.toUpperCase())}?range=${range}`;
  const secret = process.env.WORKER_WEBHOOK_SECRET;

  try {
    const upstream = await fetch(target, {
      headers: { ...(secret ? { authorization: `Bearer ${secret}` } : {}) },
      signal: AbortSignal.timeout(10_000),
      next: { revalidate: 300 },
    });
    if (!upstream.ok) {
      const text = await upstream.text().catch(() => "");
      return NextResponse.json(
        { ok: false, status: upstream.status, body: text, ticker, points: [] },
        { status: upstream.status === 404 ? 404 : 502 },
      );
    }
    return new NextResponse(upstream.body, {
      status: 200,
      headers: {
        "content-type": "application/json",
        "cache-control": "public, s-maxage=300, stale-while-revalidate=3600",
      },
    });
  } catch (err) {
    return NextResponse.json(
      {
        ok: false,
        error: "worker_unreachable",
        detail: err instanceof Error ? err.message : String(err),
        ticker,
        points: [],
      },
      { status: 502 },
    );
  }
}
