"use client";
// Public investor leaderboard — public users ranked by SINCE-FIRST-FOLLOW
// return, with the same metric set as the persona board (1y / 90d / Sharpe /
// MDD), blank until the account is old enough. `myNickname` highlights "You".
// Mobile shows only #, Investor, Return; the rest reveal at sm+.

import { useEffect, useState } from "react";
import { PERSONA_BY_ID } from "@/lib/mock/personas";
import { cn, fmt, signClass } from "@/lib/utils";

type Investor = {
  nickname: string;
  personaId: string | null;
  startedAt: string;
  returnPct: number;
  return1y: number | null;
  return90d: number | null;
  sharpe30d: number | null;
  mdd30d: number | null;
};

// Mobile: 3 columns (#, Investor, Return). sm+: full metric set.
const COLS =
  "grid-cols-[28px_1fr_auto] sm:grid-cols-[34px_1.3fr_0.9fr_1fr_0.8fr_0.8fr_0.9fr_0.9fr]";
const HIDE = "hidden sm:block"; // secondary columns, sm+ only

export function InvestorsLeaderboard({
  myNickname,
  refreshKey,
}: {
  myNickname?: string | null;
  refreshKey?: number;
}) {
  const [investors, setInvestors] = useState<Investor[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // Default cache (not no-store) so the route's CDN s-maxage is honored
        // — repeat views hit the edge, not Neon. The board changes slowly.
        const res = await fetch("/api/leaderboard/users");
        if (cancelled) return;
        // Always resolve the loading state — on a non-2xx, show the empty
        // board rather than spinning forever.
        const data = res.ok ? ((await res.json()) as { investors: Investor[] }) : { investors: [] };
        if (!cancelled) setInvestors(data.investors ?? []);
      } catch {
        if (!cancelled) setInvestors([]);
      }
    })();
    return () => { cancelled = true; };
  }, [refreshKey]);

  if (investors === null) {
    return <div className="mt-8 h-24 w-full animate-pulse rounded-3xl bg-ink-900/[0.04]" />;
  }

  return (
    <div className="mt-10">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="display-serif text-xl text-ink-900">Investors</h3>
        <span className="text-xs text-ink-500">Return since first follow</span>
      </div>
      {investors.length === 0 ? (
        <div className="rounded-3xl border border-dashed border-ink-900/15 bg-cream-50 px-5 py-8 text-center text-sm text-ink-500">
          No public investors yet — follow an analyst and keep your profile public to appear here.
        </div>
      ) : (
        <div className="overflow-hidden rounded-3xl border border-ink-900/[0.06] bg-cream-50">
          <div className={cn("grid items-center border-b border-ink-900/[0.06] bg-ink-900/[0.025] px-4 py-3 text-[10px] uppercase tracking-[0.12em] text-ink-500 sm:px-5", COLS)}>
            <div>#</div><div>Investor</div>
            <div className={HIDE}>Following</div>
            <div className="text-right sm:text-left">Return</div>
            <div className={HIDE}>1y</div><div className={HIDE}>90d</div>
            <div className={HIDE}>Sharpe</div><div className={cn(HIDE, "text-right")}>MDD</div>
          </div>
          {investors.map((inv, i) => {
            const persona = inv.personaId ? PERSONA_BY_ID[inv.personaId] : null;
            const isMe = !!myNickname && inv.nickname === myNickname;
            return (
              <div
                key={`${inv.nickname}-${i}`}
                className={cn(
                  "grid items-center border-b border-ink-900/[0.05] px-4 py-3.5 last:border-b-0 sm:px-5",
                  COLS,
                  isMe ? "bg-coral-50" : "hover:bg-ink-900/[0.02]",
                )}
              >
                <div className="num text-xs text-ink-400">{(i + 1).toString().padStart(2, "0")}</div>
                <div className="flex min-w-0 items-center gap-2 text-sm font-medium text-ink-900">
                  <span className="truncate">{inv.nickname}</span>
                  {isMe && <span className="shrink-0 rounded-full bg-coral-500/15 px-1.5 py-0.5 text-[10px] font-medium text-coral-700">You</span>}
                </div>
                <div className={cn(HIDE, "truncate text-xs text-ink-500")}>{persona?.name ?? "Cash"}</div>
                <div className={cn("num text-right text-sm font-medium sm:text-left", signClass(inv.returnPct))}>{fmt.pct(inv.returnPct)}</div>
                <div className={cn(HIDE, "num text-sm", inv.return1y != null ? signClass(inv.return1y) : "text-ink-300")}>
                  {inv.return1y != null ? fmt.pct(inv.return1y) : "—"}
                </div>
                <div className={cn(HIDE, "num text-sm", inv.return90d != null ? signClass(inv.return90d) : "text-ink-300")}>
                  {inv.return90d != null ? fmt.pct(inv.return90d) : "—"}
                </div>
                <div className={cn(HIDE, "num text-sm text-ink-800")}>
                  {inv.sharpe30d != null ? fmt.num(inv.sharpe30d) : "—"}
                </div>
                <div className={cn(HIDE, "num text-right text-sm", inv.mdd30d != null ? signClass(-inv.mdd30d) : "text-ink-300")}>
                  {inv.mdd30d != null ? fmt.pct(-inv.mdd30d) : "—"}
                </div>
              </div>
            );
          })}
        </div>
      )}
      <p className="mt-3 text-[11px] leading-relaxed text-ink-500">
        Ranked by <span className="text-ink-700">return since first follow</span> — gains carry across
        analyst switches. 1y / 90d are blank until the account is that old. Nicknames only — emails and
        real names are never shown.
      </p>
    </div>
  );
}
