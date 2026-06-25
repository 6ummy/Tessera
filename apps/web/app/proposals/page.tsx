"use client";
import { Fragment, useEffect, useMemo, useState } from "react";
import { Sparkles, Users } from "lucide-react";
import { PERSONAS, PERSONA_BY_ID, ACCENT_CLASS, type Persona } from "@/lib/mock/personas";
import { fetchProposal, fetchReports } from "@/lib/analyst-data";
import type { Proposal, Report } from "@/lib/thesis-types";
import { Header } from "@/components/header";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { PositionFeatures } from "@/components/position-features";
import { RelatedThesis, type RelatedThesisEntry } from "@/components/related-thesis";
import { PersonaDetailSheet } from "@/components/persona-detail-sheet";
import { FollowButton } from "@/components/follow-button";
import { ArrowUpRight, X } from "lucide-react";
import { cn, fmt } from "@/lib/utils";

// Consensus grid: 1 ticker col + one col per analyst + 1 avg-conv col. Built
// from PERSONAS.length (inline style, not a Tailwind arbitrary value) so it
// stays correct as personas are added (e.g. Michael → 5).
const CONSENSUS_GRID = `2fr repeat(${PERSONAS.length}, minmax(0, 1fr)) 1fr`;

// weight < 0.1% = watchlist (LLM analyzed but isn't buying now).
const ACTIVE_THRESHOLD = 0.001;

const ACCENT_HEX: Record<Persona["accent"], string> = {
  coral: "#D97757",
  sage: "#6B8E6B",
  plum: "#8B6B8E",
  ink: "#1F1E1B", oxblood: "#9A3B2E",
};

type ConsensusRow = {
  ticker: string;
  name: string;
  sector: string;
  mentions: { personaId: string; weight: number; conviction: number | null }[];
  avgConviction: number;
  avgWeight: number;
};

