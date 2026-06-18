"use client";
import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, Check, Heart, LogIn, MessageCircle, Repeat2, TrendingUp } from "lucide-react";
import { ACCENT_CLASS, PERSONAS, PERSONA_BY_ID, type Persona } from "@/lib/mock/personas";
import { rebase, usePerformance, toPoints } from "@/lib/performance-data";
import { buildAccountSegments, buildAccountIndex, type FollowEvent, ACCOUNT_CASH_KEY, ACCOUNT_MIXED_KEY } from "@/lib/account-curve";
import { useAuth } from "@/lib/firebase/auth-context";
import { Header } from "@/components/header";
import { CumulativeChart } from "@/components/cumulative-chart";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { EmailNotifyToggle } from "@/components/email-notify-toggle";
import { ProfileEditor } from "@/components/profile-editor";
import { InvestorsLeaderboard } from "@/components/investors-leaderboard";
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

/** Fetch the signed-in user's real paper portfolios (their follows).
 *  `nonce` bumps force a refetch after a follow/unfollow. */
function useMyPortfolios(nonce: number) {
  const { user } = useAuth();
  const [portfolios, setPortfolios] = useState<Portfolio[] | null>(null);
  useEffect(() => {
    if (!user) { setPortfolios(null); return; }
    let cancelled = false;
    (async () => {
      try {
        const token = await user.getIdToken();
        const res = await fetch("/api/me/portfolios", { headers: { authorization: `Bearer ${token}` }, cache: "no-store" });
        if (!res.ok || cancelled) return;
        const { portfolios } = (await res.json()) as { portfolios: Portfolio[] };
        if (!cancelled) setPortfolios(portfolios);
      } catch {
        if (!cancelled) setPortfolios([]);
      }
    })();
    return () => { cancelled = true; };
  }, [user, nonce]);
  return portfolios;
}

