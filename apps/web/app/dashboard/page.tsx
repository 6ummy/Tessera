"use client";
import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, Heart, LogIn, MessageCircle, Repeat2, TrendingUp } from "lucide-react";
import { ACCENT_CLASS, PERSONAS, PERSONA_BY_ID, type Persona } from "@/lib/mock/personas";
import { rebase, usePerformance } from "@/lib/performance-data";
import { useAuth } from "@/lib/firebase/auth-context";
import { Header } from "@/components/header";
import { CumulativeChart } from "@/components/cumulative-chart";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { PersonaAvatar } from "@/components/persona-avatar";
import { cn, fmt, signClass } from "@/lib/utils";

const ACCENT_HEX: Record<Persona["accent"], string> = {
  coral: "#D97757", sage: "#6B8E6B", plum: "#8B6B8E", ink: "#1F1E1B",
};

type Portfolio = {
  personaId: string;
  startingCapital: number;
  currentCash: number;
  totalValue: number;
  positions: Record<string, { qty: number; close: number; value: number }>;
  startedAt: string;
};

// Social feed is still a Phase-D demo (labelled in the UI).
const SOCIAL = [
  { user: "nara_k", persona: "cathie", fork: "Cathie · ex-China", note: "Removed China exposure, tilted toward Nordic semis.", likes: 142, replies: 18, ret: 0.41 },
  { user: "ben.t",  persona: "warren", fork: "Warren · Dividend-only", note: "Filtered for yield > 2.5% and 10-yr div growth.", likes: 89, replies: 7, ret: 0.13 },
  { user: "min_su", persona: "ray",    fork: "Ray · Inflation hedged", note: "Doubled TIPS allocation; cut nominal duration.", likes: 56, replies: 4, ret: 0.07 },
  { user: "alex.r", persona: "peter",  fork: "Peter · Industrials focus", note: "Concentrated GARP in re-shoring beneficiaries.", likes: 211, replies: 24, ret: 0.22 },
];