export default function ProposalsPage() {
  const [highlight, setHighlight] = useState<string | null>(null);
  // Persona detail sheet — same panel the landing page opens, shared here
  // so clicking an analyst in proposals shows the full thesis/chat/follow.
  const [openId, setOpenId] = useState<string | null>(null);
  // Clicking a ticker (in a portfolio or the consensus table) opens a centered
  // detail modal instead of expanding inline.
  const [modalPos, setModalPos] = useState<{ ticker: string; name: string; accentText: string } | null>(null);
  useEffect(() => {
    if (!modalPos) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setModalPos(null); };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = ""; };
  }, [modalPos]);
  const [proposals, setProposals] = useState<Record<string, Proposal | null>>({});
  const [reportsByPersona, setReportsByPersona] = useState<Record<string, Report[]>>({});
  const [loading, setLoading] = useState(true);
  const [reportsLoading, setReportsLoading] = useState(true);

  // Fetch all 4 personas in parallel on mount — proposals drive the
  // primary grid, reports power the cross-persona "Related thesis"
  // index shown when a card is expanded.
  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    setReportsLoading(true);
    Promise.all(
      PERSONAS.map((p) =>
        fetchProposal(p.id, { signal: ctrl.signal }).then((data) => [p.id, data] as const),
      ),
    ).then((entries) => {
      if (ctrl.signal.aborted) return;
      setProposals(Object.fromEntries(entries));
      setLoading(false);
    });
    Promise.all(
      PERSONAS.map((p) =>
        fetchReports(p.id, { limit: 10, signal: ctrl.signal }).then(
          (rs) => [p.id, rs] as const,
        ),
      ),
    ).then((entries) => {
      if (ctrl.signal.aborted) return;
      setReportsByPersona(Object.fromEntries(entries));
      setReportsLoading(false);
    });
    return () => ctrl.abort();
  }, []);

  // Cross-persona index: ticker → every report from any persona that
  // tags this ticker. Dedupes by (persona, ticker) — when the same batch
  // gets re-triggered (manual + auto) the worker writes a fresh
  // analyst_reports row each time; without the dedupe the UI shows the
  // same thesis stacked. Keeps only the newest entry per persona.
  const thesisByTicker = useMemo<Record<string, RelatedThesisEntry[]>>(() => {
    const out: Record<string, RelatedThesisEntry[]> = {};
    for (const persona of PERSONAS) {
      const reports = reportsByPersona[persona.id] ?? [];
      for (const r of reports) {
        for (const t of r.tickers) {
          const key = t.toUpperCase();
          (out[key] ??= []).push({ report: r, persona });
        }
      }
    }
    for (const k of Object.keys(out)) {
      // Sort newest-first, then keep one entry per persona (the newest).
      out[k].sort((a, b) => (a.report.date < b.report.date ? 1 : -1));
      const seen = new Set<string>();
      out[k] = out[k].filter(({ persona }) => {
        if (seen.has(persona.id)) return false;
        seen.add(persona.id);
        return true;
      });
    }
    return out;
  }, [reportsByPersona]);

  const consensus = useMemo<ConsensusRow[]>(() => {
    const byTicker = new Map<string, ConsensusRow>();
    for (const persona of PERSONAS) {
      const prop = proposals[persona.id];
      if (!prop) continue;
      for (const pos of prop.positions) {
        const existing = byTicker.get(pos.ticker);
        if (existing) {
          existing.mentions.push({
            personaId: persona.id,
            weight: pos.weight,
            conviction: pos.conviction,
          });
        } else {
          byTicker.set(pos.ticker, {
            ticker: pos.ticker,
            name: pos.name,
            sector: pos.sector,
            mentions: [{
              personaId: persona.id,
              weight: pos.weight,
              conviction: pos.conviction,
            }],
            avgConviction: 0,
            avgWeight: 0,
          });
        }
      }
    }
    const rows = Array.from(byTicker.values()).map((row) => {
      const convs = row.mentions.map((m) => m.conviction).filter((c): c is number => c !== null);
      row.avgConviction = convs.length ? convs.reduce((a, b) => a + b, 0) / convs.length : 0;
      row.avgWeight = row.mentions.reduce((a, m) => a + m.weight, 0) / row.mentions.length;
      return row;
    });
    // Default order: most analysts first, then highest avg allocation %, then
    // highest avg conviction.
    rows.sort(
      (a, b) =>
        b.mentions.length - a.mentions.length ||
        b.avgWeight - a.avgWeight ||
        b.avgConviction - a.avgConviction,
    );
    return rows;
  }, [proposals]);

  // Mobile (<sm): consensus shows ticker + analyst columns only — no company
  // name and no Avg-conv column — so it doesn't overflow a phone width.
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 639px)");
    const sync = () => setIsMobile(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  const consensusGrid = isMobile
    ? `minmax(0,1.4fr) repeat(${PERSONAS.length}, minmax(0,1fr))`
    : CONSENSUS_GRID;

  // Mobile by-analyst: all cards show; each lists its first 3 positions with a
  // "Show all positions" toggle. Desktop = full grid, all positions.
  const [expandedCards, setExpandedCards] = useState<Set<string>>(new Set());
  const toggleCard = (id: string) =>
    setExpandedCards((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });

  // Consensus is shown in its fixed default order (most analysts → avg
  // allocation % → avg conviction). No re-sort — the default is the useful view.

  // Display "as of" — latest date across all personas.
  const asOfDisplay = useMemo(() => {
    const dates = Object.values(proposals)
      .map((p) => p?.asOf)
      .filter((d): d is string => !!d)
      .sort();
    return dates[dates.length - 1] ?? null;
  }, [proposals]);

  return (
    <main className="min-h-screen">
      <Header variant="solid" />

      <section className="border-b border-ink-900/[0.06] bg-cream-50/40 py-12">
        <div className="mx-auto max-w-7xl px-6">
          <div className="flex flex-col items-start justify-between gap-6 lg:flex-row lg:items-end">
            <div>
              <div className="text-xs font-medium uppercase tracking-[0.18em] text-coral-600">This week's research</div>
              <h1 className="display-serif mt-3 text-3xl tracking-tightest text-ink-900 sm:text-6xl">
                Five portfolios.
                <br />
                <span className="italic text-ink-700">Compared side-by-side.</span>
              </h1>
              <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-ink-600">
                Each analyst proposes their highest-conviction long-term book. The consensus view shows where the desk
                agrees — and where it doesn't.
              </p>
            </div>
            <div className="flex items-center gap-2 text-xs text-ink-500">
              <span>As of</span>
              <span className="num rounded-full bg-ink-900/[0.05] px-2.5 py-1 text-ink-700">
                {loading ? "loading…" : (asOfDisplay ?? "awaiting batch")}
              </span>
            </div>
          </div>
        </div>
      </section>

      <section className="py-10">
        <div className="mx-auto max-w-7xl px-6">
          <Tabs defaultValue="by-persona">
            <TabsList>
              <TabsTrigger value="by-persona">
                <Sparkles className="mr-1.5 h-3.5 w-3.5" /> By analyst
              </TabsTrigger>
              <TabsTrigger value="consensus">
                <Users className="mr-1.5 h-3.5 w-3.5" /> Consensus
              </TabsTrigger>
            </TabsList>

            <TabsContent value="by-persona">
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
                {PERSONAS.map((persona) => {
                  const a = ACCENT_CLASS[persona.accent];
                  const prop = proposals[persona.id];
                  const positions = prop?.positions ?? [];
                  const active = positions.filter((p) => p.weight >= ACTIVE_THRESHOLD);
                  const watchlist = positions.filter((p) => p.weight < ACTIVE_THRESHOLD);
                  const combined = [...active, ...watchlist];
                  const expanded = expandedCards.has(persona.id);
                  return (
                    <div
                      key={persona.id}
                      className="flex flex-col overflow-hidden rounded-3xl border border-ink-900/[0.06] bg-cream-50"
                    >
                      <div className="border-b border-ink-900/[0.06] p-5">
                        <div className="flex items-center gap-2">
                          <div className={cn("h-1.5 w-1.5 rounded-full", a.dot)} />
                          <span className="text-[10px] font-medium uppercase tracking-[0.16em] text-ink-500">
                            {persona.archetype}
                          </span>
                        </div>
                        <div className="mt-1 flex items-baseline justify-between gap-2">
                          <button
                            type="button"
                            onClick={() => setOpenId(persona.id)}
                            className="group/name inline-flex items-baseline gap-1.5 text-left ring-focus rounded-md"
                            aria-label={`Open ${persona.name}'s thesis`}
                          >
                            <h3 className="display-serif text-2xl text-ink-900 group-hover/name:text-ink-700">{persona.name}</h3>
                            <ArrowUpRight className="h-4 w-4 -translate-y-0.5 text-ink-400 transition-transform group-hover/name:translate-x-0.5 group-hover/name:text-ink-600" />
                          </button>
                          <Badge tone={persona.accent === "ink" ? "default" : persona.accent}>
                            {persona.riskLabel}
                          </Badge>
                        </div>
                        <div className="mt-4 grid grid-cols-2 gap-3 text-[11px]">
                          <Stat label="Horizon" value={prop?.horizon || persona.horizon} />
                          <Stat label="Cash" value={prop ? fmt.pctAbs(prop.cashWeight ?? 0) : "—"} />
                        </div>
                        <div className="mt-4">
                          <FollowButton personaId={persona.id} personaName={persona.name} />
                        </div>
                      </div>

                      <div className="flex-1 divide-y divide-ink-900/[0.05]">
                        {loading && !prop ? (
                          <div className="space-y-px">
                            {[0, 1, 2].map((i) => (
                              <div key={i} className="h-20 animate-pulse bg-ink-900/[0.02]" />
                            ))}
                          </div>
                        ) : combined.length === 0 ? (
                          <div className="px-5 py-6 text-center text-xs text-ink-500">
                            No positions published yet for {persona.name}.
                          </div>
                        ) : (
                          combined.map((pos, i) => {
                            const isWatch = pos.weight < ACTIVE_THRESHOLD;
                            const showWatchHeader =
                              isWatch && i === active.length && active.length > 0;
                            // Mobile: show only the first 3 until the card is expanded.
                            const hideOnMobile = i >= 3 && !expanded;
                            return (
                              <Fragment key={pos.ticker}>
                                {showWatchHeader && (
                                  <div className={cn("border-t-2 border-dashed border-ink-900/[0.08] bg-ink-900/[0.02] px-5 py-2", hideOnMobile && "hidden sm:block")}>
                                    <div className="text-[10px] uppercase tracking-[0.16em] text-ink-500">
                                      Watchlist · not buying now
                                    </div>
                                  </div>
                                )}
                              <div
                                onMouseEnter={() => setHighlight(pos.ticker)}
                                onMouseLeave={() => setHighlight(null)}
                                className={cn(
                                  "transition-colors",
                                  isWatch && "opacity-55",
                                  hideOnMobile && "hidden sm:block",
                                  highlight === pos.ticker
                                    ? "bg-coral-50"
                                    : "hover:bg-ink-900/[0.025]",
                                )}
                              >
                                <button
                                  onClick={() => setModalPos({ ticker: pos.ticker, name: pos.name, accentText: ACCENT_CLASS[persona.accent].text })}
                                  className="block w-full text-left px-5 py-3"
                                >
                                  <div className="flex items-center justify-between gap-3">
                                    <div className="min-w-0 flex-1">
                                      <div className="flex items-center gap-2">
                                        <span className="num text-sm font-medium text-ink-900">
                                          {pos.ticker}
                                        </span>
                                        <span className="truncate text-xs text-ink-500">{pos.name}</span>
                                      </div>
                                    </div>
                                    <span className="num text-sm font-medium text-ink-800">
                                      {fmt.pctAbs(pos.weight)}
                                    </span>
                                    <ArrowUpRight className="h-3.5 w-3.5 text-ink-400" />
                                  </div>
                                  <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-ink-900/[0.05]">
                                    <div
                                      className="h-full rounded-full"
                                      style={{
                                        width: `${pos.weight * 500}%`,
                                        maxWidth: "100%",
                                        background: ACCENT_HEX[persona.accent],
                                        opacity: 0.55 + (pos.conviction ?? 0.5) * 0.45,
                                      }}
                                    />
                                  </div>
                                  <p className="mt-2 line-clamp-2 text-[12px] leading-relaxed text-ink-600">
                                    {pos.thesis}
                                  </p>
                                </button>
                              </div>
                              </Fragment>
                            );
                          })
                        )}
                        {combined.length > 3 && (
                          <button
                            type="button"
                            onClick={() => toggleCard(persona.id)}
                            className="block w-full px-5 py-2.5 text-center text-xs font-medium text-ink-600 hover:bg-ink-900/[0.03] sm:hidden"
                          >
                            {expanded ? "Show fewer" : `Show all ${combined.length} positions`}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </TabsContent>

            <TabsContent value="consensus">
              <div className="overflow-hidden rounded-3xl border border-ink-900/[0.06] bg-cream-50">
                <div className="grid border-b border-ink-900/[0.06] bg-ink-900/[0.025] px-3 py-3 text-[10px] uppercase tracking-[0.14em] text-ink-500 sm:px-5" style={{ gridTemplateColumns: consensusGrid }}>
                  <div className="uppercase tracking-[0.14em]">Ticker</div>
                  {PERSONAS.map((p) => (
                    <div key={p.id} className="flex items-center gap-1.5">
                      <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: ACCENT_HEX[p.accent] }} />
                      <span className="truncate">{p.name}</span>
                    </div>
                  ))}
                  {!isMobile && (
                    <div className="text-right uppercase tracking-[0.14em]">Avg conv.</div>
                  )}
                </div>

                {loading ? (
                  <div className="space-y-px">
                    {[0, 1, 2, 3, 4].map((i) => (
                      <div key={i} className="h-12 animate-pulse bg-ink-900/[0.02]" />
                    ))}
                  </div>
                ) : consensus.length === 0 ? (
                  <div className="px-5 py-8 text-center text-sm text-ink-500">
                    No proposals published yet. Cron runs Friday close.
                  </div>
                ) : (
                  consensus.map((row) => {
                    const mentionsByPersona = Object.fromEntries(
                      row.mentions.map((m) => [m.personaId, m]),
                    );
                    const mentionCount = row.mentions.length;
                    return (
                      <div
                        key={row.ticker}
                        role="button"
                        tabIndex={0}
                        onClick={() => setModalPos({ ticker: row.ticker, name: row.name, accentText: "text-ink-700" })}
                        style={{ gridTemplateColumns: consensusGrid }}
                        className={cn(
                          "grid cursor-pointer border-b border-ink-900/[0.05] px-3 py-3.5 last:border-b-0 transition-colors hover:bg-ink-900/[0.02] sm:px-5",
                          mentionCount >= 3 ? "bg-coral-50/50" : mentionCount === 2 && "bg-coral-50/25",
                        )}
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="num text-sm font-medium text-ink-900">{row.ticker}</div>
                          <div className="hidden truncate text-xs text-ink-500 sm:block">{row.name}</div>
                          {mentionCount >= 2 && (
                            <span title={`${mentionCount} analysts hold this name`} className="ml-auto sm:ml-0">
                              <Badge tone="coral" className="inline-flex items-center gap-1">
                                <Users className="h-3 w-3" /> {mentionCount}
                              </Badge>
                            </span>
                          )}
                        </div>
                        {PERSONAS.map((p) => {
                          const m = mentionsByPersona[p.id];
                          if (!m) return <div key={p.id} className="text-xs text-ink-300">—</div>;
                          return (
                            <div key={p.id} className="num text-xs text-ink-700">
                              {fmt.pctAbs(m.weight)}
                              <div className="mt-1 h-[3px] overflow-hidden rounded-full bg-ink-900/[0.06]">
                                <div
                                  className="h-full rounded-full"
                                  style={{
                                    width: `${Math.min(m.weight * 400, 100)}%`,
                                    background: ACCENT_HEX[p.accent],
                                    opacity: 0.5 + (m.conviction ?? 0.5) * 0.5,
                                  }}
                                />
                              </div>
                            </div>
                          );
                        })}
                        {!isMobile && (
                          <div className="num text-right text-xs font-medium text-ink-800">
                            {row.avgConviction > 0 ? fmt.num(row.avgConviction, 2) : "—"}
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>

            </TabsContent>
          </Tabs>
        </div>
      </section>

      <PersonaDetailSheet
        persona={openId ? PERSONA_BY_ID[openId] : null}
        open={!!openId}
        onOpenChange={(o) => !o && setOpenId(null)}
      />

      {modalPos && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
          <button
            type="button"
            aria-label="Close"
            onClick={() => setModalPos(null)}
            className="absolute inset-0 bg-ink-900/40 backdrop-blur-sm animate-fade-up"
          />
          <div
            role="dialog"
            aria-modal="true"
            className="relative z-10 max-h-[85vh] w-full max-w-lg overflow-auto rounded-3xl border border-ink-900/10 bg-cream-50 p-5 shadow-[0_40px_90px_-30px_rgba(31,30,27,0.45)] animate-fade-up"
          >
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="flex items-baseline gap-2 min-w-0">
                <span className="num text-lg font-semibold text-ink-900">{modalPos.ticker}</span>
                <span className="truncate text-sm text-ink-500">{modalPos.name}</span>
              </div>
              <button
                type="button"
                onClick={() => setModalPos(null)}
                aria-label="Close"
                className="-mr-1 rounded-full p-1.5 text-ink-500 hover:bg-ink-900/[0.06] ring-focus"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-3">
              <PositionFeatures ticker={modalPos.ticker} open accent={modalPos.accentText} />
              <RelatedThesis
                ticker={modalPos.ticker}
                entries={thesisByTicker[modalPos.ticker.toUpperCase()] ?? []}
                loading={reportsLoading}
              />
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.14em] text-ink-500">{label}</div>
      <div className="num mt-0.5 text-sm font-medium text-ink-900">{value}</div>
    </div>
  );
}
