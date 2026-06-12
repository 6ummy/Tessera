// Types for the real paper-track performance data (replaces the seeded
// random walks that lived in lib/mock/performance.ts until 2026-06-12).

// Chart-native point shape (kept from the mock era — Sparkline and
// CumulativeChart consume it; `value` is an index where window start = 1.0).
export type Point = { day: number; date: string; value: number };

// One point of /api/performance/[personaId]'s equity curve. `hypothetical`
// = frozen-book backfill (current holdings projected backwards — carries
// look-ahead bias and is rendered dashed + labelled); false = live paper
// track (real fills since 2026-06-11).
export type PerfSeriesPoint = {
  date: string;
  value: number;
  hypothetical: boolean;
};

export type PerformanceMetrics = {
  totalValue: number;
  return1y: number | null;
  return90d: number | null;
  sharpe30d: number | null;
  mdd30d: number | null; // positive fraction (0.04 = 4% max drawdown)
  trackStart: string | null; // first live (non-hypothetical) day
};

export type PersonaPerformance = {
  personaId: string;
  asOf: string | null;
  series: PerfSeriesPoint[];
  metrics: PerformanceMetrics | null;
};

export type PortfolioPosition = {
  ticker: string;
  name: string;
  sector: string;
  qty: number;
  close: number;
  value: number;
  weight: number;
};

export type PortfolioSnapshot = {
  personaId: string;
  asOf: string | null;
  totalValue: number | null;
  cash: number | null;
  cashWeight: number | null;
  positions: PortfolioPosition[];
};
