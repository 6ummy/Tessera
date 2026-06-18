"use client";
// Public investor leaderboard — public users ranked by since-follow return.
// Reads /api/leaderboard/users (no auth). `myNickname` highlights "You".

import { useEffect, useState } from "react";
import { PERSONA_BY_ID } from "@/lib/mock/personas";
import { cn, fmt, signClass } from "@/lib/utils";

type Investor = { nickname: string; personaId: string; returnPct: number; startedAt: string };

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
        const res = await fetch("/api/leaderboard/users");
        if (!res.ok || cancelled) return;
        const { investors } = (await res.json()) as { investors: Investor[] };
        if (!cancelled) setInvestors(investors);
      } catch {
        if (!cancelled) setInvestors([]);
      }
    })();
    return () => { cancelled = true; };
  }, [refreshKey]);

  if (investors === null) {
    return <div className="mt-6 h-24 w-full animate-pulse rounded-3xl bg-ink-900/[0.04]" />;
  }

  return (
    <div className="mt-8">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="display-serif text-xl text-ink-900">Investors</h3>
        <span className="text-xs text-ink-500">Public followers · return since follow</span>
      </div>
      {investors.length === 0 ? (
        <div className="rounded-3xl border border-dashed border-ink-900/15 bg-cream-50 px-5 py-8 text-center text-sm text-ink-500">
          No public investors yet — follow an analyst and keep your profile public to appear here.
        </div>
      ) : (
        <div className="overflow-hidden rounded-3xl border border-ink-900/[0.06] bg-cream-50">
          <div className="grid grid-cols-[40px_1.6fr_1fr_1fr] border-b border-ink-900/[0.06] bg-ink-900/[0.025] px-5 py-3 text-[10px] uppercase tracking-[0.14em] text-ink-500">
            <div>#</div><div>Investor</div><div>Following</div><div className="text-right">Return</div>
          </div>
          {investors.map((inv, i) => {
            const persona = PERSONA_BY_ID[inv.personaId];
            const isMe = !!myNickname && inv.nickname === myNickname;
            return (
              <div
                key={`${inv.nickname}-${i}`}
                className={cn(
                  "grid grid-cols-[40px_1.6fr_1fr_1fr] items-center border-b border-ink-900/[0.05] px-5 py-3.5 last:border-b-0",
                  isMe ? "bg-coral-50" : "hover:bg-ink-900/[0.02]",
                )}
              >
                <div className="num text-xs text-ink-400">{(i + 1).toString().padStart(2, "0")}</div>
                <div className="flex items-center gap-2 text-sm font-medium text-ink-900">
                  {inv.nickname}
                  {isMe && <span className="rounded-full bg-coral-500/15 px-1.5 py-0.5 text-[10px] font-medium text-coral-700">You</span>}
                </div>
                <div className="text-xs text-ink-500">{persona?.name ?? inv.personaId}</div>
                <div className={cn("num text-right text-sm", signClass(inv.returnPct))}>
                  {fmt.pct(inv.returnPct)}
                </div>
              </div>
            );
          })}
        </div>
      )}
      <p className="mt-3 text-[11px] text-ink-500">
        Return since each investor&apos;s follow date. Nicknames only — emails and real names are never shown.
      </p>
    </div>
  );
}
