"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Sparkles, Users } from "lucide-react";
import { PERSONAS, ACCENT_CLASS, type Persona } from "@/lib/mock/personas";
import { PROPOSALS, CONSENSUS } from "@/lib/mock/proposals";
import { Header } from "@/components/header";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { cn, fmt, signClass } from "@/lib/utils";

const ACCENT_HEX: Record<Persona["accent"], string> = {
  coral: "#D97757", sage: "#6B8E6B", plum: "#8B6B8E", ink: "#1F1E1B",
};

export default function ProposalsPage() {
  const [highlight, setHighlight] = useState<string | null>(null);

  const byPersona = useMemo(() => {
    const m: Record<string, typeof PROPOSALS[number]> = {};
    PROPOSALS.forEach((p) => (m[p.personaId] = p));
    return m;
  }, []);

  return (
    <main className="min-h-screen">
      <Header variant="solid" />

      <section className="border-b border-ink-900/[0.06] bg-cream-50/40 py-12">
        <div className="mx-auto max-w-7xl px-6">
          <Link href="/" className="inline-flex items-center gap-1.5 text-xs text-ink-500 hover:text-ink-800">
            <ArrowLeft className="h-3.5 w-3.5" /> Back to the desk
          </Link>
          <div className="mt-4 flex flex-col items-start justify-between gap-6 lg:flex-row lg:items-end">
            <div>
              <div className="text-xs font-medium uppercase tracking-[0.18em] text-coral-600">Today's research</div>
              <h1 className="display-serif mt-3 text-5xl tracking-tightest text-ink-900 sm:text-6xl">
                Four portfolios.
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
              <span className="num rounded-full bg-ink-900/[0.05] px-2.5 py-1 text-ink-700">{PROPOSALS[0].asOf}</span>
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

            {/* ───────── BY PERSONA: 4 columns side-by-side ───────── */}
            <TabsContent value="by-persona">
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                {PERSONAS.map((persona) => {
                  const a = ACCENT_CLASS[persona.accent];
                  const prop = byPersona[persona.id];
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
                          <h3 className="display-serif text-2xl text-ink-900">{persona.name}</h3>
                          <Badge tone={persona.accent === "ink" ? "default" : persona.accent}>
                            {persona.riskLabel}
                          </Badge>
                        </div>
                        <div className="mt-4 grid grid-cols-3 gap-3 text-[11px]">
                          <Stat label="E[R] 1y" value={fmt.pct(prop.expectedReturn)} sign={prop.expectedReturn} />
                          <Stat label="E[Vol]" value={fmt.pctAbs(prop.expectedVol)} />
                          <Stat label="Cash" value={fmt.pctAbs(prop.cashWeight)} />
                        </div>
                      </div>

                      <div className="flex-1 divide-y divide-ink-900/[0.05]">
                        {prop.positions.map((pos) => (
                          <button
                            key={pos.ticker}
                            onMouseEnter={() => setHighlight(pos.ticker)}
                            onMouseLeave={() => setHighlight(null)}
                            className={cn(
                              "block w-full text-left px-5 py-3 transition-colors",
                              highlight === pos.ticker ? "bg-coral-50" : "hover:bg-ink-900/[0.025]"
                            )}
                          >
                            <div className="flex items-center justify-between gap-3">
                              <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-2">
                                  <span className="num text-sm font-medium text-ink-900">{pos.ticker}</span>
                                  <span className="truncate text-xs text-ink-500">{pos.name}</span>
                                </div>
                              </div>
                              <span className="num text-sm font-medium text-ink-800">{fmt.pctAbs(pos.weight)}</span>
                            </div>
                            <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-ink-900/[0.05]">
                              <div
                                className="h-full rounded-full"
                                style={{ width: `${pos.weight * 500}%`, maxWidth: "100%", background: ACCENT_HEX[persona.accent], opacity: 0.55 + pos.conviction * 0.45 }}
                              />
                            </div>
                            <p className="mt-2 line-clamp-2 text-[12px] leading-relaxed text-ink-600">
                              {pos.thesis}
                            </p>
                          </button>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </TabsContent>

            {/* ───────── CONSENSUS: where the desk agrees ───────── */}
            <TabsContent value="consensus">
              <div className="overflow-hidden rounded-3xl border border-ink-900/[0.06] bg-cream-50">
                <div className="grid grid-cols-[2fr_repeat(4,1fr)_1fr] border-b border-ink-900/[0.06] bg-ink-900/[0.025] px-5 py-3 text-[10px] uppercase tracking-[0.14em] text-ink-500">
                  <div>Ticker</div>
                  {PERSONAS.map((p) => (
                    <div key={p.id} className="flex items-center gap-1.5">
                      <span className="h-1.5 w-1.5 rounded-full" style={{ background: ACCENT_HEX[p.accent] }} />
                      {p.name}
                    </div>
                  ))}
                  <div className="text-right">Avg conv.</div>
                </div>

                {CONSENSUS.map((row) => {
                  const mentionsByPersona: Record<string, { weight: number; conviction: number } | undefined> =
                    Object.fromEntries(row.mentions.map((m) => [m.personaId, m]));
                  const mentionCount = row.mentions.length;
                  return (
                    <div
                      key={row.ticker}
                      className={cn(
                        "grid grid-cols-[2fr_repeat(4,1fr)_1fr] border-b border-ink-900/[0.05] px-5 py-3.5 last:border-b-0 transition-colors hover:bg-ink-900/[0.02]",
                        mentionCount >= 3 && "bg-coral-50/40"
                      )}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="num text-sm font-medium text-ink-900">{row.ticker}</div>
                        <div className="truncate text-xs text-ink-500">{row.name}</div>
                        {mentionCount >= 3 && (
                          <Badge tone="coral" className="ml-auto sm:ml-0">Consensus</Badge>
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
                                  opacity: 0.5 + m.conviction * 0.5,
                                }}
                              />
                            </div>
                          </div>
                        );
                      })}
                      <div className="num text-right text-xs font-medium text-ink-800">
                        {fmt.num(row.avgConviction, 2)}
                      </div>
                    </div>
                  );
                })}
              </div>

              <p className="mt-4 text-xs text-ink-500">
                Rows highlighted in coral are mentioned by 3 or more analysts — strong desk-wide signal.
              </p>
            </TabsContent>
          </Tabs>
        </div>
      </section>
    </main>
  );
}

function Stat({ label, value, sign }: { label: string; value: string; sign?: number }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.14em] text-ink-500">{label}</div>
      <div className={cn("num mt-0.5 text-sm font-medium", sign !== undefined ? signClass(sign) : "text-ink-900")}>
        {value}
      </div>
    </div>
  );
}
