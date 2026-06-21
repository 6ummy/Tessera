"use client";
// Live-trading panel — Phase F scaffolding. HIDDEN in the pilot: renders null
// unless NEXT_PUBLIC_FEATURE_LIVE_TRADING === "true" (it isn't). Ties together
// the broker connect status, the kill switch, and the order-confirm modal.
// NOTHING here places an order — /api/broker/* is itself OFF-gated and there
// is no order-submit path. The real flow lands post-Phase-E.

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/firebase/auth-context";
import { KillSwitch } from "@/components/kill-switch";
import { OrderConfirmModal, type DraftOrder } from "@/components/order-confirm-modal";

const LIVE_UI_ENABLED = process.env.NEXT_PUBLIC_FEATURE_LIVE_TRADING === "true";

type Status = { connected: boolean; status: string; accountLabel: string | null };

export function LiveTradingPanel() {
  const { user } = useAuth();
  const [status, setStatus] = useState<Status | null>(null);
  const [preview, setPreview] = useState<DraftOrder | null>(null);

  useEffect(() => {
    if (!LIVE_UI_ENABLED || !user) return;
    let cancelled = false;
    (async () => {
      try {
        const token = await user.getIdToken();
        const res = await fetch("/api/broker/status", { headers: { authorization: `Bearer ${token}` }, cache: "no-store" });
        if (!res.ok || cancelled) return;
        const d = (await res.json()) as Status;
        if (!cancelled) setStatus(d);
      } catch { /* ignore */ }
    })();
    return () => { cancelled = true; };
  }, [user]);

  const connect = useCallback(async () => {
    if (!user) return;
    const token = await user.getIdToken();
    const res = await fetch("/api/broker/connect", { method: "POST", headers: { authorization: `Bearer ${token}` } });
    if (res.ok) {
      const { authorizeUrl } = (await res.json()) as { authorizeUrl?: string };
      if (authorizeUrl) window.location.href = authorizeUrl;
    } else {
      console.warn("live trading not enabled");
    }
  }, [user]);

  // The hard gate: nothing renders in the pilot.
  if (!LIVE_UI_ENABLED) return null;

  const connected = !!status?.connected;
  return (
    <div className="mb-4 rounded-3xl border border-coral-500/20 bg-cream-50 p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-[0.16em] text-coral-600">Live trading</div>
          <div className="mt-0.5 text-sm text-ink-600">
            {connected ? `Connected · ${status?.accountLabel ?? "brokerage"}` : "No brokerage connected"}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {!connected && (
            <button
              type="button"
              onClick={() => void connect()}
              className="h-9 rounded-full bg-ink-900 px-4 text-sm font-medium text-cream-50 hover:bg-ink-800 ring-focus"
            >
              Connect Alpaca
            </button>
          )}
          <KillSwitch enabled={connected} onConfirmClose={() => console.info("kill switch (scaffold)")} />
        </div>
      </div>

      <button
        type="button"
        onClick={() => setPreview({ ticker: "AAPL", side: "buy", qty: 10, estPrice: 212.34 })}
        className="mt-3 text-[11px] text-ink-500 underline-offset-2 hover:underline"
      >
        Preview order confirmation
      </button>
      <OrderConfirmModal
        order={preview}
        onConfirm={() => { console.info("order confirm (scaffold — no execution)"); setPreview(null); }}
        onCancel={() => setPreview(null)}
      />
    </div>
  );
}
