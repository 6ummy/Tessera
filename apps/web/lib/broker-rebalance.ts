// Pure rebalance diff — TS port of the worker's execution/mirror_live.py
// compute_rebalance (kept deliberately identical so the web mirror and the
// operator CLI agree). No network/DB. Whole-share targets; exits non-target
// holdings; skips sub-min_notional churn. Paper money only.

export type Side = "buy" | "sell";

export type RebalanceOrder = {
  ticker: string;
  side: Side;
  qty: number; // shares to trade (always positive)
  refPrice: number; // marked reference (persona close / live price)
};

export function computeRebalance(
  targetWeights: Record<string, number>,
  prices: Record<string, number>,
  currentQty: Record<string, number>,
  equity: number,
  minNotional = 1,
): RebalanceOrder[] {
  const tickers = [...new Set([...Object.keys(targetWeights), ...Object.keys(currentQty)])].sort();
  const out: RebalanceOrder[] = [];
  for (const ticker of tickers) {
    const w = targetWeights[ticker] ?? 0;
    const price = prices[ticker] ?? 0;
    const cur = currentQty[ticker] ?? 0;
    let target = w > 0 && price > 0 ? Math.round((equity * w) / price) : 0;
    let side: Side | null = null;
    if (w <= 0 && cur !== 0) {
      side = cur > 0 ? "sell" : "buy"; // fully exit a non-target holding
      target = 0;
    } else {
      const delta = target - cur;
      if (delta !== 0 && (price <= 0 || Math.abs(delta) * price >= minNotional)) {
        side = delta > 0 ? "buy" : "sell";
      }
    }
    if (side) out.push({ ticker, side, qty: Math.abs(target - cur), refPrice: price });
  }
  return out;
}

/** Marketable-limit price: never fill worse than `capBps` from the reference.
 *  Buy caps the upside, sell caps the downside. Rounded to cents. */
export function limitPrice(side: Side, refPrice: number, capBps: number): number {
  const f = capBps / 10_000;
  const raw = side === "buy" ? refPrice * (1 + f) : refPrice * (1 - f);
  return Math.round(raw * 100) / 100;
}
