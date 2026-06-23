// Server-side Alpaca PAPER mirror — decrypt a user's stored keys, read their
// paper account, diff it against a persona's current book, and (on execute)
// place marketable-limit orders. Used by /api/broker/sync-preview, /execute,
// /cancel-all. Paper money only: every call hits paper-api.alpaca.markets and
// the keys were validated against it at connect time. Keys live in memory for
// the duration of the request only — never logged, never returned.

import { getSql } from "@/lib/db";
import { decryptSecret } from "@/lib/broker-crypto";
import { computeRebalance, limitPrice, type RebalanceOrder } from "@/lib/broker-rebalance";

const ALPACA_PAPER = "https://paper-api.alpaca.markets";

export const slippageCapBps = (): number => {
  const v = Number(process.env.BROKER_SLIPPAGE_CAP_BPS);
  return Number.isFinite(v) && v > 0 ? v : 50;
};

type Keys = { key: string; secret: string };
// connectedAt = when the user linked this account in Convt — the "since sync"
// anchor for the Alpaca · Live curve (don't show equity from before they synced).
type Connection = Keys & { connectedAt: string | null };

export async function loadAlpacaKeys(uid: string): Promise<Connection | null> {
  const sql = getSql();
  const rows = await sql`
    SELECT bc.access_token_enc, bc.refresh_token_enc, bc.connected_at::text AS connected_at
    FROM broker_connections bc JOIN users u ON u.id = bc.user_id
    WHERE u.firebase_uid = ${uid} AND bc.provider = 'alpaca' AND bc.status = 'connected'
    ORDER BY bc.updated_at DESC LIMIT 1
  `;
  const r = rows[0];
  if (!r?.access_token_enc || !r?.refresh_token_enc) return null;
  const key = await decryptSecret(r.access_token_enc as string);
  const secret = await decryptSecret(r.refresh_token_enc as string);
  return key && secret ? { key, secret, connectedAt: (r.connected_at as string | null) ?? null } : null;
}

const hdrs = (k: Keys) => ({ "APCA-API-KEY-ID": k.key, "APCA-API-SECRET-KEY": k.secret });

