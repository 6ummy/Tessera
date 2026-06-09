"use client";
import { useEffect, useMemo, useState } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fetchTickerPrices } from "@/lib/analyst-data";
import type { TickerPrices } from "@/lib/thesis-types";
import { cn } from "@/lib/utils";

type Range = "1y" | "5y" | "10y" | "20y";

const RANGES: Range[] = ["1y", "5y", "10y", "20y"];

/**
 * Lazy-loads the long-horizon close-price series for one ticker and
 * renders it as an area chart. Mounts inside the expanded position card.
 *
 * Range buttons trigger an in-place refetch — each range hits its own
 * /api/prices/{ticker}?range=… key, so the Edge CDN caches them
 * independently (5-min TTL).
 */
export function PriceHistoryChart({
  ticker,
  color,
  defaultRange = "20y",
}: {
  ticker: string;
  color: string;
  defaultRange?: Range;
}) {
  const [range, setRange] = useState<Range>(defaultRange);
  const [data, setData] = useState<TickerPrices | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    fetchTickerPrices(ticker, { range, signal: ctrl.signal }).then((d) => {
      if (ctrl.signal.aborted) return;
      setData(d);
      setLoading(false);
    });
    return () => ctrl.abort();
  }, [ticker, range]);

  const series = useMemo(
    () => (data?.points ?? []).map((p) => ({ date: p.date, close: p.close })),
    [data],
  );

  const { firstClose, lastClose, totalReturn } = useMemo(() => {
    if (!series.length) return { firstClose: null, lastClose: null, totalReturn: null };
    const f = series[0].close;
    const l = series[series.length - 1].close;
    return { firstClose: f, lastClose: l, totalReturn: f > 0 ? l / f - 1 : null };
  }, [series]);

  const gradId = `priceGrad-${ticker}-${color.replace("#", "")}`;

  return (
    <div className="mt-3 rounded-lg border border-ink-900/[0.06] bg-cream-50 px-3 py-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <div className="text-[10px] uppercase tracking-[0.16em] text-ink-500">
            Price history
          </div>
          {totalReturn !== null && firstClose !== null && lastClose !== null && (
            <div className="num text-[11px] text-ink-600">
              ${firstClose.toFixed(2)} → ${lastClose.toFixed(2)}{" "}
              <span
                className={cn(
                  "font-medium",
                  totalReturn >= 0 ? "text-sage-600" : "text-coral-600",
                )}
              >
                ({totalReturn >= 0 ? "+" : ""}
                {(totalReturn * 100).toFixed(0)}%)
              </span>
            </div>
          )}
        </div>
        <div className="inline-flex items-center gap-0.5 rounded-full bg-ink-900/[0.05] p-0.5">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={cn(
                "rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] transition-colors",
                range === r
                  ? "bg-cream-50 text-ink-900 shadow-sm"
                  : "text-ink-500 hover:text-ink-800",
              )}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="h-32 animate-pulse rounded-md bg-ink-900/[0.04]" />
      ) : series.length === 0 ? (
        <div className="grid h-32 place-items-center text-[11px] text-ink-500">
          No price history available for {ticker} yet.
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={140}>
          <AreaChart data={series} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.28} />
                <stop offset="100%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="date"
              tick={{ fontSize: 9 }}
              tickFormatter={(v: string) => v.slice(0, 4)}
              minTickGap={48}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 9 }}
              tickFormatter={(v: number) =>
                v >= 1000 ? `${(v / 1000).toFixed(1)}k` : `${v.toFixed(0)}`
              }
              axisLine={false}
              tickLine={false}
              width={32}
              domain={["dataMin", "dataMax"]}
            />
            <Tooltip
              contentStyle={{
                background: "#FAF9F5",
                border: "1px solid rgba(31,30,27,0.08)",
                borderRadius: 10,
                fontSize: 11,
                padding: "6px 10px",
              }}
              labelStyle={{
                color: "#7C7870",
                marginBottom: 2,
                fontFamily: "var(--font-mono)",
              }}
              formatter={(v: number) => [`$${v.toFixed(2)}`, "Close"]}
            />
            <Area
              type="monotone"
              dataKey="close"
              stroke={color}
              strokeWidth={1.5}
              fill={`url(#${gradId})`}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
