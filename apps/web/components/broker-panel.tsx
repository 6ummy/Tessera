"use client";
// One panel for the Alpaca PAPER account: connect by key/secret, then mirror
// YOUR followed analyst's book onto it. Preview (dry-run) → choose limit/market
// → place; open orders live under "Order status" (where you cancel). Hidden
// unless NEXT_PUBLIC_FEATURE_BROKER_CONNECT === "true". Paper money only.

import { useCallback, useEffect, useState } from "react";
import { Link2, Check, ArrowRightLeft, ListChecks, OctagonX, ExternalLink } from "lucide-react";
import { useAuth } from "@/lib/firebase/auth-context";
import { cn } from "@/lib/utils";

const ENABLED = process.env.NEXT_PUBLIC_FEATURE_BROKER_CONNECT === "true";
const NAME: Record<string, string> = { warren: "Warren", cathie: "Cathie", ray: "Ray", peter: "Peter", michael: "Michael" };

type PreviewOrder = { ticker: string; side: "buy" | "sell"; qty: number; refPrice: number; limitPrice: number; estValue: number };
type Preview = { persona: string; equity: number; marketOpen: boolean; slippageCapBps: number; skipped: string[]; orders: PreviewOrder[] };
type ExecResult = { ticker: string; side: string; qty: number; ok: boolean; detail: string };
type BrokerOrder = { id: string; ticker: string; side: string; qty: number; type: string; limitPrice: number | null; status: string; filledQty: number; filledAvgPrice: number | null; createdAt: string | null; filledAt: string | null };

// Compact ET date+time ("06/25 14:32") for the order list. Filled orders show
// the fill time; still-working ones show when they were placed.
function fmtOrderTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-US", {
    timeZone: "America/New_York", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).replace(",", "");
}
type OrderType = "limit" | "market";

const OPEN_STATUSES = new Set(["new", "accepted", "pending_new", "partially_filled", "held", "accepted_for_bidding"]);