/** Fetch the user's follow/unfollow history for the account curve. */
function useMyTimeline(nonce: number) {
  const { user } = useAuth();
  const [events, setEvents] = useState<FollowEvent[]>([]);
  useEffect(() => {
    if (!user) { setEvents([]); return; }
    let cancelled = false;
    (async () => {
      try {
        const token = await user.getIdToken();
        const res = await fetch("/api/me/timeline", { headers: { authorization: `Bearer ${token}` }, cache: "no-store" });
        if (!res.ok || cancelled) return;
        const { events } = (await res.json()) as { events: FollowEvent[] };
        if (!cancelled) setEvents(events);
      } catch { /* leave empty — curve falls back to all-cash */ }
    })();
    return () => { cancelled = true; };
  }, [user, nonce]);
  return events;
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
  // Bumped on any follow/unfollow to refetch portfolios + timeline.
  const [reloadNonce, setReloadNonce] = useState(0);
  const reload = () => setReloadNonce((n) => n + 1);
  const portfolios = useMyPortfolios(reloadNonce);
  const hasFollows = !!portfolios && portfolios.length > 0;

  // Public profile — nickname drives the "You" highlight on the Investors
  // board; profileNonce refetches it + the board after a profile save.
  const [profileNonce, setProfileNonce] = useState(0);
  const [myNickname, setMyNickname] = useState<string | null>(null);
  useEffect(() => {
    if (!user) { setMyNickname(null); return; }
    let cancelled = false;
    (async () => {
      try {
        const token = await user.getIdToken();
        const res = await fetch("/api/me/profile", { headers: { authorization: `Bearer ${token}` }, cache: "no-store" });
        if (!res.ok || cancelled) return;
        const d = (await res.json()) as { nickname: string | null };
        if (!cancelled) setMyNickname(d.nickname ?? null);
      } catch { /* ignore */ }
    })();
    return () => { cancelled = true; };
  }, [user, profileNonce]);

  // Single-follow: at most one analyst. Clicking a name follows/switches;
  // clicking the followed one unfollows (back to cash).
  const followedId = portfolios?.[0]?.personaId ?? null;
  const [busyFollowId, setBusyFollowId] = useState<string | null>(null);
  const switchFollow = async (id: string) => {
    if (!user) { void signInWithGoogle(); return; }
    setBusyFollowId(id);
    try {
      const token = await user.getIdToken();
      const method = followedId === id ? "DELETE" : "POST";
      await fetch("/api/follow", {
        method,
        headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
        body: JSON.stringify({ personaId: id }),
      });
      reload();
    } catch (err) {
      console.error("dashboard.follow_toggle_failed", err);
    } finally {
      setBusyFollowId(null);
    }
  };

  // Which followed persona is in focus (default: first follow).
  const [focusId, setFocusId] = useState<string | null>(null);
  const selected = useMemo<Portfolio | null>(() => {
    if (!portfolios || portfolios.length === 0) return null;
    return portfolios.find((p) => p.personaId === focusId) ?? portfolios[0];
  }, [portfolios, focusId]);

  // Real paper-track data: persona curves + leaderboard metrics.
  const personaIds = PERSONAS.map((p) => p.id);
  const { perf, benchmark } = usePerformance(personaIds);
  const events = useMyTimeline(reloadNonce);

  // Persona NAV series + the date axis the account is walked over. The axis is
  // the UNION of the S&P window and the persona snapshot dates — so the curve
  // and the compounded value extend through the latest persona data even when
  // the S&P feed lags a day. (Otherwise a follow/switch made "today" wouldn't
  // appear until SPY catches up: the axis would end before the switch date and
  // the chart would still show the previous analyst.)
  const seriesAndAxis = useMemo(() => {
    if (!benchmark || benchmark.length < 2) return null;
    const seriesByPersona: Record<string, ReturnType<typeof toPoints>> = {};
    for (const p of PERSONAS) {
      const pf = perf[p.id];
      if (pf) seriesByPersona[p.id] = toPoints(pf);
    }
    const axisSet = new Set(benchmark.map((p) => p.date));
    for (const pts of Object.values(seriesByPersona)) for (const pt of pts) axisSet.add(pt.date);
    return { seriesByPersona, axis: [...axisSet].sort() };
  }, [benchmark, perf]);

  // The account is ONE $100K paper book over time. Its value/return are the
  // COMPOUNDED result across every follow + analyst switch — reconstructed
  // from follow_events (same engine as the chart + investor leaderboard), NOT
  // the current user_portfolios row, which reseeds to $100K on each switch and
  // would drop the prior analyst's P&L (showing the new analyst at ~0%).
  const account = useMemo(() => {
    if (!seriesAndAxis) return null;
    const nodes = buildAccountIndex(events, seriesAndAxis.seriesByPersona, seriesAndAxis.axis);
    if (nodes.length === 0) return null;
    const idx = nodes[nodes.length - 1].value;
    const started = [...events].filter((e) => e.action === "follow").map((e) => e.ts).sort()[0] ?? null;
    return { value: 100_000 * idx, ret: idx - 1, started };
  }, [seriesAndAxis, events]);

  // Headline value/return: the compounded account when reconstructable, else
  // the row sum (loading / no perf yet).
  const totalValue = account?.value ?? (portfolios?.reduce((s, p) => s + p.totalValue, 0) ?? 0);
  const aggReturn = account?.ret ?? 0;
  // Scale the current persona's mirrored book (cash + positions, reseeded to
  // $100K on a switch) to the compounded account value so the tiles reconcile.
  const bookScale = selected && selected.totalValue > 0 ? totalValue / selected.totalValue : 1;

  const selectedPersona = selected ? PERSONA_BY_ID[selected.personaId] : null;

  // ── Account curve over the full S&P window ──────────────────────────────
  // The chart shows your whole paper account over the last ~1y: flat (cash)
  // before/after follows, tracking each persona while followed, recoloured at
  // every follow/unfollow. The S&P 500 reference is ALWAYS drawn over the
  // full window, even before your first follow.
  const accountChart = useMemo(() => {
    if (!seriesAndAxis || !benchmark) return null;
    const colorFor = (key: string) =>
      key === ACCOUNT_CASH_KEY ? "#C9C5BC"
      : key === ACCOUNT_MIXED_KEY ? "#1F1E1B"
      : ACCENT_HEX[PERSONA_BY_ID[key].accent];
    const segments = buildAccountSegments(events, seriesAndAxis.seriesByPersona, seriesAndAxis.axis, colorFor);
    const label = (key: string) =>
      key === ACCOUNT_CASH_KEY ? "Cash"
      : key === ACCOUNT_MIXED_KEY ? "You · mixed"
      : `You · ${PERSONA_BY_ID[key].name}`;
    const youSeries = segments.map((seg, i) => ({
      id: `you-${i}`, name: label(seg.key), color: seg.color, data: seg.data,
    }));
    return [
      ...youSeries,
      { id: "sp500", name: "S&P 500", color: "#A8A39A", data: rebase(benchmark), dashed: true },
    ];
  }, [seriesAndAxis, benchmark, events]);

  const selectedPositions = useMemo(() => {
    if (!selected) return [];
    return Object.entries(selected.positions)
      .map(([ticker, p]) => ({
        ticker,
        value: p.value * bookScale,
        weight: selected.totalValue > 0 ? p.value / selected.totalValue : 0,
      }))
      .sort((a, b) => b.value - a.value);
  }, [selected, bookScale]);

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
                  {fmt.pct(aggReturn)} since first follow
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
              ) : (
                <>
                  {/* Compact: pick one analyst (click to follow / switch;
                      click the followed one to unfollow) + email alerts inline. */}
                  <div className="mb-4 flex flex-col gap-3 rounded-2xl border border-ink-900/[0.06] bg-cream-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4 sm:py-2.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="mr-1 w-full text-[10px] uppercase tracking-[0.16em] text-ink-500 sm:w-auto">Analyst</span>
                      {PERSONAS.map((p) => {
                        const followed = followedId === p.id;
                        return (
                          <button
                            key={p.id}
                            type="button"
                            onClick={() => switchFollow(p.id)}
                            disabled={busyFollowId === p.id}
                            aria-pressed={followed}
                            title={followed ? `Unfollow ${p.name}` : `Follow ${p.name}`}
                            className={cn(
                              "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-colors ring-focus disabled:opacity-50",
                              followed
                                ? "border-sage-500/40 bg-sage-500/10 text-ink-900"
                                : "border-ink-900/[0.06] text-ink-700 hover:bg-ink-900/[0.04]",
                            )}
                          >
                            <span className={cn("h-1.5 w-1.5 rounded-full", ACCENT_CLASS[p.accent].dot)} />
                            {p.name}
                            {followed && (
                              <span className="inline-flex items-center gap-0.5 text-xs font-medium text-sage-600">
                                <Check className="h-3 w-3" /> Following
                              </span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                    <EmailNotifyToggle />
                  </div>

                  <div className="mb-4">
                    <ProfileEditor onSaved={() => setProfileNonce((n) => n + 1)} />
                  </div>

                  {portfolios.length === 0 ? (
                    <EmptyState
                      title="You're not following anyone yet"
                      body="Hit Follow on an analyst above — Tessera seeds a $100K paper book that mirrors their moves."
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
                        <div className="text-xs uppercase tracking-[0.16em] text-ink-500">Last 1 year · paper</div>
                        <h2 className="display-serif mt-1 text-2xl text-ink-900">
                          Your account vs S&amp;P 500
                        </h2>
                      </div>
                      {accountChart ? (
                        <CumulativeChart height={280} series={accountChart} zoomable />
                      ) : (
                        <div className="h-[280px] w-full animate-pulse rounded-2xl bg-ink-900/[0.04]" />
                      )}
                      <p className="mt-2 text-[11px] leading-relaxed text-ink-500">
                        Flat while you hold cash; tracks each analyst&apos;s book by weight while you
                        follow them (recoloured at every follow / unfollow). Real paper track — no real money.
                      </p>
                    </div>

                    <div className="space-y-4">
                      <Tile label="Starting capital" value="$100,000" />
                      <Tile label="Total value" value={`$${Math.round(totalValue).toLocaleString("en-US")}`}
                        sub={`${fmt.pct(aggReturn)} since first follow`} />
                      <Tile label="Cash" value={`$${Math.round(selected!.currentCash * bookScale).toLocaleString("en-US")}`}
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
                        No positions yet — your analyst hasn&apos;t published a book to mirror.
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
                </>
              )}
            </TabsContent>

            {/* ───── LEADERBOARD ───── */}
            <TabsContent value="leaderboard">
              <div className="mb-4 flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
                <h2 className="display-serif text-2xl text-ink-900">Leaderboard</h2>
                <div className="text-xs text-ink-500">
                  Ranked by return <span className="font-medium text-ink-700">since inception</span> ·
                  real fills from <span className="num text-ink-700">Jun 11, 2026</span>
                </div>
              </div>
              <div className="overflow-hidden rounded-3xl border border-ink-900/[0.06] bg-cream-50">
                <div className="grid grid-cols-[28px_1fr_auto] sm:grid-cols-[40px_1.4fr_1.1fr_0.9fr_0.9fr_1fr_1fr_1fr] items-center border-b border-ink-900/[0.06] bg-ink-900/[0.025] px-4 py-3 text-[10px] uppercase tracking-[0.12em] text-ink-500 sm:px-5">
                  <div>#</div><div>Analyst</div>
                  <div className="text-right sm:text-left">Since inception</div>
                  <div className="hidden sm:block">1y*</div><div className="hidden sm:block">90d</div>
                  <div className="hidden sm:block">Sharpe 30d</div><div className="hidden sm:block">MDD 30d</div>
                  <div className="hidden text-right sm:block">Value</div>
                </div>
                {(() => {
                  // Rank by return SINCE INCEPTION (real paper track) =
                  // total_value / $100K bootstrap − 1. 1y is hypothetical-
                  // backfilled (look-ahead) so it's context, not the rank key.
                  const inception = (id: string) => {
                    const tv = perf[id]?.metrics?.totalValue;
                    return tv != null ? tv / 100_000 - 1 : null;
                  };
                  return [...PERSONAS]
                    .sort((a, b) => (inception(b.id) ?? -Infinity) - (inception(a.id) ?? -Infinity))
                    .map((p, i) => {
                      const pm = perf[p.id]?.metrics ?? null;
                      const inc = inception(p.id);
                      return (
                      <div key={p.id} className="grid grid-cols-[28px_1fr_auto] sm:grid-cols-[40px_1.4fr_1.1fr_0.9fr_0.9fr_1fr_1fr_1fr] items-center border-b border-ink-900/[0.05] px-4 py-3.5 last:border-b-0 hover:bg-ink-900/[0.02] sm:px-5 sm:py-4">
                        <div className="num text-xs text-ink-400">{(i + 1).toString().padStart(2, "0")}</div>
                        <div className="truncate text-sm font-medium text-ink-900">{p.name}</div>
                        <div className={cn("num text-right text-sm font-medium sm:text-left", inc != null ? signClass(inc) : "text-ink-400")}>
                          {inc != null ? fmt.pct(inc) : "—"}
                        </div>
                        <div className={cn("hidden num text-sm sm:block", pm?.return1y != null ? signClass(pm.return1y) : "text-ink-400")}>
                          {pm?.return1y != null ? fmt.pct(pm.return1y) : "—"}
                        </div>
                        <div className={cn("hidden num text-sm sm:block", pm?.return90d != null ? signClass(pm.return90d) : "text-ink-400")}>
                          {pm?.return90d != null ? fmt.pct(pm.return90d) : "—"}
                        </div>
                        <div className="hidden num text-sm text-ink-800 sm:block">
                          {pm?.sharpe30d != null ? fmt.num(pm.sharpe30d) : "—"}
                        </div>
                        <div className={cn("hidden num text-sm sm:block", pm?.mdd30d != null ? signClass(-pm.mdd30d) : "text-ink-400")}>
                          {pm?.mdd30d != null ? fmt.pct(-pm.mdd30d) : "—"}
                        </div>
                        <div className="hidden num text-right text-sm text-ink-800 sm:block">
                          {pm?.totalValue != null
                            ? `$${pm.totalValue.toLocaleString("en-US", { maximumFractionDigits: 0 })}`
                            : "—"}
                        </div>
                      </div>
                      );
                    });
                })()}
              </div>
              <p className="mt-3 text-[11px] text-ink-500">
                Ranked by <span className="text-ink-700">return since inception</span> — each persona
                started at $100K on Jun 11, 2026 (real fills). *1y is a hypothetical
                frozen-book backfill (look-ahead bias), shown for context only.
                Sharpe/MDD are 30-day trailing on paper NAV.
              </p>

              <InvestorsLeaderboard myNickname={myNickname} refreshKey={profileNonce} />
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
