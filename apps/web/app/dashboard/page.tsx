"use client";
import { Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, Heart, MessageCircle, Repeat2, TrendingUp } from "lucide-react";
import { ACCENT_CLASS, PERSONAS, PERSONA_BY_ID, type Persona } from "@/lib/mock/personas";
import { rebase, splitSegments, usePerformance } from "@/lib/performance-data";
import { Header } from "@/components/header";
import { CumulativeChart } from "@/components/cumulative-chart";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { PersonaAvatar } from "@/components/persona-avatar";
import { cn, fmt, signClass } from "@/lib/utils";

const ACCENT_HEX: Record<Persona["accent"], string> = {
  coral: "#D97757", sage: "#6B8E6B", plum: "#8B6B8E", ink: "#1F1E1B",
};

// Mock user portfolio
const MY = {
  startingCapital: 100_000,
  followedPersona: "peter",
  startedOn: "2025-08-12",
  positions: [
    { ticker: "META", weight: 0.13, pnl: 0.082 },
    { ticker: "ANET", weight: 0.11, pnl: 0.041 },
    { ticker: "BKNG", weight: 0.10, pnl: -0.012 },
    { ticker: "ISRG", weight: 0.09, pnl: 0.056 },
    { ticker: "LRCX", weight: 0.10, pnl: 0.118 },
    { ticker: "TSM",  weight: 0.12, pnl: 0.091 },
    { ticker: "NOW",  weight: 0.09, pnl: 0.024 },
    { ticker: "DECK", weight: 0.08, pnl: -0.038 },
    { ticker: "URI",  weight: 0.10, pnl: 0.067 },
  ],
};

const SOCIAL = [
  { user: "nara_k", persona: "cathie", fork: "Cathie · ex-China", note: "Removed China exposure, tilted toward Nordic semis.", likes: 142, replies: 18, ret: 0.41 },
  { user: "ben.t",  persona: "warren", fork: "Warren · Dividend-only", note: "Filtered for yield > 2.5% and 10-yr div growth.", likes: 89, replies: 7, ret: 0.13 },
  { user: "min_su", persona: "ray",    fork: "Ray · Inflation hedged", note: "Doubled TIPS allocation; cut nominal duration.", likes: 56, replies: 4, ret: 0.07 },
  { user: "alex.r", persona: "peter",  fork: "Peter · Industrials focus", note: "Concentrated GARP in re-shoring beneficiaries.", likes: 211, replies: 24, ret: 0.22 },
];

export default function DashboardPage() {
  return (
    <Suspense fallback={null}>
      <DashboardInner />
    </Suspense>
  );
}

const VALID_TABS = ["portfolio", "leaderboard", "social"] as const;

