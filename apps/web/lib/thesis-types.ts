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