/** Fetch the signed-in user's real paper portfolios (their follows). */
function useMyPortfolios() {
  const { user } = useAuth();
  const [portfolios, setPortfolios] = useState<Portfolio[] | null>(null);
  useEffect(() => {
    if (!user) { setPortfolios(null); return; }
    let cancelled = false;
    (async () => {
      try {
        const token = await user.getIdToken();
        const res = await fetch("/api/me/portfolios", { headers: { authorization: `Bearer ${token}` } });
        if (!res.ok || cancelled) return;
        const { portfolios } = (await res.json()) as { portfolios: Portfolio[] };
        if (!cancelled) setPortfolios(portfolios);
      } catch {
        if (!cancelled) setPortfolios([]);
      }
    })();
    return () => { cancelled = true; };
  }, [user]);
  return portfolios;
}

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

  const { configured, user, signInWithGoogle } = useAuth();
  const portfolios = useMyPortfolios();
  const hasFollows = !!portfolios && portfolios.length > 0;

  // Which followed persona is in focus (default: first follow).
  const [focusId, setFocusId] = useState<string | null>(null);
  const selected = useMemo<Portfolio | null>(() => {
    if (!portfolios || portfolios.length === 0) return null;
    return portfolios.find((p) => p.personaId === focusId) ?? portfolios[0];
  }, [portfolios, focusId]);

  // Real paper-track data: persona curves + leaderboard metrics.
  const personaIds = PERSONAS.map((p) => p.id);
  const { perf, benchmark } = usePerformance(personaIds);

  // Aggregate header figures across every follow.
  const totalValue = portfolios?.reduce((s, p) => s + p.totalValue, 0) ?? 0;
  const totalStarting = portfolios?.reduce((s, p) => s + p.startingCapital, 0) ?? 0;
  const aggReturn = totalStarting > 0 ? totalValue / totalStarting - 1 : 0;

  // Selected persona's curve, re-based to the follow's start date so it
  // reflects the user's actual holding window.
  const selectedPersona = selected ? PERSONA_BY_ID[selected.personaId] : null;
  const selPerf = selected ? perf[selected.personaId] ?? null : null;
  const series = useMemo(() => {
    if (!selPerf || !selected) return [];
    // ONLY the persona's track since your follow date — rebased to 0% at
    // follow. Before you followed you held cash (flat / nothing to show),
    // so a brand-new follow yields ≤1 point and we render the "building"
    // placeholder rather than back-painting the persona's prior history
    // as if it were yours.
    const start = selected.startedAt.slice(0, 10);
    const pts = selPerf.series
      .filter((s) => s.date >= start)
      .map((s, i) => ({ day: i, date: s.date, value: s.value }));
    return pts.length > 1 ? rebase(pts) : [];
  }, [selPerf, selected]);
  const bench180 = benchmark ? rebase(benchmark.slice(-180)) : null;

  const selectedPositions = useMemo(() => {
    if (!selected) return [];
    return Object.entries(selected.positions)
      .map(([ticker, p]) => ({ ticker, value: p.value, weight: selected.totalValue > 0 ? p.value / selected.totalValue : 0 }))
      .sort((a, b) => b.value - a.value);
  }, [selected]);

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
                {hasFollows ? (
                  portfolios!.length === 1 ? (
                    <>
                      Paper portfolio · Following{" "}
                      <span className="font-medium text-ink-800">
                        {PERSONA_BY_ID[portfolios![0].personaId].name}
                      </span>{" "}
                      since <span className="num">{portfolios![0].startedAt.slice(0, 10)}</span>
                    </>
                  ) : (
                    <>
                      Paper portfolio · Following{" "}
                      <span className="font-medium text-ink-800">{portfolios!.length} analysts</span>
                    </>
                  )
                ) : (
                  "Paper portfolio"
                )}
              </p>
            </div>
            {hasFollows && (
              <div className="text-right">
                <div className="text-[10px] uppercase tracking-[0.16em] text-ink-500">Portfolio value</div>
                <div className="num mt-1 text-4xl font-medium text-ink-900">
                  ${totalValue.toLocaleString("en-US", { maximumFractionDigits: 0 })}
                </div>
                <div className={cn("num mt-0.5 text-sm", signClass(aggReturn))}>
                  {fmt.pct(aggReturn)} since follow
                </div>
              </div>
            )}
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
              {configured && !user ? (
                <EmptyState
                  title="Sign in to see your portfolio"
                  body="Follow an analyst and Tessera tracks a $100K paper book for you."
                  action={<Button size="md" onClick={() => void signInWithGoogle()}><LogIn className="h-4 w-4" /> Sign in</Button>}
                />
              ) : portfolios === null ? (
                <div className="h-[320px] w-full animate-pulse rounded-3xl bg-ink-900/[0.04]" />
              ) : portfolios.length === 0 ? (
                <EmptyState
                  title="You're not following anyone yet"
                  body="Open an analyst and hit Follow — Tessera seeds a $100K paper book that mirrors their moves."
                  action={<Link href="/"><Button size="md">Meet the analysts</Button></Link>}
                />
              ) : (
                <>
                  {portfolios.length > 1 && (
                    <div className="mb-4 flex flex-wrap gap-2">
                      {portfolios.map((p) => {
                        const per = PERSONA_BY_ID[p.personaId];
                        const active = selected?.personaId === p.personaId;
                        return (
                          <button
                            key={p.personaId}
                            onClick={() => setFocusId(p.personaId)}
                            className={cn(
                              "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm ring-focus",
                              active ? "border-ink-900/20 bg-cream-50 text-ink-900" : "border-ink-900/[0.06] text-ink-600 hover:bg-ink-900/[0.04]",
                            )}
                          >
                            <span className={cn("h-1.5 w-1.5 rounded-full", ACCENT_CLASS[per.accent].dot)} />
                            {per.name}
                          </button>
                        );
                      })}
                    </div>
                  )}

                  <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
                    <div className="rounded-3xl border border-ink-900/[0.06] bg-cream-50 p-6">
                      <div className="mb-4">
                        <div className="text-xs uppercase tracking-[0.16em] text-ink-500">Since you followed · paper</div>
                        <h2 className="display-serif mt-1 text-2xl text-ink-900">
                          {selectedPersona?.name} vs benchmark
                        </h2>
                      </div>
                      {series.length > 1 && selectedPersona ? (
                        <CumulativeChart
                          height={280}
                          series={[
                            { id: selectedPersona.id, name: "You", color: ACCENT_HEX[selectedPersona.accent], data: series },
                            ...(bench180
                              ? [{ id: "sp500", name: "S&P 500", color: "#A8A39A", data: bench180, dashed: true }]
                              : []),
                          ]}
                        />
                      ) : (
                        <div className="grid h-[280px] w-full place-items-center rounded-2xl bg-ink-900/[0.03] px-6 text-center text-sm text-ink-500">
                          Tracking {selectedPersona?.name} since{" "}
                          <span className="num mx-1">{selected!.startedAt.slice(0, 10)}</span>
                          — your curve builds from your follow date (flat until then; you held cash).
                        </div>
                      )}
                      <p className="mt-2 text-[11px] text-ink-500">
                        You mirror {selectedPersona?.name}&apos;s book by weight from your follow date. Real paper track — no real money.
                      </p>
                    </div>

                    <div className="space-y-4">
                      <Tile label="Starting capital" value={`$${selected!.startingCapital.toLocaleString("en-US", { maximumFractionDigits: 0 })}`} />
                      <Tile label="Total value" value={`$${selected!.totalValue.toLocaleString("en-US", { maximumFractionDigits: 0 })}`}
                        sub={`${fmt.pct(selected!.startingCapital > 0 ? selected!.totalValue / selected!.startingCapital - 1 : 0)} since follow`} />
                      <Tile label="Cash" value={`$${selected!.currentCash.toLocaleString("en-US", { maximumFractionDigits: 0 })}`}
                        sub={`${fmt.pctAbs(selected!.totalValue > 0 ? selected!.currentCash / selected!.totalValue : 0)} allocation`} />
                      <Tile label="Open positions" value={`${selectedPositions.length}`} sub={`Following ${selectedPersona?.name}`} />
                    </div>
                  </div>

                  <div className="mt-4 overflow-hidden rounded-3xl border border-ink-900/[0.06] bg-cream-50">
                    <div className="grid grid-cols-[1.5fr_1fr_1fr] border-b border-ink-900/[0.06] bg-ink-900/[0.025] px-5 py-3 text-[10px] uppercase tracking-[0.14em] text-ink-500">
                      <div>Ticker</div>
                      <div>Weight</div>
                      <div className="text-right">Market value</div>
                    </div>
                    {selectedPositions.length === 0 ? (
                      <div className="px-5 py-8 text-center text-sm text-ink-500">
                        Positions populate after the next nightly sync (the mirror engine runs after market close).
                      </div>
                    ) : (
                      selectedPositions.map((p) => (
                        <div key={p.ticker} className="grid grid-cols-[1.5fr_1fr_1fr] border-b border-ink-900/[0.05] px-5 py-3.5 last:border-b-0 hover:bg-ink-900/[0.02]">
                          <div className="num text-sm font-medium text-ink-900">{p.ticker}</div>
                          <div className="num text-sm text-ink-700">{fmt.pctAbs(p.weight)}</div>
                          <div className="num text-right text-sm text-ink-800">
                            ${p.value.toLocaleString("en-US", { maximumFractionDigits: 0 })}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </>
              )}
            </TabsContent>

            {/* ───── LEADERBOARD ───── */}
            <TabsContent value="leaderboard">
              <div className="overflow-hidden rounded-3xl border border-ink-900/[0.06] bg-cream-50">
                <div className="grid grid-cols-[40px_1.4fr_1fr_1fr_1fr_1fr_1fr] border-b border-ink-900/[0.06] bg-ink-900/[0.025] px-5 py-3 text-[10px] uppercase tracking-[0.14em] text-ink-500">
                  <div>#</div><div>Analyst</div><div>1y</div><div>90d</div><div>Sharpe 30d</div><div>MDD 30d</div><div className="text-right">Value</div>
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
                Paper track — real fills since Jun 11, 2026. Sharpe/MDD are
                30-day trailing on paper NAV. Hit rate lands once closed-lot
                tracking ships.
              </p>
            </TabsContent>

            {/* ───── SOCIAL (Phase-D demo) ───── */}
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
              <p className="mt-3 text-[11px] text-ink-500">Social feed is a Phase-D demo — not real users yet.</p>
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

function EmptyState({ title, body, action }: { title: string; body: string; action: React.ReactNode }) {
  return (
    <div className="grid place-items-center rounded-3xl border border-dashed border-ink-900/15 bg-cream-50 px-6 py-16 text-center">
      <h3 className="display-serif text-2xl text-ink-900">{title}</h3>
      <p className="mt-2 max-w-md text-sm text-ink-600">{body}</p>
      <div className="mt-5">{action}</div>
    </div>
  );
}
