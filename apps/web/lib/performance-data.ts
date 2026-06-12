"use client";
// Client-side fetchers + hook for the real paper-track performance data.
// Same proxy pattern as analyst-data.ts (/api/* Edge routes → worker),
// plus a module-level promise cache so the landing grid (4 cards), the
// hero chart, and the detail sheet share one fetch per persona.

import { useEffect, useState } from "react";
import type {
  PersonaPerformance,
  Point,
  PortfolioSnapshot,
} from "./performance-types";

const FETCH_TIMEOUT_MS = 20_000;

async function getJson<T>(url: string): Promise<T | null> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
  try {
    const resp = await fetch(url, { signal: ctrl.signal });
    if (!resp.ok) return null;
    return (await resp.json()) as T;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

const perfCache = new Map<string, Promise<PersonaPerformance | null>>();

export function fetchPerformance(
  personaId: string,
): Promise<PersonaPerformance | null> {
  let p = perfCache.get(personaId);
  if (!p) {
    p = getJson<PersonaPerformance>(`/api/performance/${personaId}`);
    perfCache.set(personaId, p);
  }
  return p;
}

export function fetchPortfolio(
  personaId: string,
): Promise<PortfolioSnapshot | null> {
  return getJson<PortfolioSnapshot>(`/api/portfolio/${personaId}`);
}

let benchCache: Promise<Point[] | null> | null = null;

/** S&P 500 reference from the existing /api/prices route (SPY daily
 * closes, 1y window), normalized to window start = 1.0. */
export function fetchBenchmark(): Promise<Point[] | null> {
  if (!benchCache) {
    benchCache = getJson<{ points?: { date: string; close: number }[] }>(
      "/api/prices/SPY?range=1y",
    ).then((body) => {
      const pts = body?.points ?? [];
      if (pts.length < 2) return null;
      const base = pts[0].close;
      return pts.map((p, i) => ({
        day: i,
        date: p.date,
        value: Number((p.close / base).toFixed(6)),
      }));
    });
  }
  return benchCache;
}

/** Split an equity curve into its hypothetical (dashed) and live (solid)
 * chart segments. The live segment is prepended with the last
 * hypothetical point so the two lines connect visually — the underlying
 * data is already continuous (frozen book = first real snapshot). */
export function splitSegments(perf: PersonaPerformance): {
  hyp: Point[];
  live: Point[];
} {
  const hyp: Point[] = [];
  const live: Point[] = [];
  perf.series.forEach((s, i) => {
    const pt = { day: i, date: s.date, value: s.value };
    if (s.hypothetical) hyp.push(pt);
    else live.push(pt);
  });
  if (hyp.length > 0 && live.length > 0) live.unshift(hyp[hyp.length - 1]);
  return { hyp, live };
}

/** Full curve as chart points (hypothetical + live blended). */
export function toPoints(perf: PersonaPerformance): Point[] {
  return perf.series.map((s, i) => ({ day: i, date: s.date, value: s.value }));
}

/** Re-base a sliced window so its first point = 1.0 (the chart plots
 * value − 1 as cumulative %, so windows must start at par). */
export function rebase(points: Point[]): Point[] {
  if (points.length === 0) return points;
  const base = points[0].value;
  if (base === 0) return points;
  return points.map((p, i) => ({
    day: i,
    date: p.date,
    value: Number((p.value / base).toFixed(6)),
  }));
}

export type PerformanceState = {
  perf: Record<string, PersonaPerformance | null>;
  benchmark: Point[] | null;
  loading: boolean;
};

export function usePerformance(personaIds: string[]): PerformanceState {
  const key = personaIds.join(",");
  const [state, setState] = useState<PerformanceState>({
    perf: {},
    benchmark: null,
    loading: true,
  });

  useEffect(() => {
    let alive = true;
    const ids = key.split(",").filter(Boolean);
    Promise.all([
      Promise.all(ids.map((id) => fetchPerformance(id))),
      fetchBenchmark(),
    ]).then(([results, benchmark]) => {
      if (!alive) return;
      const perf: Record<string, PersonaPerformance | null> = {};
      ids.forEach((id, i) => (perf[id] = results[i]));
      setState({ perf, benchmark, loading: false });
    });
    return () => {
      alive = false;
    };
  }, [key]);

  return state;
}
