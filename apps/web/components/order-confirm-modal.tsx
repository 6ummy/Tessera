"use client";
// Order confirmation modal — Phase F scaffolding (display only).
// Every live order must be explicitly confirmed by the user (no silent
// execution). This component just renders the confirmation; it is NOT wired to
// any order-placement path. The real submit lands post-Phase-E.

import { cn } from "@/lib/utils";

export type DraftOrder = {
  ticker: string;
  side: "buy" | "sell";
  qty: number;
  estPrice: number; // last close — indicative only
};

export function OrderConfirmModal({
  order,
  onConfirm,
  onCancel,
  busy = false,
}: {
  order: DraftOrder | null;
  onConfirm: () => void;
  onCancel: () => void;
  busy?: boolean;
}) {
  if (!order) return null;
  const est = order.qty * order.estPrice;
  const isBuy = order.side === "buy";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Confirm order"
      className="fixed inset-0 z-50 grid place-items-center bg-ink-900/40 p-4 backdrop-blur-sm"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-sm rounded-3xl border border-ink-900/10 bg-cream-50 p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="text-xs uppercase tracking-[0.16em] text-coral-600">Confirm live order</div>
        <h2 className="display-serif mt-1 text-2xl text-ink-900">
          {isBuy ? "Buy" : "Sell"} {order.ticker}
        </h2>

        <dl className="mt-4 space-y-2 text-sm">
          <Row label="Side" value={<span className={cn("font-medium", isBuy ? "text-sage-600" : "text-coral-600")}>{order.side.toUpperCase()}</span>} />
          <Row label="Quantity" value={<span className="num">{order.qty}</span>} />
          <Row label="Est. price" value={<span className="num">${order.estPrice.toLocaleString("en-US", { minimumFractionDigits: 2 })}</span>} />
          <Row label="Est. value" value={<span className="num font-medium">${est.toLocaleString("en-US", { maximumFractionDigits: 0 })}</span>} />
        </dl>

        <p className="mt-4 rounded-xl bg-coral-500/[0.07] px-3 py-2 text-[11px] leading-relaxed text-ink-600">
          This places a <span className="font-medium text-ink-800">real order with real money</span>.
          Estimated value is indicative — the fill price may differ.
        </p>

        <div className="mt-5 flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="h-10 flex-1 rounded-full border border-ink-900/10 text-sm font-medium text-ink-700 hover:bg-ink-900/[0.04] ring-focus"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="h-10 flex-1 rounded-full bg-ink-900 text-sm font-medium text-cream-50 hover:bg-ink-800 ring-focus disabled:opacity-50"
          >
            {busy ? "Placing…" : "Confirm order"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-ink-500">{label}</dt>
      <dd className="text-ink-900">{value}</dd>
    </div>
  );
}
