// Shared types for analyst output — used by both /api routes and
// frontend components. Replaces the type exports previously hanging
// off lib/mock/reports.ts + lib/mock/proposals.ts (now deleted).

export type Position = {
  ticker: string;
  name: string;
  sector: string;
  weight: number; // 0.12 = 12%
  side: "long" | "short" | "buy" | "sell" | "hold" | "trim" | "add";
  // Ray's RegimeAllocation has no per-slice conviction → null. UI may
  // hide the conviction dot when null.
  conviction: number | null;
  thesis: string;
};

export type RegimeProbabilities = {
  goldilocks_prob: number;
  reflation_prob: number;
  stagflation_prob: number;
  deflation_prob: number;
  delta_from_last_week_md?: string;
};

export type Proposal = {
  personaId: string;
  asOf: string | null;
  horizon: string;
  cashWeight: number | null;
  positions: Position[];
  // Ray-only: null for stock-picker personas.
  regime?: RegimeProbabilities | null;
  notesToManager?: string;
};

export type TickerFeatures = {
  ticker: string;
  name: string;
  sector: string;
  asof: string | null;
  features: {
    ret_1d: number | null;
    ret_5d: number | null;
    ret_30d: number | null;
    ret_90d: number | null;
    ret_1y: number | null;
    vol_30d: number | null;
    rsi_14: number | null;
    sma_20: number | null;
    sma_50: number | null;
    volume_z: number | null;
    fcf_yield: number | null;
    peg: number | null;
    market_cap_usd: number | null;
    operating_margin: number | null;
    eps_cagr_3y: number | null;
    debt_to_equity: number | null;
    gross_margin: number | null;
    gross_margin_trend: number | null;
  } | null;
};

export type Report = {
  id: string;
  personaId: string;
  date: string;
  title: string;
  tickers: string[];
  type: "thesis" | "update" | "macro" | "exit";
  summary: string;
  body: string[];
  numerics?: { label: string; value: string }[];
  whatWouldMakeMeWrong?: string[];
  cashTarget?: number | null;
  notesToManager?: string;
};
