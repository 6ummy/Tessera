"use client";
import { useEffect, useState } from "react";
import { fetchTickerFeatures } from "@/lib/analyst-data";
import type { TickerFeatures } from "@/lib/thesis-types";
import { cn } from "@/lib/utils";

/**
 * Expandable feature grid for a position card. Lazy-fetches the latest
 * ticker_features row when first opened (one shot per ticker; results
 * are not memoized across mounts, but the proxy + worker share a 60s
 * CDN cache so repeat hits are fast).
 *
 * Visual grouping: Valuation (fcf_yield, peg, mcap), Quality (eps_cagr,
 * d/e, gross margin + trend), Price (1m / 3m / 1y returns), Technical
 * (vol_30d, rsi, volume_z).
 */
export function PositionFeatures({
  ticker,
  open,
  accent = "text-coral-600",
}: {
  ticker: string;
  open: boolean;
  accent?: string;
}) {
  const [data, setData] = useState<TickerFeatures | null>(null);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!open || loaded) return;
    const ctrl = new AbortController();
    setLoading(true);
    fetchTickerFeatures(ticker, { signal: ctrl.signal }).then((d) => {
      if (ctrl.signal.aborted) return;
      setData(d);
      setLoaded(true);
      setLoading(false);
    });
    return () => ctrl.abort();
  }, [open, ticker, loaded]);

  if (!open) return null;

  if (loading) {
    return (
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="h-12 animate-pulse rounded-lg bg-ink-900/[0.04]"
          />
        ))}
      </div>
    );
  }

  if (!data?.features) {
    return (
      <p className="mt-3 rounded-lg border border-dashed border-ink-900/10 bg-cream-50 px-3 py-3 text-center text-[11px] text-ink-500">
        No feature snapshot yet. Daily ingest hasn't populated this
        ticker — try again after the next 21:30 UTC cron.
      </p>
    );
  }

  const f = data.features;
  const groups: { title: string; cells: { label: string; value: string }[] }[] =
    [
      {
        title: "Valuation",
        cells: [
          { label: "FCF yield", value: fmtPct(f.fcf_yield) },
          { label: "PEG", value: fmtNum(f.peg, 2) },
          { label: "Market cap", value: fmtMoney(f.market_cap_usd) },
        ],
      },
      {
        title: "Quality",
        cells: [
          { label: "EPS CAGR 3y", value: fmtPctSigned(f.eps_cagr_3y) },
          { label: "Debt / Equity", value: fmtNum(f.debt_to_equity, 2) },
          { label: "Gross margin", value: fmtPct(f.gross_margin) },
          {
            label: "Margin trend 3y",
            value: fmtPctSigned(f.gross_margin_trend),
          },
          { label: "Op margin", value: fmtPct(f.operating_margin) },
        ],
      },
      {
        title: "Price returns",
        cells: [
          { label: "30d", value: fmtPctSigned(f.ret_30d) },
          { label: "90d", value: fmtPctSigned(f.ret_90d) },
          { label: "1y", value: fmtPctSigned(f.ret_1y) },
        ],
      },
      {
        title: "Technical",
        cells: [
          { label: "Realized vol 30d", value: fmtPct(f.vol_30d) },
          { label: "RSI 14", value: fmtNum(f.rsi_14, 0) },
          { label: "Volume z", value: fmtNum(f.volume_z, 2, true) },
        ],
      },
    ];

  return (
    <div className="mt-3 space-y-3 rounded-lg border border-ink-900/[0.06] bg-cream-50 px-3 py-3">
      <div className="flex items-baseline justify-between">
        <div className={cn("text-[10px] uppercase tracking-[0.16em]", accent)}>
          {data.ticker} · {data.name}
        </div>
        <div className="num text-[10px] text-ink-400">
          as of {data.asof ?? "—"}
        </div>
      </div>
      {groups.map((g) => (
        <div key={g.title}>
          <div className="mb-1.5 text-[9px] uppercase tracking-[0.14em] text-ink-500">
            {g.title}
          </div>
          <div className="grid grid-cols-3 gap-px overflow-hidden rounded-md border border-ink-900/[0.06] bg-ink-900/[0.06]">
            {g.cells.map((c) => (
              <div key={c.label} className="bg-cream-50 px-2 py-1.5">
                <div className="text-[9px] uppercase tracking-[0.12em] text-ink-500">
                  {c.label}
                </div>
                <div className="num mt-0.5 text-[12px] font-medium text-ink-900">
                  {c.value}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function fmtPct(v: number | null): string {
  if (v === null || v === undefined) return "—";
  return `${(v * 100).toFixed(2)}%`;
}
function fmtPctSigned(v: number | null): string {
  if (v === null || v === undefined) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(1)}%`;
}
function fmtNum(v: number | null, digits = 2, signed = false): string {
  if (v === null || v === undefined) return "—";
  const sign = signed && v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(digits)}`;
}
function fmtMoney(v: number | null): string {
  if (v === null || v === undefined) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toFixed(0)}`;
}
