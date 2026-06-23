"use client";
// Mirror a persona's book onto YOUR connected Alpaca PAPER account. Phase F.
// Preview (dry-run) → confirm → execute (marketable-limit, slippage-capped).
// Hidden unless NEXT_PUBLIC_FEATURE_BROKER_CONNECT === "true" AND an account is
// connected. Paper money only.

import { useCallback, useEffect, useState } from "react";
import { ArrowRightLeft, OctagonX } from "lucide-react";
import { useAuth } from "@/lib/firebase/auth-context";
import { cn } from "@/lib/utils";

const ENABLED = process.env.NEXT_PUBLIC_FEATURE_BROKER_CONNECT === "true";
const PERSONAS = [
  { id: "warren", name: "Warren" }, { id: "cathie", name: "Cathie" },
  { id: "ray", name: "Ray" }, { id: "peter", name: "Peter" },
];

type PreviewOrder = { ticker: string; side: "buy" | "sell"; qty: number; refPrice: number; limitPrice: number; estValue: number };
type Preview = { persona: string; equity: number; marketOpen: boolean; slippageCapBps: number; skipped: string[]; orders: PreviewOrder[] };
type ExecResult = { ticker: string; side: string; qty: number; ok: boolean; detail: string };

export function BrokerSync() {
  const { user } = useAuth();
  const [connected, setConnected] = useState(false);
  const [persona, setPersona] = useState("cathie");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [results, setResults] = useState<ExecResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const call = useCallback(async (path: string, init?: RequestInit) => {
    const token = await user!.getIdToken();
    return fetch(path, { ...init, headers: { authorization: `Bearer ${token}`, ...(init?.body ? { "content-type": "application/json" } : {}) } });
  }, [user]);

  useEffect(() => {
    if (!ENABLED || !user) return;
    void (async () => {
      const res = await call("/api/broker/keys");
      if (res.ok) setConnected(!!(await res.json()).connected);
    })();
  }, [user, call]);

  if (!ENABLED || !user || !connected) return null;

  const doPreview = async () => {
    setBusy(true); setError(null); setResults(null); setPreview(null);
    try {
      const res = await call(`/api/broker/sync-preview?persona=${persona}`);
      const d = await res.json();
      if (!res.ok) { setError(d.error ?? "preview failed"); return; }
      setPreview(d as Preview);
    } finally { setBusy(false); }
  };

  const doExecute = async () => {
    setBusy(true); setError(null);
    try {
      const res = await call("/api/broker/execute", { method: "POST", body: JSON.stringify({ persona }) });
      const d = await res.json();
      if (!res.ok) { setError(d.error ?? "execute failed"); return; }
      setResults(d.results as ExecResult[]);
      setPreview(null);
    } finally { setBusy(false); }
  };

  const doCancel = async () => {
    setBusy(true); setError(null);
    try {
      const res = await call("/api/broker/cancel-all", { method: "POST" });
      const d = await res.json();
      setError(res.ok ? `Cancelled ${d.cancelled} open order(s)` : (d.error ?? "cancel failed"));
    } finally { setBusy(false); }
  };

  return (
    <div className="mb-4 rounded-3xl border border-ink-900/[0.08] bg-cream-50 p-5">
      <div className="flex items-center justify-between gap-3">
        <span className="inline-flex items-center gap-2 text-xs font-medium uppercase tracking-[0.14em] text-coral-600">
          <ArrowRightLeft className="h-4 w-4" /> Mirror to my Alpaca paper
        </span>
        <button type="button" onClick={() => void doCancel()} disabled={busy}
          className="inline-flex h-8 items-center gap-1.5 rounded-full border border-coral-500/40 bg-coral-500/10 px-3 text-xs font-medium text-coral-700 hover:bg-coral-500/15 ring-focus disabled:opacity-50">
          <OctagonX className="h-3.5 w-3.5" /> Cancel open orders
        </button>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {PERSONAS.map((p) => (
          <button key={p.id} type="button" onClick={() => setPersona(p.id)}
            className={cn("h-8 rounded-full border px-3 text-xs font-medium ring-focus",
              persona === p.id ? "border-ink-900 bg-ink-900 text-cream-50" : "border-ink-900/10 text-ink-700 hover:bg-ink-900/[0.04]")}>
            {p.name}
          </button>
        ))}
        <button type="button" onClick={() => void doPreview()} disabled={busy}
          className="ml-auto h-8 rounded-full bg-ink-900 px-4 text-xs font-medium text-cream-50 hover:bg-ink-800 ring-focus disabled:opacity-50">
          {busy && !preview ? "Loading…" : "Preview sync"}
        </button>
      </div>

      {error && <p className="mt-3 text-xs text-ink-600">{error}</p>}

      {results && (
        <div className="mt-3 rounded-xl bg-sage-500/[0.08] p-3 text-xs text-ink-700">
          <div className="font-medium">Placed {results.filter((r) => r.ok).length}/{results.length} order(s)</div>
          {results.filter((r) => !r.ok).map((r) => (
            <div key={r.ticker} className="text-coral-700">✗ {r.side} {r.qty} {r.ticker}: {r.detail}</div>
          ))}
        </div>
      )}

      {preview && (
        <SyncModal preview={preview} busy={busy} onConfirm={() => void doExecute()} onCancel={() => setPreview(null)} />
      )}
    </div>
  );
}