export function BrokerPanel({ personaId }: { personaId: string | null }) {
  const { user } = useAuth();
  const [connected, setConnected] = useState(false);
  const [accountLabel, setAccountLabel] = useState<string | null>(null);
  const [key, setKey] = useState("");
  const [secret, setSecret] = useState("");
  const [view, setView] = useState<"none" | "preview" | "orders">("none");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [orderType, setOrderType] = useState<OrderType>("limit");
  const [openOrders, setOpenOrders] = useState<BrokerOrder[] | null>(null);
  const [results, setResults] = useState<ExecResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const call = useCallback(async (path: string, init?: RequestInit) => {
    const token = await user!.getIdToken();
    return fetch(path, { ...init, headers: { authorization: `Bearer ${token}`, ...(init?.body ? { "content-type": "application/json" } : {}) } });
  }, [user]);

  const loadStatus = useCallback(async () => {
    const res = await call("/api/broker/keys");
    if (res.ok) {
      const d = await res.json();
      setConnected(!!d.connected);
      setAccountLabel(d.accountLabel ?? null);
    }
  }, [call]);

  useEffect(() => { if (ENABLED && user) void loadStatus(); }, [user, loadStatus]);

  if (!ENABLED || !user) return null;

  const connect = async () => {
    setBusy(true); setError(null);
    try {
      const res = await call("/api/broker/keys", { method: "POST", body: JSON.stringify({ key: key.trim(), secret: secret.trim() }) });
      const d = await res.json();
      if (!res.ok) { setError(d.error ?? "could not connect"); return; }
      setKey(""); setSecret(""); setConnected(true); setAccountLabel(d.accountLabel ?? null);
    } finally { setBusy(false); }
  };

  const disconnect = async () => {
    setBusy(true);
    try {
      await call("/api/broker/keys", { method: "DELETE" });
      setConnected(false); setAccountLabel(null); setView("none"); setResults(null);
    } finally { setBusy(false); }
  };

  const openPreview = async () => {
    if (!personaId) return;
    setBusy(true); setError(null); setResults(null);
    try {
      const res = await call(`/api/broker/sync-preview?persona=${personaId}`);
      const d = await res.json();
      if (!res.ok) { setError(d.error ?? "preview failed"); return; }
      setPreview(d as Preview); setOrderType("limit"); setView("preview");
    } finally { setBusy(false); }
  };

  const execute = async () => {
    if (!personaId) return;
    setBusy(true); setError(null);
    try {
      const res = await call("/api/broker/execute", { method: "POST", body: JSON.stringify({ persona: personaId, orderType }) });
      const d = await res.json();
      if (!res.ok) { setError(d.error ?? "execute failed"); return; }
      setResults(d.results as ExecResult[]); setView("none");
    } finally { setBusy(false); }
  };

  const openOrderStatus = async () => {
    setBusy(true); setError(null);
    try {
      const res = await call("/api/broker/orders");
      const d = await res.json();
      if (!res.ok) { setError(d.error ?? "could not load orders"); return; }
      setOpenOrders(d.orders as BrokerOrder[]); setView("orders");
    } finally { setBusy(false); }
  };

  const cancelAll = async () => {
    setBusy(true);
    try {
      const res = await call("/api/broker/cancel-all", { method: "POST" });
      if (!res.ok) { setError((await res.json()).error ?? "cancel failed"); return; }
      setView("none"); // cancelled — close the panel so it doesn't look stuck
    } finally { setBusy(false); }
  };

  const personaName = personaId ? NAME[personaId] ?? personaId : null;

  return (
    <div className="mb-4 rounded-3xl border border-ink-900/[0.08] bg-cream-50 p-5">
      <div className="flex items-center gap-2">
        <Link2 className="h-4 w-4 text-coral-600" />
        <span className="text-xs font-medium uppercase tracking-[0.14em] text-coral-600">Alpaca paper account</span>
        <a href="https://app.alpaca.markets/dashboard/overview" target="_blank" rel="noopener noreferrer"
          className="ml-auto inline-flex items-center gap-1 text-[11px] text-ink-500 hover:text-ink-800 ring-focus">
          Open in Alpaca <ExternalLink className="h-3 w-3" />
        </a>
      </div>

      {!connected ? (
        <>
          <p className="mt-2 text-xs text-ink-500">
            Paste your Alpaca <span className="font-medium text-ink-700">paper</span> API key + secret
            (Alpaca → Paper account → API Keys). Stored encrypted — never shown again. No real money.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input value={key} onChange={(e) => setKey(e.target.value)} placeholder="API key id" autoComplete="off"
              className="h-9 w-48 rounded-full border border-ink-900/10 bg-cream-100 px-3 text-sm text-ink-900 outline-none ring-focus placeholder:text-ink-400" />
            <input value={secret} onChange={(e) => setSecret(e.target.value)} placeholder="API secret" type="password" autoComplete="off"
              className="h-9 w-56 rounded-full border border-ink-900/10 bg-cream-100 px-3 text-sm text-ink-900 outline-none ring-focus placeholder:text-ink-400" />
            <button type="button" onClick={() => void connect()} disabled={busy || !key.trim() || !secret.trim()}
              className="h-9 rounded-full bg-ink-900 px-4 text-sm font-medium text-cream-50 hover:bg-ink-800 ring-focus disabled:opacity-50">
              {busy ? "Connecting…" : "Connect"}
            </button>
          </div>
          {error && <p className="mt-2 text-xs text-coral-600">{error}</p>}
        </>
      ) : (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-2 text-sm text-ink-800">
              <Check className="h-4 w-4 text-sage-600" /> Connected · <span className="num">{accountLabel}</span>
            </span>
            <div className="ml-auto flex items-center gap-2">
              <button type="button" onClick={() => void openPreview()} disabled={busy || !personaId}
                title={personaId ? `Mirror ${personaName}'s book` : "Follow an analyst to mirror"}
                className="inline-flex h-9 items-center gap-1.5 rounded-full bg-ink-900 px-4 text-sm font-medium text-cream-50 hover:bg-ink-800 ring-focus disabled:opacity-50">
                <ArrowRightLeft className="h-4 w-4" /> {personaId ? `Mirror ${personaName}` : "Mirror"}
              </button>
              <button type="button" onClick={() => void openOrderStatus()} disabled={busy}
                className="inline-flex h-9 items-center gap-1.5 rounded-full border border-ink-900/10 px-3 text-sm text-ink-700 hover:bg-ink-900/[0.04] ring-focus disabled:opacity-50">
                <ListChecks className="h-4 w-4" /> Order status
              </button>
              <button type="button" onClick={() => void disconnect()} disabled={busy}
                className="h-9 rounded-full border border-ink-900/10 px-3 text-xs text-ink-600 hover:bg-ink-900/[0.04] ring-focus disabled:opacity-50">
                Disconnect
              </button>
            </div>
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-ink-500">
            Following or switching an analyst doesn&apos;t trade your Alpaca account on its own —
            it&apos;s manual: hit <span className="font-medium text-ink-700">Mirror</span>.
          </p>
          {error && <p className="mt-2 text-xs text-ink-600">{error}</p>}
          {results && (
            <div className="mt-3 rounded-xl bg-sage-500/[0.08] p-3 text-xs text-ink-700">
              <div className="font-medium">Placed {results.filter((r) => r.ok).length}/{results.length} order(s) — see Order status</div>
              {results.filter((r) => !r.ok).map((r) => (
                <div key={r.ticker} className="text-coral-700">✗ {r.side} {r.qty} {r.ticker}: {r.detail}</div>
              ))}
            </div>
          )}
        </>
      )}

      {view === "preview" && preview && (
        <PreviewModal preview={preview} orderType={orderType} setOrderType={setOrderType} busy={busy}
          onConfirm={() => void execute()} onCancel={() => setView("none")} />
      )}
      {view === "orders" && openOrders && (
        <OrderStatusModal orders={openOrders} busy={busy} onCancelAll={() => void cancelAll()} onClose={() => setView("none")} />
      )}
    </div>
  );
}

