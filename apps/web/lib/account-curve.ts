// Reconstruct a user's paper-account curve across their follow history.
//
// The account is a single $100K paper book over time. On any given day it is
// either in CASH (flat — before the first follow, or after an unfollow) or
// TRACKING one or more followed personas (its daily return = the mean of
// those personas' daily returns). Walking the day axis with the follow/
// unfollow events yields one continuous index (1.0 = window start), which we
// cut into colored SEGMENTS at every state change so the chart can paint the
// cash stretches grey and each persona's stretch in its own colour.

import type { Point } from "./performance-types";

export type FollowEvent = { personaId: string; action: "follow" | "unfollow"; ts: string };

/** One day of the reconstructed account: index value (1.0 = window start)
 *  and the state key (a personaId, "__cash__", or "__mixed__"). */
export type AccountNode = { date: string; value: number; key: string };

export type AccountSegment = {
  /** State key for this segment: a personaId, "__cash__", or "__mixed__". */
  key: string;
  data: Point[];
  color: string;
};

const CASH = "__cash__";
const MIXED = "__mixed__";

/**
 * Reconstruct the per-day account index from a follow history. Flat (1.0) in
 * cash, compounding the mean of the followed personas' daily returns while
 * following. Shared by the dashboard chart (segmented) and the public
 * investor leaderboard (metrics).
 *
 * @param events            follow/unfollow events, any order
 * @param seriesByPersona   personaId → date-sorted NAV points ({date, value})
 * @param axis              sorted date strings to walk over (e.g. the S&P window)
 */
export function buildAccountIndex(
  events: FollowEvent[],
  seriesByPersona: Record<string, { date: string; value: number }[]>,
  axis: string[],
): AccountNode[] {
  if (axis.length === 0) return [];

  const valByPersona: Record<string, Map<string, number>> = {};
  for (const [pid, pts] of Object.entries(seriesByPersona)) {
    valByPersona[pid] = new Map(pts.map((p) => [p.date, p.value]));
  }

  const evs = events
    .map((e) => ({ ...e, date: e.ts.slice(0, 10) }))
    .sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0));

  // For each axis date, the set of personas followed as of end-of-day.
  // A re-follow without an intervening unfollow is a no-op (count-guarded).
  const active = new Map<string, number>();
  let evi = 0;
  const personasByDate: string[][] = [];
  for (const d of axis) {
    while (evi < evs.length && evs[evi].date <= d) {
      const e = evs[evi];
      if (e.action === "follow") {
        active.set(e.personaId, (active.get(e.personaId) ?? 0) + 1);
      } else {
        const c = (active.get(e.personaId) ?? 0) - 1;
        if (c <= 0) active.delete(e.personaId);
        else active.set(e.personaId, c);
      }
      evi++;
    }
    personasByDate.push([...active.keys()].sort());
  }

  // Walk the index: flat in cash, compound the mean daily return while following.
  const nodes: AccountNode[] = [];
  let index = 1.0;
  for (let i = 0; i < axis.length; i++) {
    const d = axis[i];
    const personas = personasByDate[i];
    if (i > 0 && personas.length > 0) {
      const dPrev = axis[i - 1];
      let sum = 0;
      let n = 0;
      for (const pid of personas) {
        const v = valByPersona[pid]?.get(d);
        const vp = valByPersona[pid]?.get(dPrev);
        if (v != null && vp != null && vp !== 0) {
          sum += v / vp - 1;
          n += 1;
        }
      }
      if (n > 0) index *= 1 + sum / n;
    }
    const key = personas.length === 0 ? CASH : personas.length === 1 ? personas[0] : MIXED;
    nodes.push({ date: d, value: Number(index.toFixed(6)), key });
  }
  return nodes;
}

/**
 * @param events            follow/unfollow events, any order
 * @param seriesByPersona   personaId → date-sorted NAV-index points
 * @param axis              sorted date strings to plot over (e.g. the S&P window)
 * @param colorFor          maps a state key → stroke colour
 */
export function buildAccountSegments(
  events: FollowEvent[],
  seriesByPersona: Record<string, Point[]>,
  axis: string[],
  colorFor: (key: string) => string,
): AccountSegment[] {
  return segmentNodes(buildAccountIndex(events, seriesByPersona, axis), colorFor);
}

/**
 * Cut a reconstructed account index into colour-coded segments at every key
 * change. Separated from buildAccountSegments so a caller can slice / rebase
 * the nodes first (e.g. a "since inception / 1M / 3M / 1Y" range selector).
 * The boundary node is shared by both neighbours so the line stays visually
 * continuous through the colour change.
 */
export function segmentNodes(
  nodes: AccountNode[],
  colorFor: (key: string) => string,
): AccountSegment[] {
  if (nodes.length === 0) return [];
  const segments: AccountSegment[] = [];
  let cur: AccountNode[] = [];
  const flush = () => {
    if (cur.length < 1) return;
    const key = cur[0].key;
    segments.push({
      key,
      color: colorFor(key),
      data: cur.map((nd, j) => ({ day: j, date: nd.date, value: nd.value })),
    });
  };
  for (const nd of nodes) {
    if (cur.length === 0 || nd.key === cur[cur.length - 1].key) {
      cur.push(nd);
    } else {
      cur.push(nd); // close current segment on the boundary node
      flush();
      cur = [nd]; // and reopen the next from it
    }
  }
  flush();
  return segments;
}

export const ACCOUNT_CASH_KEY = CASH;
export const ACCOUNT_MIXED_KEY = MIXED;
