"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, Briefcase, MessageCircle, Sparkles, Target, TrendingUp } from "lucide-react";
import { ACCENT_CLASS, type Persona } from "@/lib/mock/personas";
import { SERIES, BENCHMARK } from "@/lib/mock/performance";
import { fetchProposal, fetchReports } from "@/lib/analyst-data";
import type { Proposal, Report } from "@/lib/thesis-types";
import { Sheet, SheetContent } from "./ui/sheet";
import { CumulativeChart } from "./cumulative-chart";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { ReportList } from "./report-list";
import { AnalystChat } from "./analyst-chat";
import { PersonaAvatar } from "./persona-avatar";
import { cn, fmt, signClass } from "@/lib/utils";

type ViewMode = "thesis" | "chat";

const ACCENT_HEX: Record<Persona["accent"], string> = {
  coral: "#D97757",
  sage: "#6B8E6B",
  plum: "#8B6B8E",
  ink: "#1F1E1B",
};

export function PersonaDetailSheet({
  persona,
  open,
  onOpenChange,
}: {
  persona: Persona | null;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const [view, setView] = useState<ViewMode>("thesis");
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [loadingData, setLoadingData] = useState(false);

  // Reset to thesis view whenever a new persona opens
  useEffect(() => {
    if (persona) setView("thesis");
  }, [persona?.id]);

  // Fetch live reports + proposal whenever the sheet opens for a persona.
  // Uses AbortController so a rapid persona switch cancels the in-flight
  // request rather than racing two responses into state.
  useEffect(() => {
    if (!persona || !open) return;
    const ctrl = new AbortController();
    setLoadingData(true);
    setProposal(null);
    setReports([]);
    Promise.all([
      fetchProposal(persona.id, { signal: ctrl.signal }),
      fetchReports(persona.id, { limit: 5, signal: ctrl.signal }),
    ])
      .then(([p, r]) => {
        if (ctrl.signal.aborted) return;
        setProposal(p);
        setReports(r);
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoadingData(false);
      });
    return () => ctrl.abort();
  }, [persona?.id, open]);

  if (!persona) return null;
  const a = ACCENT_CLASS[persona.accent];
  const m = persona.metrics;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent>
        <div className="flex h-full flex-col">
          {/* ── HEADER (always visible) ── */}
          <div className="shrink-0 border-b border-ink-900/[0.06] px-8 pt-10 pb-5">
            <div className="flex items-start gap-5">
              <PersonaAvatar persona={persona} size="xl" ring />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <div className={cn("h-1.5 w-1.5 rounded-full", a.dot)} />
                  <span className="text-xs font-medium uppercase tracking-[0.14em] text-ink-500">
                    {persona.archetype} · Age {persona.age}
                  </span>
                </div>
                <div className="mt-1 flex items-baseline justify-between gap-4">
                  <h2 className="display-serif text-5xl text-ink-900">{persona.name}</h2>
                  <Badge tone={persona.accent === "ink" ? "default" : persona.accent}>{persona.riskLabel}</Badge>
                </div>
              </div>
            </div>
            <p className="mt-4 max-w-prose text-[14px] leading-relaxed text-ink-700">{persona.philosophy}</p>

            {/* View toggle */}
            <div className="mt-5 inline-flex h-9 items-center gap-1 rounded-full bg-ink-900/[0.05] p-1 text-sm">
              <ToggleBtn active={view === "thesis"} onClick={() => setView("thesis")}>
                <Sparkles className="h-3.5 w-3.5" /> Thesis
              </ToggleBtn>
              <ToggleBtn active={view === "chat"} onClick={() => setView("chat")}>
                <MessageCircle className="h-3.5 w-3.5" /> Chat with {persona.name}
              </ToggleBtn>
            </div>
          </div>

          {/* ── BODY (mode-dependent) ── */}
          {view === "chat" ? (
            <div className="min-h-0 flex-1">
              <AnalystChat persona={persona} />
            </div>
          ) : (
          <div className="min-h-0 flex-1 overflow-y-auto">

          <div className="mt-8 grid grid-cols-4 gap-px overflow-hidden border-y border-ink-900/[0.06] bg-ink-900/[0.06]">
            {[
              { l: "1-year return", v: fmt.pct(m.return1y), s: m.return1y },
              { l: "Sharpe (1y)", v: fmt.num(m.sharpe) },
              { l: "Max drawdown", v: fmt.pct(m.mdd), s: m.mdd },
              { l: "Hit rate", v: fmt.pctAbs(m.hitRate) },
            ].map((s, i) => (
              <div key={i} className="bg-cream-50 px-4 py-4">
                <div className="text-[10px] uppercase tracking-[0.16em] text-ink-500">{s.l}</div>
                <div className={cn("num mt-1.5 text-xl font-medium", s.s !== undefined ? signClass(s.s) : "text-ink-900")}>{s.v}</div>
              </div>
            ))}
          </div>

          <div className="px-8 py-8">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-medium text-ink-900">Cumulative return · last 365 days</h3>
              <div className="flex items-center gap-3 text-[11px] text-ink-500">
                <Legend color={ACCENT_HEX[persona.accent]} label={persona.name} />
                <Legend color="#A8A39A" label="S&P 500" dashed />
              </div>
            </div>
            <div className="rounded-2xl border border-ink-900/[0.06] bg-cream-50 p-3">
              <CumulativeChart
                height={220}
                series={[
                  { id: persona.id, name: persona.name, color: ACCENT_HEX[persona.accent], data: SERIES[persona.id] },
                  { id: "sp500", name: "S&P 500", color: "#A8A39A", data: BENCHMARK, dashed: true },
                ]}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 px-8">
            <InfoTile icon={<Target className="h-4 w-4" />} label="Horizon" value={persona.horizon} />
            <InfoTile icon={<TrendingUp className="h-4 w-4" />} label="Avg holding" value={m.avgHold} />
            <InfoTile icon={<Briefcase className="h-4 w-4" />} label="Turnover" value={m.turnover} />
            <InfoTile icon={<Sparkles className="h-4 w-4" />} label="Conviction floor" value="0.65 +" />
          </div>

          <div className="px-8 py-8">
            <h3 className="mb-3 text-sm font-medium text-ink-900">Signature signals</h3>
            <ul className="space-y-2">
              {persona.signature.map((s) => (
                <li key={s} className="flex items-center gap-3 rounded-xl border border-ink-900/[0.06] bg-cream-50 px-4 py-3 text-sm text-ink-700">
                  <span className={cn("h-1.5 w-1.5 rounded-full", a.dot)} />
                  {s}
                </li>
              ))}
            </ul>
          </div>

          <div className="border-t border-ink-900/[0.06] bg-cream-100/40 px-8 py-8">
            <div className="mb-4 flex items-baseline justify-between">
              <div>
                <h3 className="text-sm font-medium text-ink-900">Recent reports</h3>
                <p className="mt-0.5 text-xs text-ink-500">
                  How {persona.name} writes, what {persona.name} watches.
                </p>
              </div>
              <span className="num text-[11px] text-ink-500">
                {loadingData ? "loading…" : `${reports.length} on file`}
              </span>
            </div>
            {loadingData ? (
              <div className="space-y-2">
                <div className="h-16 animate-pulse rounded-xl bg-ink-900/[0.04]" />
                <div className="h-16 animate-pulse rounded-xl bg-ink-900/[0.04]" />
              </div>
            ) : reports.length === 0 ? (
              <p className="rounded-xl border border-dashed border-ink-900/10 bg-cream-50 px-4 py-6 text-center text-xs text-ink-500">
                No published reports yet. {persona.name}'s next batch runs Friday close.
              </p>
            ) : (
              <ReportList reports={reports} persona={persona} />
            )}
          </div>

          <div className="px-8 pb-8 pt-8">
            <h3 className="mb-3 text-sm font-medium text-ink-900">
              Latest portfolio · {proposal?.positions.length ?? 0} positions
            </h3>
            {loadingData ? (
              <div className="space-y-2">
                <div className="h-14 animate-pulse rounded-xl bg-ink-900/[0.04]" />
                <div className="h-14 animate-pulse rounded-xl bg-ink-900/[0.04]" />
                <div className="h-14 animate-pulse rounded-xl bg-ink-900/[0.04]" />
              </div>
            ) : !proposal || proposal.positions.length === 0 ? (
              <p className="rounded-xl border border-dashed border-ink-900/10 bg-cream-50 px-4 py-6 text-center text-xs text-ink-500">
                Portfolio not yet published. Comes online with the next cron.
              </p>
            ) : (
              <div className="overflow-hidden rounded-2xl border border-ink-900/[0.06] bg-cream-50">
                {proposal.positions.slice(0, 5).map((pos) => (
                  <div key={pos.ticker} className="flex items-center justify-between gap-4 border-b border-ink-900/[0.05] px-4 py-3 last:border-b-0">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="num text-sm font-medium text-ink-900">{pos.ticker}</span>
                        <span className="truncate text-xs text-ink-500">{pos.name}</span>
                      </div>
                      <p className="mt-0.5 line-clamp-1 text-xs text-ink-500">{pos.sector}</p>
                    </div>
                    <div className="text-right">
                      <div className="num text-sm font-medium text-ink-900">{fmt.pctAbs(pos.weight)}</div>
                      {pos.conviction !== null && (
                        <div className="num text-[10px] text-ink-500">
                          conv {fmt.num(pos.conviction, 2)}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="sticky bottom-0 mt-auto border-t border-ink-900/[0.06] bg-cream-50/95 px-8 py-4 backdrop-blur">
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs text-ink-500">
                {proposal?.asOf ? (
                  <>As of <span className="num text-ink-700">{proposal.asOf}</span></>
                ) : (
                  "Awaiting next batch"
                )}
              </span>
              <Link href={`/proposals?focus=${persona.id}`}>
                <Button variant="primary" size="md">
                  See in proposals
                  <ArrowUpRight className="h-4 w-4" />
                </Button>
              </Link>
            </div>
          </div>
          </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function ToggleBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex h-7 items-center gap-1.5 rounded-full px-3 text-xs font-medium transition-colors ring-focus",
        active ? "bg-cream-50 text-ink-900 shadow-sm" : "text-ink-600 hover:text-ink-900"
      )}
    >
      {children}
    </button>
  );
}

function InfoTile({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-ink-900/[0.06] bg-cream-50 px-4 py-3">
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.16em] text-ink-500">
        <span className="text-ink-400">{icon}</span>
        {label}
      </div>
      <div className="mt-1 text-sm font-medium text-ink-900">{value}</div>
    </div>
  );
}

function Legend({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className="h-[2px] w-4"
        style={{
          background: dashed ? `repeating-linear-gradient(90deg, ${color} 0 4px, transparent 4px 8px)` : color,
        }}
      />
      {label}
    </span>
  );
}