function SyncModal({ preview, busy, onConfirm, onCancel }: { preview: Preview; busy: boolean; onConfirm: () => void; onCancel: () => void }) {
  const buys = preview.orders.filter((o) => o.side === "buy").length;
  const sells = preview.orders.length - buys;
  return (
    <div role="dialog" aria-modal="true" aria-label="Confirm mirror"
      className="fixed inset-0 z-50 grid place-items-center bg-ink-900/40 p-4 backdrop-blur-sm" onClick={onCancel}>
      <div className="w-full max-w-md rounded-3xl border border-ink-900/10 bg-cream-50 p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="text-xs uppercase tracking-[0.16em] text-coral-600">Confirm paper mirror</div>
        <h2 className="display-serif mt-1 text-2xl capitalize text-ink-900">{preview.persona}</h2>
        <p className="mt-1 text-xs text-ink-500">
          Equity <span className="num">${preview.equity.toLocaleString("en-US", { maximumFractionDigits: 0 })}</span> ·
          {" "}{buys} buy / {sells} sell · limit-capped {preview.slippageCapBps}bps
        </p>

        {!preview.marketOpen && (
          <p className="mt-3 rounded-xl bg-coral-500/[0.08] px-3 py-2 text-[11px] leading-relaxed text-coral-700">
            Market is closed — orders queue to the next open and may fill at a gap. The {preview.slippageCapBps}bps limit still caps the price.
          </p>
        )}

        {preview.orders.length === 0 ? (
          <p className="mt-4 text-sm text-ink-600">Already in sync — no orders.</p>
        ) : (
          <div className="mt-4 max-h-64 overflow-auto rounded-xl border border-ink-900/[0.06]">
            <table className="w-full text-xs">
              <thead className="text-ink-400"><tr className="border-b border-ink-900/[0.06]">
                <th className="px-3 py-1.5 text-left font-medium">Order</th>
                <th className="px-3 py-1.5 text-right font-medium">Limit</th>
                <th className="px-3 py-1.5 text-right font-medium">Est. value</th>
              </tr></thead>
              <tbody>
                {preview.orders.map((o) => (
                  <tr key={o.ticker} className="border-b border-ink-900/[0.04] last:border-0">
                    <td className="px-3 py-1.5">
                      <span className={cn("font-medium", o.side === "buy" ? "text-sage-600" : "text-coral-600")}>{o.side}</span>
                      {" "}<span className="num">{o.qty}</span> {o.ticker}
                    </td>
                    <td className="num px-3 py-1.5 text-right">${o.limitPrice.toFixed(2)}</td>
                    <td className="num px-3 py-1.5 text-right">${o.estValue.toLocaleString("en-US")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p className="mt-3 text-[11px] leading-relaxed text-ink-500">
          Paper money only. Orders are placed as marketable-limit (never worse than {preview.slippageCapBps}bps from the marked price).
        </p>
        <div className="mt-5 flex gap-2">
          <button type="button" onClick={onCancel} className="h-10 flex-1 rounded-full border border-ink-900/10 text-sm font-medium text-ink-700 hover:bg-ink-900/[0.04] ring-focus">Cancel</button>
          <button type="button" onClick={onConfirm} disabled={busy || preview.orders.length === 0}
            className="h-10 flex-1 rounded-full bg-ink-900 text-sm font-medium text-cream-50 hover:bg-ink-800 ring-focus disabled:opacity-50">
            {busy ? "Placing…" : `Place ${preview.orders.length} order(s)`}
          </button>
        </div>
      </div>
    </div>
  );
}
