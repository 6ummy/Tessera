"use client";
// Alpaca PAPER broker, split across the dashboard via context so the pieces can
// live in different places:
//   <BrokerProvider personaId>  — holds all state + handlers, renders the modals.
//   <BrokerActions/>            — Mirror + Order-status buttons (analyst selector).
//   <BrokerConnection/>         — connect form / connected label + Disconnect (Setting).
// Gated on NEXT_PUBLIC_FEATURE_BROKER_CONNECT. Paper money only.

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Link2, Check, ArrowRightLeft, ListChecks, OctagonX, ExternalLink } from "lucide-react";
import { useAuth } from "@/lib/firebase/auth-context";
import { cn } from "@/lib/utils";

export const BROKER_ENABLED = process.env.NEXT_PUBLIC_FEATURE_BROKER_CONNECT === "true";
const NAME: Record<string, string> = { warren: "Warren", cathie: "Cathie", ray: "Ray", peter: "Peter", michael: "Michael" };

type PreviewOrder = { ticker: string; side: "buy" | "sell"; qty: number; refPrice: number; limitPrice: number; estValue: number };
type Preview = { persona: string; equity: number; marketOpen: boolean; slippageCapBps: number; skipped: string[]; orders: PreviewOrder[] };
type ExecResult = { ticker: string; side: string; qty: number; ok: boolean; detail: string };
type BrokerOrder = { id: string; ticker: string; side: string; qty: number; type: string; limitPrice: number | null; status: string; filledQty: number; filledAvgPrice: number | null; createdAt: string | null; filledAt: string | null };
type OrderType = "limit" | "market";

const OPEN_STATUSES = new Set(["new", "accepted", "pending_new", "partially_filled", "held", "accepted_for_bidding"]);

// Compact ET date+time ("06/25 14:32") for the order list.
function fmtOrderTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-US", {
    timeZone: "America/New_York", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).replace(",", "");
}

type BrokerContextValue = {
  personaId: string | null;
  personaName: string | null;
  connected: boolean;
  accountLabel: string | null;
  busy: boolean;
  error: string | null;
  results: ExecResult[] | null;
  apiKey: string; setApiKey: (s: string) => void;
  apiSecret: string; setApiSecret: (s: string) => void;
  connect: () => Promise<void>;
  disconnect: () => Promise<void>;
  openPreview: () => Promise<void>;
  openOrderStatus: () => Promise<void>;
};

const BrokerContext = createContext<BrokerContextValue | null>(null);
const useBroker = () => useContext(BrokerContext);

