"use client";
import { useEffect, useState } from "react";
import { fetchAttribution } from "@/lib/performance-data";
import type { PersonaAttribution } from "@/lib/performance-types";
import { cn, fmt, signClass } from "@/lib/utils";

type Period = "mtd" | "7d" | "30d";
const PERIODS: { id: Period; label: string }[] = [
  { id: "mtd", label: "MTD" },
  { id: "7d", label: "7d" },
  { id: "30d", label: "30d" },
];

/** Ticker-level P&L attribution for the persona's paper track. Rows come
 * from /api/attribution and are pre-sorted by |pnl|; contributions sum to
 * the period's total return (shown in the header). Spans the hypothetical
 * backfill + live track transparently — same as the curve above it. */
export function AttributionTable({ personaId }: { personaId: string }) {
  const [period, setPeriod] = useState<Period>("mtd");
  const [data, setData] = useState<PersonaAttribution | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fetchAttribution(personaId, period).then((d) => {
      if (!alive) return;
      setData(d);
      setLoading(false);
    });
    return () => {
      alive = false;
    };
  }, [personaId, period]);

  const rows = data?.rows ?? [];

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium text-ink-900">Return attribution</h3>
          {data?.totalReturn != null && (
            <p className="mt-0.5 text-[11px] text-ink-500">
              Period total{" "}
              <span className={cn("num", signClass(data.totalReturn))}>
                {fmt.pct(data.totalReturn)}
              </span>{" "}
              · contributions sum to it
            </p>
          )}
        </div>
        <div className="inline-flex h-7 items-center gap-0.5 rounded-full bg-ink-900/[0.05] p-0.5 text-xs">
          {PERIODS.map((p) => (
            <button
              key={p.id}
              onClick={() => setPeriod(p.id)}
              className={cn(
                "rounded-full px-2.5 py-1 transition-colors",
                period === p.id
                  ? "bg-cream-50 text-ink-900 shadow-sm"
                  : "text-ink-500 hover:text-ink-800",
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="h-32 w-full animate-pulse rounded-2xl bg-ink-900/[0.04]" />
      ) : rows.length === 0 ? (
        <p className="rounded-2xl border border-ink-900/[0.06] bg-cream-50 px-4 py-6 text-center text-xs text-ink-500">
          No attribution yet for this window — the paper track needs at least
          two daily snapshots in the period.
        </p>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-ink-900/[0.06] bg-cream-50">
          <div className="grid grid-cols-[1.4fr_1fr_1fr] border-b border-ink-900/[0.06] bg-ink-900/[0.025] px-4 py-2 text-[10px] uppercase tracking-[0.14em] text-ink-500">
            <div>Position</div>
            <div className="text-right">P&L</div>
            <div className="text-right">Contribution</div>
          </div>
          {rows.map((r) => (
            <div
              key={r.ticker}
              className="grid grid-cols-[1.4fr_1fr_1fr] items-center border-b border-ink-900/[0.05] px-4 py-2.5 last:border-b-0"
            >
              <div className="min-w-0">
                <div className="num text-sm font-medium text-ink-900">{r.ticker}</div>
                <div className="truncate text-[11px] text-ink-500">{r.name}</div>
              </div>
              <div className={cn("num text-right text-sm", signClass(r.pnl))}>
                {r.pnl >= 0 ? "+" : "−"}${Math.abs(r.pnl).toLocaleString("en-US", { maximumFractionDigits: 0 })}
              </div>
              <div className={cn("num text-right text-sm", signClass(r.contribution))}>
                {fmt.pct(r.contribution, 2)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
