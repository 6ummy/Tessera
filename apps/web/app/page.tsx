"use client";
import { useState } from "react";
import Link from "next/link";
import { ArrowDown, ArrowRight, ChevronRight, Database, FileText, GitBranch, ShieldCheck } from "lucide-react";
import { PERSONAS, PERSONA_BY_ID, type Persona } from "@/lib/mock/personas";
import { toPoints, usePerformance } from "@/lib/performance-data";
import { Header } from "@/components/header";
import { PersonaCard } from "@/components/persona-card";
import { PersonaDetailSheet } from "@/components/persona-detail-sheet";
import { CumulativeChart, type Series } from "@/components/cumulative-chart";
import { Button } from "@/components/ui/button";
import { fmt } from "@/lib/utils";

const ACCENT_HEX: Record<Persona["accent"], string> = {
  coral: "#D97757",
  sage: "#6B8E6B",
  plum: "#8B6B8E",
  ink: "#1F1E1B",
};

const PERSONA_IDS = PERSONAS.map((p) => p.id);

export default function Page() {
  const [openId, setOpenId] = useState<string | null>(null);
  const persona = openId ? PERSONA_BY_ID[openId] : null;
  const { perf, benchmark, loading } = usePerformance(PERSONA_IDS);

  // One solid line per persona — the full paper-track curve (product
  // decision 2026-06-12: no dashed split in the UI; the data-level
  // hypothetical flag stays in /api/performance for anything downstream).
  const heroSeries: Series[] = PERSONAS.flatMap((p) => {
    const data = perf[p.id];
    if (!data || data.series.length === 0) return [];
    return [{ id: p.id, name: p.name, color: ACCENT_HEX[p.accent], data: toPoints(data) }];
  });
  if (benchmark)
    heroSeries.push({ id: "sp500", name: "S&P 500", color: "#A8A39A", data: benchmark, dashed: true });

  return (
    <main className="min-h-screen">
      <Header variant="solid" />

      {/* ───────────────────────────── HERO ───────────────────────────── */}
      <section className="relative overflow-hidden pt-12 sm:pt-16">
        <div className="absolute inset-0 -z-10 opacity-[0.55]">
          <div className="absolute left-1/2 top-0 h-[640px] w-[1100px] -translate-x-1/2 rounded-full bg-[radial-gradient(closest-side,rgba(217,119,87,0.18),transparent_70%)]" />
        </div>

        <div className="mx-auto max-w-7xl px-6">
          <div className="mx-auto max-w-3xl text-center">
            <div className="inline-flex items-center gap-2 rounded-full border border-ink-900/10 bg-cream-50/70 px-3 py-1 text-xs text-ink-600 backdrop-blur animate-fade-up">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-coral-500/40" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-coral-500" />
              </span>
              AI analyst personas · Paper trading pilot
            </div>

            <h1 className="display-serif mt-6 text-[56px] leading-[1.02] tracking-tightest text-ink-900 sm:text-[72px] animate-fade-up">
              Four analysts.
              <br />
              <span className="italic text-ink-700">One conviction</span>{" "}
              <span className="text-coral-600">at a time.</span>
            </h1>

            <p className="mx-auto mt-6 max-w-xl text-[17px] leading-relaxed text-ink-600 animate-fade-up">
              Four <span className="font-medium text-ink-800">AI analysts</span>, each with their
              own philosophy and voice. Same market, four portfolios — follow the one that thinks
              like you.
            </p>

            <div className="mt-8 flex items-center justify-center gap-3 animate-fade-up">
              <a href="#analysts">
                <Button size="lg">
                  Meet the analysts
                  <ArrowDown className="h-4 w-4" />
                </Button>
              </a>
              <Link href="/proposals">
                <Button size="lg" variant="outline">
                  See today's proposals
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
            </div>
          </div>

          {/* Floating mini chart */}
          <div className="relative mx-auto mt-16 max-w-5xl">
            <div className="rounded-[28px] border border-ink-900/[0.06] bg-cream-50 p-6 shadow-[0_40px_80px_-30px_rgba(31,30,27,0.25)] animate-fade-up">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="text-xs uppercase tracking-[0.16em] text-ink-500">Cumulative return · 365 days · paper</div>
                  <div className="display-serif mt-1 text-2xl text-ink-900">All analysts vs S&amp;P 500</div>
                </div>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-ink-500">
                  {PERSONAS.map((p) => (
                    <span key={p.id} className="inline-flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full" style={{ background: ACCENT_HEX[p.accent] }} />
                      {p.name}
                    </span>
                  ))}
                  <span className="inline-flex items-center gap-1.5">
                    <span
                      className="h-[2px] w-3"
                      style={{ background: "repeating-linear-gradient(90deg, #A8A39A 0 4px, transparent 4px 8px)" }}
                    />
                    S&amp;P 500
                  </span>
                </div>
              </div>
              {loading || heroSeries.length === 0 ? (
                <div className="h-[260px] w-full animate-pulse rounded-2xl bg-ink-900/[0.04]" />
              ) : (
                <CumulativeChart height={260} series={heroSeries} />
              )}
              <p className="mt-3 text-[11px] leading-relaxed text-ink-500">
                Live paper track — real fills since{" "}
                <span className="font-medium text-ink-700">Jun 11, 2026</span>.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ─────────────────────────── ANALYSTS GRID ─────────────────────────── */}
      <section id="analysts" className="relative py-24 sm:py-32">
        <div className="mx-auto max-w-7xl px-6">
          <div className="flex flex-col items-start justify-between gap-6 sm:flex-row sm:items-end">
            <div className="max-w-2xl">
              <div className="text-xs font-medium uppercase tracking-[0.18em] text-coral-600">The Desk</div>
              <h2 className="display-serif mt-3 text-5xl tracking-tightest text-ink-900">
                Meet your analysts.
              </h2>
              <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-ink-600">
                Four philosophies, four voices. They read the same market and reach different
                conclusions. Tap any card for the full thesis and current book.
              </p>
            </div>
            <Link href="/proposals" className="group inline-flex items-center gap-2 text-sm font-medium text-ink-700 hover:text-ink-900">
              Compare today's proposals side-by-side
              <ChevronRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
          </div>

          <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {PERSONAS.map((p, i) => (
              <div
                key={p.id}
                className="animate-fade-up"
                style={{ animationDelay: `${i * 60}ms`, animationFillMode: "both" }}
              >
                <PersonaCard persona={p} onOpen={setOpenId} performance={perf[p.id]} />
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─────────────────────────── HOW IT WORKS (teaser) ─────────────────────────── */}
      <section className="relative border-t border-ink-900/[0.06] bg-cream-50/60 py-24">
        <div className="mx-auto max-w-5xl px-6">
          <div className="text-center">
            <div className="text-xs font-medium uppercase tracking-[0.18em] text-coral-600">The process</div>
            <h2 className="display-serif mt-3 text-5xl leading-[1.04] tracking-tightest text-ink-900">
              Research is the loop.
              <br />
              <span className="italic text-ink-700">You make the call.</span>
            </h2>
            <p className="mx-auto mt-5 max-w-lg text-[15px] leading-relaxed text-ink-600">
              The numbers are computed in code; the analysts write the thesis. Every position
              clears a deterministic risk gateway before you see it.
            </p>
          </div>

          <div className="mt-12 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MiniStep n={1} title="Ingest" icon={<Database className="h-4 w-4" />} desc="Fundamentals, filings, macro." />
            <MiniStep n={2} title="Analysts write" icon={<FileText className="h-4 w-4" />} desc="Four philosophies, four portfolios." />
            <MiniStep n={3} title="Compare side-by-side" icon={<GitBranch className="h-4 w-4" />} desc="See where the desk agrees — and disagrees." />
            <MiniStep n={4} title="Risk gateway" icon={<ShieldCheck className="h-4 w-4" />} desc="Deterministic safety checks." />
          </div>

          <div className="mt-10 flex justify-center">
            <Link href="/how-it-works">
              <Button variant="outline" size="lg">
                Read the full pipeline
                <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* ─────────────────────────── FOOTER ─────────────────────────── */}
      <footer className="border-t border-ink-900/[0.06] py-10">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-3 px-6 text-xs text-ink-500 sm:flex-row">
          <div className="flex items-center gap-2">
            <span className="display-serif text-base text-ink-700">Convt</span>
            <span>· Paper trading pilot · Not investment advice</span>
          </div>
          <div className="num">v0.1 · {fmt.num(PERSONAS.length, 0)} analysts on the desk</div>
        </div>
      </footer>

      <PersonaDetailSheet persona={persona} open={!!openId} onOpenChange={(o) => !o && setOpenId(null)} />
    </main>
  );
}

function MiniStep({ n, title, icon, desc }: { n: number; title: string; icon: React.ReactNode; desc: string }) {
  return (
    <div className="group rounded-2xl border border-ink-900/[0.06] bg-cream-50 p-5 transition-colors hover:border-ink-900/[0.12]">
      <div className="flex items-center justify-between">
        <div className="num text-xs text-ink-400">0{n}</div>
        <div className="grid h-8 w-8 place-items-center rounded-full bg-ink-900 text-cream-50">
          {icon}
        </div>
      </div>
      <h3 className="mt-4 text-sm font-medium text-ink-900">{title}</h3>
      <p className="mt-1 text-[13px] text-ink-600">{desc}</p>
    </div>
  );
}