export function BrokerProvider({ personaId, children }: { personaId: string | null; children: React.ReactNode }) {
  const { user } = useAuth();
  const [connected, setConnected] = useState(false);
  const [accountLabel, setAccountLabel] = useState<string | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
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

  useEffect(() => { if (BROKER_ENABLED && user) void loadStatus(); }, [user, loadStatus]);

  const connect = async () => {
    setBusy(true); setError(null);
    try {
      const res = await call("/api/broker/keys", { method: "POST", body: JSON.stringify({ key: apiKey.trim(), secret: apiSecret.trim() }) });
      const d = await res.json();
      if (!res.ok) { setError(d.error ?? "could not connect"); return; }
      setApiKey(""); setApiSecret(""); setConnected(true); setAccountLabel(d.accountLabel ?? null);
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

  const value: BrokerContextValue = {
    personaId,
    personaName: personaId ? NAME[personaId] ?? personaId : null,
    connected, accountLabel, busy, error, results,
    apiKey, setApiKey, apiSecret, setApiSecret,
    connect, disconnect, openPreview, openOrderStatus,
  };

  return (
    <BrokerContext.Provider value={value}>
      {children}
      {BROKER_ENABLED && view === "preview" && preview && (
        <PreviewModal preview={preview} orderType={orderType} setOrderType={setOrderType} busy={busy}
          onConfirm={() => void execute()} onCancel={() => setView("none")} />
      )}
      {BROKER_ENABLED && view === "orders" && openOrders && (
        <OrderStatusModal orders={openOrders} busy={busy} onCancelAll={() => void cancelAll()} onClose={() => setView("none")} />
      )}
    </BrokerContext.Provider>
  );
}

/** Mirror + Order-status buttons — placed in the analyst selector. Renders
 *  nothing until an Alpaca account is connected. */
export function BrokerActions() {
  const b = useBroker();
  if (!BROKER_ENABLED || !b || !b.connected) return null;
  return (
    <div className="flex flex-col items-stretch gap-1.5 sm:items-end">
      <div className="flex items-center gap-2">
        <button type="button" onClick={() => void b.openPreview()} disabled={b.busy || !b.personaId}
          title={b.personaId ? `Mirror ${b.personaName}'s book` : "Follow an analyst to mirror"}
          className="inline-flex h-9 items-center gap-1.5 whitespace-nowrap rounded-full bg-ink-900 px-3 text-xs font-medium text-cream-50 hover:bg-ink-800 ring-focus disabled:opacity-50 sm:px-4 sm:text-sm">
          <ArrowRightLeft className="h-4 w-4 shrink-0" /> {b.personaId ? `Mirror ${b.personaName}` : "Mirror"}
        </button>
        <button type="button" onClick={() => void b.openOrderStatus()} disabled={b.busy}
          className="inline-flex h-9 items-center gap-1.5 whitespace-nowrap rounded-full border border-ink-900/10 px-3 text-xs text-ink-700 hover:bg-ink-900/[0.04] ring-focus disabled:opacity-50 sm:text-sm">
          <ListChecks className="h-4 w-4 shrink-0" /> Order status
        </button>
      </div>
      {b.error && <p className="text-xs text-coral-600">{b.error}</p>}
      {b.results && (
        <div className="rounded-xl bg-sage-500/[0.08] p-2.5 text-xs text-ink-700">
          <div className="font-medium">Placed {b.results.filter((r) => r.ok).length}/{b.results.length} order(s) — see Order status</div>
          {b.results.filter((r) => !r.ok).map((r) => (
            <div key={r.ticker} className="text-coral-700">✗ {r.side} {r.qty} {r.ticker}: {r.detail}</div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Connect form / connected label + Disconnect — placed in the Setting tab. */
export function BrokerConnection() {
  const b = useBroker();
  if (!BROKER_ENABLED || !b) return null;
  return (
    <div className="rounded-3xl border border-ink-900/[0.08] bg-cream-50 p-5">
      <div className="flex items-center gap-2">
        <Link2 className="h-4 w-4 text-coral-600" />
        <span className="text-xs font-medium uppercase tracking-[0.14em] text-coral-600">Alpaca paper account</span>
        <a href="https://app.alpaca.markets/dashboard/overview" target="_blank" rel="noopener noreferrer"
          className="ml-auto inline-flex items-center gap-1 text-[11px] text-ink-500 hover:text-ink-800 ring-focus">
          Open in Alpaca <ExternalLink className="h-3 w-3" />
        </a>
      </div>

      {!b.connected ? (
        <>
          <p className="mt-2 text-xs text-ink-500">
            Paste your Alpaca <span className="font-medium text-ink-700">paper</span> API key + secret
            (Alpaca → Paper account → API Keys). Stored encrypted — never shown again. No real money.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input value={b.apiKey} onChange={(e) => b.setApiKey(e.target.value)} placeholder="API key id" autoComplete="off"
              className="h-9 w-48 rounded-full border border-ink-900/10 bg-cream-100 px-3 text-sm text-ink-900 outline-none ring-focus placeholder:text-ink-400" />
            <input value={b.apiSecret} onChange={(e) => b.setApiSecret(e.target.value)} placeholder="API secret" type="password" autoComplete="off"
              className="h-9 w-56 rounded-full border border-ink-900/10 bg-cream-100 px-3 text-sm text-ink-900 outline-none ring-focus placeholder:text-ink-400" />
            <button type="button" onClick={() => void b.connect()} disabled={b.busy || !b.apiKey.trim() || !b.apiSecret.trim()}
              className="h-9 rounded-full bg-ink-900 px-4 text-sm font-medium text-cream-50 hover:bg-ink-800 ring-focus disabled:opacity-50">
              {b.busy ? "Connecting…" : "Connect"}
            </button>
          </div>
          {b.error && <p className="mt-2 text-xs text-coral-600">{b.error}</p>}
        </>
      ) : (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-2 text-sm text-ink-800">
            <Check className="h-4 w-4 text-sage-600" /> Connected · <span className="num">{b.accountLabel}</span>
          </span>
          <button type="button" onClick={() => void b.disconnect()} disabled={b.busy}
            className="ml-auto h-9 rounded-full border border-ink-900/10 px-3 text-xs text-ink-600 hover:bg-ink-900/[0.04] ring-focus disabled:opacity-50">
            Disconnect
          </button>
          <p className="w-full text-[11px] leading-relaxed text-ink-500">
            Mirror / Order-status live next to your analyst on the My-portfolio tab. Following or
            switching an analyst doesn&apos;t trade on its own — it&apos;s manual.
          </p>
        </div>
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
