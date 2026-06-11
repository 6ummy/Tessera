"use client";
import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { FileText, X } from "lucide-react";
import type { Report } from "@/lib/thesis-types";
import type { Persona } from "@/lib/mock/personas";
import { ACCENT_CLASS } from "@/lib/mock/personas";
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

export type RelatedThesisEntry = {
  report: Report;
  persona: Persona;
};

/**
 * Cross-persona thesis index rendered at the bottom of an expanded
 * position card. Each entry shows author + title + date; clicking
 * pops a Radix Dialog with the full thesis body over a blurred
 * backdrop (same overlay style as the persona detail sheet).
 */
// Map raw conviction to the same readable tier the worker uses in
// _reshape_report_row. Centralized here so the UI doesn't depend on the
// worker's reshape for the related-thesis rendering (which needs per-
// ticker conviction, not the report's first-proposal conviction).
function convictionLabel(conv: number, side: string): string {
  if (side === "trim" || side === "sell") return side;
  if (conv >= 0.80) return "Strong buy";
  if (conv >= 0.65) return "Buy";
  if (conv >= 0.50) return "Hold";
  return "Watch";
}

export function RelatedThesis({
  ticker,
  entries,
  loading,
}: {
  ticker: string;
  entries: RelatedThesisEntry[];
  loading: boolean;
}) {
  const [openId, setOpenId] = useState<string | null>(null);
  const openEntry = entries.find((e) => e.report.id === openId) ?? null;
  const tickerKey = ticker.toUpperCase();

  return (
    <div className="mt-3 rounded-lg border border-ink-900/[0.06] bg-cream-50 px-3 py-3">
      <div className="mb-2 flex items-baseline justify-between">
        <div className="text-[10px] uppercase tracking-[0.16em] text-ink-500">
          Related thesis
        </div>
        <div className="num text-[10px] text-ink-400">
          {loading ? "loading…" : `${entries.length} on file`}
        </div>
      </div>

      {loading ? (
        <div className="space-y-1.5">
          <div className="h-10 animate-pulse rounded-md bg-ink-900/[0.04]" />
          <div className="h-10 animate-pulse rounded-md bg-ink-900/[0.04]" />
        </div>
      ) : entries.length === 0 ? (
        <p className="rounded-md border border-dashed border-ink-900/10 px-3 py-3 text-center text-[11px] text-ink-500">
          No analyst has written about {ticker} yet.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {entries.map(({ report, persona }) => {
            const a = ACCENT_CLASS[persona.accent];
            // Per-ticker proposal info if v2 report carried the map.
            // Falls back to the global report.title for v1 rows or
            // ETF/regime rows where the map isn't populated.
            const perTicker = report.proposalsByTicker?.[tickerKey];
            const tickerTitle = perTicker
              ? `${persona.name} · ${tickerKey} · ${convictionLabel(perTicker.conviction, perTicker.side)}`
              : report.title;
            return (
              <li key={report.id}>
                <button
                  onClick={() => setOpenId(report.id)}
                  className={cn(
                    "flex w-full items-start gap-3 rounded-md border border-ink-900/[0.06] bg-cream-50 px-3 py-2 text-left transition-colors",
                    "hover:border-ink-900/[0.14] hover:bg-ink-900/[0.02] ring-focus",
                  )}
                >
                  <div
                    className={cn(
                      "mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full",
                      a.bg,
                      a.text,
                    )}
                  >
                    <FileText className="h-3 w-3" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge tone={TYPE_TONE[report.type]}>{TYPE_LABEL[report.type]}</Badge>
                      <span className="text-[11px] font-medium text-ink-700">
                        {persona.name}
                      </span>
                      <span className="num ml-auto text-[10px] text-ink-500">
                        {report.date}
                      </span>
                    </div>
                    <h5 className="display-serif mt-1 line-clamp-2 text-[13px] leading-snug text-ink-900">
                      {tickerTitle}
                    </h5>
                    {perTicker?.thesisMd && (
                      <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-ink-600">
                        {perTicker.thesisMd}
                      </p>
                    )}
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <Dialog.Root open={!!openEntry} onOpenChange={(o) => !o && setOpenId(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-ink-900/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=open]:fade-in" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[92vw] max-w-2xl -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-3xl border border-ink-900/[0.08] bg-cream-50 shadow-2xl outline-none data-[state=open]:animate-in data-[state=open]:fade-in data-[state=open]:zoom-in-95">
            <Dialog.Title className="sr-only">
              {openEntry?.report.title ?? "Thesis"}
            </Dialog.Title>
            <Dialog.Close
              aria-label="Close"
              className="absolute right-5 top-5 z-10 rounded-full p-1.5 text-ink-500 hover:bg-ink-900/[0.05] hover:text-ink-800 ring-focus"
            >
              <X className="h-4 w-4" />
            </Dialog.Close>
            {openEntry && <ThesisModalBody entry={openEntry} ticker={tickerKey} />}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}

function ThesisModalBody({
  entry,
  ticker,
}: {
  entry: RelatedThesisEntry;
  ticker: string;
}) {
  const { report, persona } = entry;
  const a = ACCENT_CLASS[persona.accent];
  // v2 reports carry per-ticker proposals on `proposalsByTicker`. When
  // we're showing this modal for a specific sibling ticker, render its
  // sizing reasoning, not the report's first-proposal body.
  const perTicker = report.proposalsByTicker?.[ticker];
  const title = perTicker
    ? `${persona.name} · ${ticker} · ${convictionLabel(perTicker.conviction, perTicker.side)}`
    : report.title;
  const bodyParas = perTicker?.thesisMd
    ? perTicker.thesisMd.split(/\n{2,}/).filter((p) => p.trim())
    : report.body;
  return (
    <div className="max-h-[85vh] overflow-y-auto">
      <div className="border-b border-ink-900/[0.06] px-7 py-6">
        <div className="flex items-center gap-2">
          <div className={cn("h-1.5 w-1.5 rounded-full", a.dot)} />
          <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-ink-500">
            {persona.name} · {persona.archetype}
          </span>
          <span className="num ml-auto text-[11px] text-ink-500">{report.date}</span>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Badge tone={TYPE_TONE[report.type]}>{TYPE_LABEL[report.type]}</Badge>
          <span className="num text-[11px] font-medium text-ink-700">{ticker}</span>
          {perTicker && (
            <span className="num text-[11px] text-ink-500">
              · {(perTicker.targetWeight * 100).toFixed(1)}% weight · conv {perTicker.conviction.toFixed(2)}
            </span>
          )}
        </div>
        <h2 className="display-serif mt-3 text-3xl leading-tight text-ink-900">
          {title}
        </h2>
      </div>
      <div className="px-7 py-6">
        <div className="prose prose-sm max-w-none">
          {bodyParas.length === 0 ? (
            <p className="text-[14px] leading-relaxed text-ink-500">
              {report.summary || "No body content."}
            </p>
          ) : (
            bodyParas.map((p, i) => (
              <p key={i} className="text-[14px] leading-relaxed text-ink-700">
                {p}
              </p>
            ))
          )}
        </div>

        {report.numerics && report.numerics.length > 0 && (
          <div className="mt-6">
            <div className="mb-2 text-[10px] uppercase tracking-[0.16em] text-ink-500">
              Key numerics
            </div>
            <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-ink-900/[0.06] bg-ink-900/[0.06] sm:grid-cols-3">
              {report.numerics.map((n) => (
                <div key={n.label} className="bg-cream-50 px-3 py-2">
                  <div className="text-[10px] uppercase tracking-[0.14em] text-ink-500">
                    {n.label}
                  </div>
                  <div className="num mt-0.5 text-sm font-medium text-ink-900">
                    {n.value}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {report.whatWouldMakeMeWrong && report.whatWouldMakeMeWrong.length > 0 && (
          <div className="mt-6 rounded-xl border border-ink-900/[0.06] bg-cream-100/60 p-4">
            <div className="mb-2 text-[10px] uppercase tracking-[0.16em] text-coral-600">
              What would make me wrong
            </div>
            <ul className="space-y-1.5 text-[13px] leading-relaxed text-ink-700">
              {report.whatWouldMakeMeWrong.map((w, i) => (
                <li key={i} className="flex gap-2">
                  <span className="mt-2 inline-block h-1 w-1 shrink-0 rounded-full bg-coral-500" />
                  {w}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