async function api(path: string, k: Keys, init?: RequestInit): Promise<unknown> {
  const res = await fetch(`${ALPACA_PAPER}${path}`, {
    ...init,
    headers: { ...hdrs(k), ...(init?.body ? { "content-type": "application/json" } : {}) },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`alpaca ${init?.method ?? "GET"} ${path} → ${res.status}`);
  return res.status === 204 ? null : res.json();
}

type Position = { symbol: string; qty: string; current_price?: string };

/** Target weights + reference (close) prices from the persona's latest real
 *  paper snapshot. Crypto pairs (BTC/USD …) are skipped — equity/ETF only. */
async function loadPersonaTarget(
  persona: string,
): Promise<{ weights: Record<string, number>; prices: Record<string, number>; skipped: string[] }> {
  const sql = getSql();
  const rows = await sql`
    SELECT total_value::text AS total_value, positions
    FROM persona_portfolios
    WHERE persona_id = ${persona} AND NOT hypothetical
    ORDER BY ts DESC LIMIT 1
  `;
  const r = rows[0];
  const weights: Record<string, number> = {};
  const prices: Record<string, number> = {};
  const skipped: string[] = [];
  if (!r?.total_value || !r?.positions) return { weights, prices, skipped };
  const total = Number(r.total_value);
  const positions = r.positions as Record<string, { close?: number; value?: number }>;
  for (const [ticker, v] of Object.entries(positions)) {
    if (ticker.includes("/")) { skipped.push(ticker); continue; } // crypto pair
    const value = Number(v.value ?? 0);
    const close = Number(v.close ?? 0);
    if (value > 0 && close > 0 && total > 0) {
      weights[ticker] = value / total;
      prices[ticker] = close;
    }
  }
  return { weights, prices, skipped };
}

export type PreviewOrder = RebalanceOrder & { limitPrice: number; estValue: number };
export type Preview = {
  persona: string;
  equity: number;
  marketOpen: boolean;
  slippageCapBps: number;
  skipped: string[];
  orders: PreviewOrder[];
};

export async function buildPreview(keys: Keys, persona: string): Promise<Preview> {
  const cap = slippageCapBps();
  const [account, positionsRaw, clock, target] = await Promise.all([
    api("/v2/account", keys) as Promise<{ equity?: string }>,
    api("/v2/positions", keys) as Promise<Position[]>,
    api("/v2/clock", keys) as Promise<{ is_open?: boolean }>,
    loadPersonaTarget(persona),
  ]);
  const equity = Number(account.equity ?? 0);
  const current: Record<string, number> = {};
  const livePrices: Record<string, number> = {};
  for (const p of positionsRaw) {
    current[p.symbol] = Number(p.qty);
    const lp = Number(p.current_price ?? 0);
    if (lp > 0) livePrices[p.symbol] = lp;
  }
  const prices = { ...target.prices, ...livePrices };
  const orders = computeRebalance(target.weights, prices, current, equity).map((o) => ({
    ...o,
    limitPrice: limitPrice(o.side, o.refPrice, cap),
    estValue: Math.round(o.qty * o.refPrice),
  }));
  return { persona, equity, marketOpen: !!clock.is_open, slippageCapBps: cap, skipped: target.skipped, orders };
}

export type OrderType = "limit" | "market";
export type ExecResult = { ticker: string; side: string; qty: number; ok: boolean; detail: string };

/** Re-prices from fresh data (does NOT trust a client-submitted list), then
 *  places each order. "limit" → marketable-limit capped at slippageCapBps;
 *  "market" → plain market order (no price cap — the user opted out). */
export async function executeMirror(
  keys: Keys, persona: string, orderType: OrderType = "limit",
): Promise<ExecResult[]> {
  const preview = await buildPreview(keys, persona);
  const results: ExecResult[] = [];
  for (const o of preview.orders) {
    try {
      const body = JSON.stringify(
        orderType === "market"
          ? { symbol: o.ticker, qty: String(o.qty), side: o.side, type: "market", time_in_force: "day" }
          : { symbol: o.ticker, qty: String(o.qty), side: o.side, type: "limit", time_in_force: "day", limit_price: String(o.limitPrice) },
      );
      const r = (await api("/v2/orders", keys, { method: "POST", body })) as { status?: string };
      results.push({ ticker: o.ticker, side: o.side, qty: o.qty, ok: true, detail: r.status ?? "accepted" });
    } catch (err) {
      results.push({ ticker: o.ticker, side: o.side, qty: o.qty, ok: false, detail: String(err) });
    }
  }
  return results;
}

export type BrokerOrder = {
  id: string; ticker: string; side: string; qty: number; type: string;
  limitPrice: number | null; status: string; filledQty: number; filledAvgPrice: number | null;
};

const OPEN_STATUSES = new Set(["new", "accepted", "pending_new", "partially_filled", "held", "accepted_for_bidding"]);
export const isOpenStatus = (s: string): boolean => OPEN_STATUSES.has(s);

/** Recent orders (all statuses, newest first) — the Order-status list. Filled,
 *  still-working, and cancelled all show; the open ones are what cancel-all hits. */
export async function listRecentOrders(keys: Keys): Promise<BrokerOrder[]> {
  const raw = (await api("/v2/orders?status=all&limit=50&direction=desc", keys)) as Array<{
    id: string; symbol: string; side: string; qty: string; type: string; limit_price?: string;
    status: string; filled_qty?: string; filled_avg_price?: string;
  }>;
  return raw.map((o) => ({
    id: o.id, ticker: o.symbol, side: o.side, qty: Number(o.qty), type: o.type,
    limitPrice: o.limit_price ? Number(o.limit_price) : null, status: o.status,
    filledQty: Number(o.filled_qty ?? 0), filledAvgPrice: o.filled_avg_price ? Number(o.filled_avg_price) : null,
  }));
}

export type AccountSummary = { equity: number; cash: number; positionsCount: number };

/** Live snapshot of the connected paper account — drives the dashboard tiles
 *  once an account is linked. */
export async function accountSummary(keys: Keys): Promise<AccountSummary> {
  const [acct, positions] = await Promise.all([
    api("/v2/account", keys) as Promise<{ equity?: string; cash?: string }>,
    api("/v2/positions", keys) as Promise<unknown[]>,
  ]);
  return {
    equity: Number(acct.equity ?? 0),
    cash: Number(acct.cash ?? 0),
    positionsCount: Array.isArray(positions) ? positions.length : 0,
  };
}

export type EquityPoint = { date: string; equity: number };

/** The account's real equity curve (finer than our 1/day paper reconstruction).
 *  Alpaca's portfolio history — 1D bars over `period`. New accounts return only
 *  what they have. Used for the "Alpaca · Live" chart line. */
export async function accountHistory(keys: Keys, period = "1A", timeframe = "1D"): Promise<EquityPoint[]> {
  const raw = (await api(`/v2/account/portfolio/history?period=${period}&timeframe=${timeframe}`, keys)) as {
    timestamp?: number[]; equity?: Array<number | null>;
  };
  const ts = raw.timestamp ?? [];
  const eq = raw.equity ?? [];
  const out: EquityPoint[] = [];
  for (let i = 0; i < ts.length; i++) {
    const e = eq[i];
    if (e != null && e > 0) out.push({ date: new Date(ts[i] * 1000).toISOString().slice(0, 10), equity: e });
  }
  return out;
}

/** Kill switch — cancel every OPEN order (stops anything pending). */
export async function cancelOpenOrders(keys: Keys): Promise<number> {
  const r = (await api("/v2/orders", keys, { method: "DELETE" })) as unknown[] | null;
  return Array.isArray(r) ? r.length : 0;
}