function PreviewModal({ preview, orderType, setOrderType, busy, onConfirm, onCancel }: {
  preview: Preview; orderType: OrderType; setOrderType: (t: OrderType) => void; busy: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  const buys = preview.orders.filter((o) => o.side === "buy").length;
  const sells = preview.orders.length - buys;
  return (
    <div role="dialog" aria-modal="true" aria-label="Confirm mirror"
      className="fixed inset-0 z-50 grid place-items-center bg-ink-900/40 p-4 backdrop-blur-sm" onClick={onCancel}>
      <div className="w-full max-w-md rounded-3xl border border-ink-900/10 bg-cream-50 p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="text-xs uppercase tracking-[0.16em] text-coral-600">Confirm paper mirror</div>
        <h2 className="display-serif mt-1 text-2xl capitalize text-ink-900">{preview.persona}</h2>
        <p className="mt-1 text-xs text-ink-500">
          Equity <span className="num">${preview.equity.toLocaleString("en-US", { maximumFractionDigits: 0 })}</span> · {buys} buy / {sells} sell
        </p>

        <div className="mt-3 inline-flex rounded-full border border-ink-900/10 p-0.5 text-xs">
          {(["limit", "market"] as const).map((t) => (
            <button key={t} type="button" onClick={() => setOrderType(t)}
              className={cn("h-7 rounded-full px-3 font-medium capitalize ring-focus", orderType === t ? "bg-ink-900 text-cream-50" : "text-ink-600")}>
              {t === "limit" ? `Limit (${preview.slippageCapBps}bps)` : "Market"}
            </button>
          ))}
        </div>

        {orderType === "market" && (
          <p className="mt-2 text-[11px] leading-relaxed text-coral-700">Market orders have no price cap — they fill at whatever the next print is.</p>
        )}
        {!preview.marketOpen && (
          <p className="mt-2 rounded-xl bg-coral-500/[0.08] px-3 py-2 text-[11px] leading-relaxed text-coral-700">
            Market is closed — orders queue to the next open and may fill at a gap.
          </p>
        )}

        {preview.orders.length === 0 ? (
          <p className="mt-4 text-sm text-ink-600">Already in sync — no orders.</p>
        ) : (
          <div className="mt-3 max-h-64 overflow-auto rounded-xl border border-ink-900/[0.06]">
            <table className="w-full text-xs">
              <thead className="text-ink-400"><tr className="border-b border-ink-900/[0.06]">
                <th className="px-3 py-1.5 text-left font-medium">Order</th>
                <th className="px-3 py-1.5 text-right font-medium">{orderType === "limit" ? "Limit" : "Type"}</th>
                <th className="px-3 py-1.5 text-right font-medium">Est. value</th>
              </tr></thead>
              <tbody>
                {preview.orders.map((o) => (
                  <tr key={o.ticker} className="border-b border-ink-900/[0.04] last:border-0">
                    <td className="px-3 py-1.5">
                      <span className={cn("font-medium", o.side === "buy" ? "text-sage-600" : "text-coral-600")}>{o.side}</span>{" "}
                      <span className="num">{o.qty}</span> {o.ticker}
                    </td>
                    <td className="num px-3 py-1.5 text-right">{orderType === "limit" ? `$${o.limitPrice.toFixed(2)}` : "mkt"}</td>
                    <td className="num px-3 py-1.5 text-right">${o.estValue.toLocaleString("en-US")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p className="mt-3 text-[11px] leading-relaxed text-ink-500">Paper money only.</p>
        <div className="mt-4 flex gap-2">
          <button type="button" onClick={onCancel} className="h-10 flex-1 rounded-full border border-ink-900/10 text-sm font-medium text-ink-700 hover:bg-ink-900/[0.04] ring-focus">Cancel</button>
          <button type="button" onClick={onConfirm} disabled={busy || preview.orders.length === 0}
            className="h-10 flex-1 rounded-full bg-ink-900 text-sm font-medium text-cream-50 hover:bg-ink-800 ring-focus disabled:opacity-50">
            {busy ? "Placing…" : `Place ${preview.orders.length} ${orderType} order(s)`}
          </button>
        </div>
      </div>
    </div>
  );
}

function statusColor(status: string): string {
  if (status === "filled") return "text-sage-600";
  if (OPEN_STATUSES.has(status)) return "text-amber-600";
  return "text-ink-400"; // canceled / expired / rejected / done
}

function OrderStatusModal({ orders, busy, onCancelAll, onClose }: {
  orders: BrokerOrder[]; busy: boolean; onCancelAll: () => void; onClose: () => void;
}) {
  const open = orders.filter((o) => OPEN_STATUSES.has(o.status));
  return (
    <div role="dialog" aria-modal="true" aria-label="Order status"
      className="fixed inset-0 z-50 grid place-items-center bg-ink-900/40 p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-lg rounded-3xl border border-ink-900/10 bg-cream-50 p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <div>
            <h2 className="display-serif text-xl text-ink-900">Order status</h2>
            <p className="text-xs text-ink-500">{open.length} open · {orders.length - open.length} done (recent)</p>
          </div>
          {open.length > 0 && (
            <button type="button" onClick={onCancelAll} disabled={busy}
              className="inline-flex h-8 items-center gap-1.5 rounded-full border border-coral-500/40 bg-coral-500/10 px-3 text-xs font-medium text-coral-700 hover:bg-coral-500/15 ring-focus disabled:opacity-50">
              <OctagonX className="h-3.5 w-3.5" /> {busy ? "Cancelling…" : `Cancel ${open.length} open`}
            </button>
          )}
        </div>

        {orders.length === 0 ? (
          <p className="mt-4 text-sm text-ink-600">No recent orders.</p>
        ) : (
          <div className="mt-3 max-h-80 overflow-auto rounded-xl border border-ink-900/[0.06]">
            <table className="w-full text-xs">
              <thead className="text-ink-400"><tr className="border-b border-ink-900/[0.06]">
                <th className="px-3 py-1.5 text-left font-medium">Order</th>
                <th className="px-3 py-1.5 text-right font-medium">Price</th>
                <th className="px-3 py-1.5 text-right font-medium">Time (ET)</th>
                <th className="px-3 py-1.5 text-right font-medium">Status</th>
              </tr></thead>
              <tbody>
                {orders.map((o) => {
                  const filled = o.status === "filled" || o.filledQty > 0;
                  const price = filled && o.filledAvgPrice !== null ? `$${o.filledAvgPrice.toFixed(2)}`
                    : o.limitPrice !== null ? `$${o.limitPrice.toFixed(2)} lim` : "mkt";
                  return (
                    <tr key={o.id} className="border-b border-ink-900/[0.04] last:border-0">
                      <td className="px-3 py-1.5">
                        <span className={cn("font-medium", o.side === "buy" ? "text-sage-600" : "text-coral-600")}>{o.side}</span>{" "}
                        <span className="num">{o.qty}</span> {o.ticker}
                      </td>
                      <td className="num px-3 py-1.5 text-right text-ink-600">{price}</td>
                      <td className="num px-3 py-1.5 text-right text-ink-500" title={(o.filledAt ?? o.createdAt) ?? ""}>
                        {fmtOrderTime(o.filledAt ?? o.createdAt)}
                      </td>
                      <td className={cn("px-3 py-1.5 text-right font-medium", statusColor(o.status))}>
                        {o.status === "partially_filled" ? `part (${o.filledQty}/${o.qty})` : OPEN_STATUSES.has(o.status) ? "open" : o.status}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <button type="button" onClick={onClose} className="mt-4 h-10 w-full rounded-full border border-ink-900/10 text-sm font-medium text-ink-700 hover:bg-ink-900/[0.04] ring-focus">Close</button>
      </div>
    </div>
  );
}
