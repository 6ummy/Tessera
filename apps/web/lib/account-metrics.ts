// Headline metrics over a reconstructed user account index. Ports the
// worker's paper_engine sharpe_30d / max_drawdown so the public investor
// leaderboard's columns match the persona leaderboard's conventions.
//
// "Since inception" return is measured from the user's FIRST follow ever
// (the account is flat cash before it, so it carries gains across analyst
// switches — switching Warren→Cathie does NOT reset the return to 0).

import { buildAccountIndex, ACCOUNT_CASH_KEY, type FollowEvent } from "./account-curve";

export type AccountMetrics = {
  /** Return since the first follow (= account index today − 1). */
  sinceInception: number | null;
  return1y: number | null;   // null until the account is ≥1y old
  return90d: number | null;  // null until the account is ≥90d old
  sharpe30d: number | null;  // null with <5 active observations
  mdd30d: number | null;     // null with <2 active observations
};

/** Annualized Sharpe over the trailing ≤30 daily returns (rf=0). Mirrors
 *  paper_engine.sharpe_30d: ≥5 obs, std-floor guard. */
export function sharpe30d(dailyReturns: number[]): number | null {
  const rets = dailyReturns.slice(-30);
  if (rets.length < 5) return null;
  const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
  const variance = rets.reduce((a, r) => a + (r - mean) ** 2, 0) / (rets.length - 1);
  const std = Math.sqrt(variance);
  if (std < 1e-12) return null;
  return (mean / std) * Math.sqrt(252);
}

/** Max peak-to-trough drawdown (positive fraction) over the trailing ≤30
 *  values. Mirrors paper_engine.max_drawdown. */
export function maxDrawdown(values: number[]): number | null {
  const vals = values.slice(-30);
  if (vals.length < 2) return null;
  let peak = vals[0];
  let mdd = 0;
  for (const v of vals) {
    peak = Math.max(peak, v);
    if (peak > 0) mdd = Math.max(mdd, (peak - v) / peak);
  }
  return mdd;
}

const DAY_MS = 86_400_000;
const dayDiff = (from: string, to: string) => Math.round((Date.parse(to) - Date.parse(from)) / DAY_MS);
const minusDays = (date: string, days: number) =>
  new Date(Date.parse(date) - days * DAY_MS).toISOString().slice(0, 10);

export function computeAccountMetrics(
  events: FollowEvent[],
  seriesByPersona: Record<string, { date: string; value: number }[]>,
  axis: string[],
): { metrics: AccountMetrics; firstFollow: string | null; currentPersonaId: string | null } {
  const empty: AccountMetrics = {
    sinceInception: null, return1y: null, return90d: null, sharpe30d: null, mdd30d: null,
  };
  const nodes = buildAccountIndex(events, seriesByPersona, axis);
  const firstFollow = events
    .filter((e) => e.action === "follow")
    .map((e) => e.ts.slice(0, 10))
    .sort()[0] ?? null;
  if (nodes.length === 0 || !firstFollow) {
    return { metrics: empty, firstFollow, currentPersonaId: null };
  }

  const last = nodes[nodes.length - 1];
  const today = last.date;
  const ageDays = dayDiff(firstFollow, today);

  // Trailing-window return: indexToday / index_at(today − window) − 1.
  const returnOver = (windowDays: number): number | null => {
    const cutoff = minusDays(today, windowDays);
    const i = nodes.findIndex((n) => n.date >= cutoff);
    if (i < 0 || !nodes[i].value) return null;
    return last.value / nodes[i].value - 1;
  };

  // Active-only daily returns / values: skip cash-flat days so a recent
  // unfollow's zeros don't dilute Sharpe/MDD.
  const activeReturns: number[] = [];
  const activeValues: number[] = [];
  for (let i = 0; i < nodes.length; i++) {
    const active = nodes[i].key !== ACCOUNT_CASH_KEY;
    if (!active) continue;
    activeValues.push(nodes[i].value);
    if (i > 0 && nodes[i - 1].key !== ACCOUNT_CASH_KEY && nodes[i - 1].value) {
      activeReturns.push(nodes[i].value / nodes[i - 1].value - 1);
    }
  }

  const metrics: AccountMetrics = {
    sinceInception: last.value - 1,
    return1y: ageDays >= 365 ? returnOver(365) : null,
    return90d: ageDays >= 90 ? returnOver(90) : null,
    sharpe30d: sharpe30d(activeReturns),
    mdd30d: maxDrawdown(activeValues),
  };
  const currentPersonaId =
    last.key !== ACCOUNT_CASH_KEY && !last.key.startsWith("__") ? last.key : null;
  return { metrics, firstFollow, currentPersonaId };
}