function DashboardInner() {
  const params = useSearchParams();
  const router = useRouter();
  const raw = params.get("tab") ?? "portfolio";
  const tab = (VALID_TABS as readonly string[]).includes(raw) ? raw : "portfolio";

  const handleTabChange = (next: string) => {
    router.replace(next === "portfolio" ? "/dashboard" : `/dashboard?tab=${next}`, { scroll: false });
  };

  const followed = PERSONA_BY_ID[MY.followedPersona];
  const pnlPct = MY.positions.reduce((s, p) => s + p.weight * p.pnl, 0);
  const value = MY.startingCapital * (1 + pnlPct);
  // Real paper-track data: followed persona's curve for the portfolio
  // tab, all four personas' metrics for the leaderboard.
  const personaIds = PERSONAS.map((p) => p.id);
  const { perf, benchmark } = usePerformance(personaIds);
  const followedPerf = perf[MY.followedPersona] ?? null;
  const followedSegments = followedPerf ? splitSegments(followedPerf) : null;
  // Last ~180 trading days, re-based so the window starts at 0%.
  const series = followedPerf
    ? rebase(
        followedPerf.series
          .slice(-180)
          .map((s, i) => ({ day: i, date: s.date, value: s.value })),
      )
    : [];
  const bench180 = benchmark ? rebase(benchmark.slice(-180)) : null;
  const followedHypDays = followedSegments?.hyp.length ?? 0;

  return (
    <main className="min-h-screen">
      <Header variant="solid" />

      <section className="border-b border-ink-900/[0.06] bg-cream-50/40 py-10">
        <div className="mx-auto max-w-7xl px-6">
          <Link href="/" className="inline-flex items-center gap-1.5 text-xs text-ink-500 hover:text-ink-800">
            <ArrowLeft className="h-3.5 w-3.5" /> Back to the desk
          </Link>
          <div className="mt-3 flex items-end justify-between gap-6">
            <div>
              <div className="text-xs font-medium uppercase tracking-[0.18em] text-coral-600">Your account</div>
              <h1 className="display-serif mt-2 text-5xl tracking-tightest text-ink-900">Dashboard</h1>
              <p className="mt-2 text-sm text-ink-600">
                Paper portfolio · Following{" "}
                <span className="font-medium text-ink-800">{followed.name}</span> since{" "}
                <span className="num">{MY.startedOn}</span>
              </p>
            </div>
            <div className="text-right">
              <div className="text-[10px] uppercase tracking-[0.16em] text-ink-500">Portfolio value</div>
              <div className="num mt-1 text-4xl font-medium text-ink-900">
                ${value.toLocaleString("en-US", { maximumFractionDigits: 0 })}
              </div>
              <div className={cn("num mt-0.5 text-sm", signClass(pnlPct))}>
                {fmt.pct(pnlPct)} all-time
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="py-10">
        <div className="mx-auto max-w-7xl px-6">
          <Tabs value={tab} onValueChange={handleTabChange}>
            <TabsList>
              <TabsTrigger value="portfolio">My portfolio</TabsTrigger>
              <TabsTrigger value="leaderboard">Leaderboard</TabsTrigger>
              <TabsTrigger value="social">Social</TabsTrigger>
            </TabsList>

            {/* ───── PORTFOLIO ───── */}
            <TabsContent value="portfolio">
              <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
                <div className="rounded-3xl border border-ink-900/[0.06] bg-cream-50 p-6">
                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <div className="text-xs uppercase tracking-[0.16em] text-ink-500">Last 180 days · paper</div>
                      <h2 className="display-serif mt-1 text-2xl text-ink-900">Performance vs benchmark</h2>
                    </div>
                  </div>
                  {series.length > 1 ? (
                    <CumulativeChart
                      height={280}
                      series={[
                        { id: followed.id, name: "You", color: ACCENT_HEX[followed.accent], data: series },
                        ...(bench180
                          ? [{ id: "sp500", name: "S&P 500", color: "#A8A39A", data: bench180, dashed: true }]
                          : []),
                      ]}
                    />
                  ) : (
                    <div className="h-[280px] w-full animate-pulse rounded-2xl bg-ink-900/[0.04]" />
                  )}
                  {followedHypDays > 0 && (
                    <p className="mt-2 text-[11px] text-ink-500">
                      Includes {followed.name}&apos;s hypothetical backfill (current
                      book projected backwards) before Jun 11, 2026 — the live paper
                      track starts there. Positions below are Phase-D demo data.
                    </p>
                  )}
                </div>

                <div className="space-y-4">
                  <Tile label="Starting capital" value={`$${MY.startingCapital.toLocaleString()}`} />
                  <Tile label="Following" value={followed.name} sub={followed.archetype} />
                  <Tile label="Open positions" value={`${MY.positions.length}`} />
                  <Tile label="Cash" value="$8,000" sub="8% allocation" />
                </div>
              </div>

              <div className="mt-4 overflow-hidden rounded-3xl border border-ink-900/[0.06] bg-cream-50">
                <div className="grid grid-cols-[1fr_1fr_1fr_1fr] border-b border-ink-900/[0.06] bg-ink-900/[0.025] px-5 py-3 text-[10px] uppercase tracking-[0.14em] text-ink-500">
                  <div>Ticker</div>
                  <div>Weight</div>
                  <div>Position P&L</div>
                  <div className="text-right">Contribution</div>
                </div>
                {MY.positions.map((p) => (
                  <div key={p.ticker} className="grid grid-cols-[1fr_1fr_1fr_1fr] border-b border-ink-900/[0.05] px-5 py-3.5 last:border-b-0 hover:bg-ink-900/[0.02]">
                    <div className="num text-sm font-medium text-ink-900">{p.ticker}</div>
                    <div className="num text-sm text-ink-700">{fmt.pctAbs(p.weight)}</div>
                    <div className={cn("num text-sm", signClass(p.pnl))}>{fmt.pct(p.pnl)}</div>
                    <div className={cn("num text-right text-sm", signClass(p.weight * p.pnl))}>
                      {fmt.pct(p.weight * p.pnl, 2)}
                    </div>
                  </div>
                ))}
              </div>
            </TabsContent>

            {/* ───── LEADERBOARD ───── */}
            <TabsContent value="leaderboard">
              <div className="overflow-hidden rounded-3xl border border-ink-900/[0.06] bg-cream-50">
                <div className="grid grid-cols-[40px_1.4fr_1fr_1fr_1fr_1fr_1fr] border-b border-ink-900/[0.06] bg-ink-900/[0.025] px-5 py-3 text-[10px] uppercase tracking-[0.14em] text-ink-500">
                  <div>#</div><div>Analyst</div><div>1y †</div><div>90d</div><div>Sharpe 30d</div><div>MDD 30d</div><div className="text-right">Value</div>
                </div>
                {[...PERSONAS]
                  .sort((a, b) =>
                    (perf[b.id]?.metrics?.return1y ?? -Infinity) -
                    (perf[a.id]?.metrics?.return1y ?? -Infinity))
                  .map((p, i) => {
                    const pm = perf[p.id]?.metrics ?? null;
                    return (
                      <div key={p.id} className="grid grid-cols-[40px_1.4fr_1fr_1fr_1fr_1fr_1fr] items-center border-b border-ink-900/[0.05] px-5 py-4 last:border-b-0 hover:bg-ink-900/[0.02]">
                        <div className="num text-xs text-ink-400">{(i + 1).toString().padStart(2, "0")}</div>
                        <div className="flex items-center gap-3">
                          <PersonaAvatar persona={p} size="xs" />
                          <div>
                            <div className="text-sm font-medium text-ink-900">{p.name}</div>
                            <div className="text-[11px] text-ink-500">{p.archetype}</div>
                          </div>
                        </div>
                        <div className={cn("num text-sm", pm?.return1y != null ? signClass(pm.return1y) : "text-ink-400")}>
                          {pm?.return1y != null ? fmt.pct(pm.return1y) : "—"}
                        </div>
                        <div className={cn("num text-sm", pm?.return90d != null ? signClass(pm.return90d) : "text-ink-400")}>
                          {pm?.return90d != null ? fmt.pct(pm.return90d) : "—"}
                        </div>
                        <div className="num text-sm text-ink-800">
                          {pm?.sharpe30d != null ? fmt.num(pm.sharpe30d) : "—"}
                        </div>
                        <div className={cn("num text-sm", pm?.mdd30d != null ? signClass(-pm.mdd30d) : "text-ink-400")}>
                          {pm?.mdd30d != null ? fmt.pct(-pm.mdd30d) : "—"}
                        </div>
                        <div className="num text-right text-sm text-ink-800">
                          {pm?.totalValue != null
                            ? `$${pm.totalValue.toLocaleString("en-US", { maximumFractionDigits: 0 })}`
                            : "—"}
                        </div>
                      </div>
                    );
                  })}
              </div>
              <p className="mt-3 text-[11px] text-ink-500">
                † 1y blends the hypothetical backfill (current book projected
                backwards — look-ahead bias) with the live paper track that
                started Jun 11, 2026. Sharpe/MDD are 30-day trailing on paper
                NAV. Hit rate lands once closed-lot tracking ships.
              </p>
            </TabsContent>

            {/* ───── SOCIAL ───── */}
            <TabsContent value="social">
              <div className="grid gap-4 md:grid-cols-2">
                {SOCIAL.map((post) => {
                  const persona = PERSONA_BY_ID[post.persona];
                  const a = ACCENT_CLASS[persona.accent];
                  return (
                    <article key={post.fork} className="rounded-3xl border border-ink-900/[0.06] bg-cream-50 p-6">
                      <div className="flex items-center gap-3">
                        <div className="grid h-9 w-9 place-items-center rounded-full bg-gradient-to-br from-coral-400 to-plum-500 text-cream-50 text-xs font-semibold">
                          {post.user[0].toUpperCase()}
                        </div>
                        <div>
                          <div className="text-sm font-medium text-ink-900">@{post.user}</div>
                          <div className="flex items-center gap-1.5 text-[11px] text-ink-500">
                            <Repeat2 className="h-3 w-3" />
                            forked
                            <span className={cn("inline-flex items-center gap-1 font-medium", a.text)}>
                              <span className={cn("h-1.5 w-1.5 rounded-full", a.dot)} /> {persona.name}
                            </span>
                          </div>
                        </div>
                        <div className={cn("ml-auto inline-flex items-center gap-1 text-sm num font-medium", signClass(post.ret))}>
                          <TrendingUp className="h-3.5 w-3.5" /> {fmt.pct(post.ret)}
                        </div>
                      </div>
                      <h3 className="display-serif mt-4 text-xl text-ink-900">{post.fork}</h3>
                      <p className="mt-1.5 text-sm leading-relaxed text-ink-600">{post.note}</p>
                      <div className="mt-5 flex items-center gap-5 text-xs text-ink-500">
                        <span className="inline-flex items-center gap-1.5"><Heart className="h-3.5 w-3.5" /> {post.likes}</span>
                        <span className="inline-flex items-center gap-1.5"><MessageCircle className="h-3.5 w-3.5" /> {post.replies}</span>
                        <Badge tone="default" className="ml-auto">Copy fork</Badge>
                      </div>
                    </article>
                  );
                })}
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </section>
    </main>
  );
}

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-2xl border border-ink-900/[0.06] bg-cream-50 px-5 py-4">
      <div className="text-[10px] uppercase tracking-[0.16em] text-ink-500">{label}</div>
      <div className="num mt-1 text-xl font-medium text-ink-900">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-ink-500">{sub}</div>}
    </div>
  );
}
