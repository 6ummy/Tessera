"use client";
import { useEffect, useState } from "react";
import { ChevronDown, FileText } from "lucide-react";
import type { Report, TickerFeatures } from "@/lib/thesis-types";
import type { Persona } from "@/lib/mock/personas";
import { ACCENT_CLASS } from "@/lib/mock/personas";
import { fetchTickerFeatures } from "@/lib/analyst-data";
import { Badge } from "./ui/badge";
import { cn } from "@/lib/utils";

const TYPE_TONE: Record<Report["type"], "default" | "coral" | "sage" | "plum"> = {
  thesis: "coral",
  update: "default",
  macro: "plum",
  exit: "sage",
};

const TYPE_LABEL: Record<Report["type"], string> = {
  thesis: "Thesis",
  update: "Update",
  macro: "Macro",
  exit: "Exit",
};

export function ReportList({ reports, persona }: { reports: Report[]; persona: Persona }) {
  const [openId, setOpenId] = useState<string | null>(reports[0]?.id ?? null);
  const a = ACCENT_CLASS[persona.accent];

  if (!reports?.length) return null;

  return (
    <div className="space-y-3">
      {reports.map((r) => {
        const open = openId === r.id;
        return (
          <article
            key={r.id}
            className={cn(
              "overflow-hidden rounded-2xl border bg-cream-50 transition-colors",
              open ? "border-ink-900/[0.12]" : "border-ink-900/[0.06]"
            )}
          >
            <button
              onClick={() => setOpenId(open ? null : r.id)}
              className="flex w-full items-start gap-4 px-5 py-4 text-left ring-focus hover:bg-ink-900/[0.02]"
            >
              <div className={cn("mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full", a.bg, a.text)}>
                <FileText className="h-3.5 w-3.5" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={TYPE_TONE[r.type]}>{TYPE_LABEL[r.type]}</Badge>
                  {r.tickers.map((t) => (
                    <span key={t} className="num text-[11px] font-medium text-ink-700">
                      {t}
                    </span>
                  ))}
                  <span className="num ml-auto text-[11px] text-ink-500">{r.date}</span>
                </div>
                <h4 className="display-serif mt-1.5 text-lg leading-snug text-ink-900">{r.title}</h4>
                <p className="mt-1 text-[13px] leading-relaxed text-ink-600">{r.summary}</p>
              </div>
              <ChevronDown
                className={cn(
                  "mt-1.5 h-4 w-4 shrink-0 text-ink-400 transition-transform",
                  open && "rotate-180"
                )}
              />
            </button>

            {open && (
              <div className="border-t border-ink-900/[0.06] px-5 pb-5 pt-4">
                {r.tickers[0] && <ThesisMetricsTable ticker={r.tickers[0]} />}
                <div className="prose prose-sm max-w-none">
                  {r.body.map((p, i) => (
                    <p key={i} className="text-[14px] leading-relaxed text-ink-700">
                      {p}
                    </p>
                  ))}
                </div>

                {r.numerics && r.numerics.length > 0 && (
                  <div className="mt-5">
                    <div className="mb-2 text-[10px] uppercase tracking-[0.16em] text-ink-500">
                      Key numerics
                    </div>
                    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-ink-900/[0.06] bg-ink-900/[0.06] sm:grid-cols-3">
                      {r.numerics.map((n) => (
                        <div key={n.label} className="bg-cream-50 px-3 py-2">
                          <div className="text-[10px] uppercase tracking-[0.14em] text-ink-500">
                            {n.label}
                          </div>
                          <div className="num mt-0.5 text-sm font-medium text-ink-900">{n.value}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {r.whatWouldMakeMeWrong && r.whatWouldMakeMeWrong.length > 0 && (
                  <div className="mt-5 rounded-xl border border-ink-900/[0.06] bg-cream-100/60 p-4">
                    <div className="mb-2 text-[10px] uppercase tracking-[0.16em] text-coral-600">
                      What would make me wrong
                    </div>
                    <ul className="space-y-1.5 text-[13px] leading-relaxed text-ink-700">
                      {r.whatWouldMakeMeWrong.map((w, i) => (
                        <li key={i} className="flex gap-2">
                          <span className="mt-2 inline-block h-1 w-1 shrink-0 rounded-full bg-coral-500" />
                          {w}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}

/**
 * Compact 4-cell key-metrics strip rendered at the top of an opened
 * thesis. Fetches the latest ticker_features for the report's primary
 * ticker once (per mount) and shows the four numbers most readers
 * scan first: price vs 52w trend, valuation, quality, durability.
 */
function ThesisMetricsTable({ ticker }: { ticker: string }) {
  const [data, setData] = useState<TickerFeatures | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    fetchTickerFeatures(ticker, { signal: ctrl.signal }).then((d) => {
      if (ctrl.signal.aborted) return;
      setData(d);
      setLoading(false);
    });
    return () => ctrl.abort();
  }, [ticker]);

  if (loading) {
    return (
      <div className="mb-4 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-ink-900/[0.06] bg-ink-900/[0.06] sm:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-12 animate-pulse bg-ink-900/[0.02]" />
        ))}
      </div>
    );
  }
  const f = data?.features;
  if (!f) return null;

  const cells: { label: string; value: string }[] = [
    { label: "1y return", value: fmtPctSigned(f.ret_1y) },
    { label: "FCF yield", value: fmtPct(f.fcf_yield) },
    { label: "PEG", value: fmtNum(f.peg, 2) },
    { label: "Gross margin", value: fmtPct(f.gross_margin) },
  ];

  return (
    <div className="mb-4">
      <div className="mb-2 flex items-baseline justify-between">
        <div className="text-[10px] uppercase tracking-[0.16em] text-ink-500">
          {ticker} · key metrics
        </div>
        <div className="num text-[10px] text-ink-400">
          as of {data?.asof ?? "—"}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-ink-900/[0.06] bg-ink-900/[0.06] sm:grid-cols-4">
        {cells.map((c) => (
          <div key={c.label} className="bg-cream-50 px-3 py-2">
            <div className="text-[10px] uppercase tracking-[0.14em] text-ink-500">
              {c.label}
            </div>
            <div className="num mt-0.5 text-sm font-medium text-ink-900">{c.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${(v * 100).toFixed(2)}%`;
}
function fmtPctSigned(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(1)}%`;
}
function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return "—";
  return v.toFixed(digits);
}
