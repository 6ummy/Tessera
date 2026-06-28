"use client";
// Starting-capital editor — the return denominator for an Alpaca-connected
// user. Default $100K; each real paper account can start at a different
// balance, so connected users set their own here. Non-Alpaca users keep the
// fixed $100K paper-follow capital (this control has no effect for them).

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/firebase/auth-context";

export function StartingCapitalEditor({ onSaved }: { onSaved?: () => void }) {
  const { user } = useAuth();
  const [capital, setCapital] = useState("100000");
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(0);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    (async () => {
      try {
        const token = await user.getIdToken();
        const res = await fetch("/api/me/preferences", { headers: { authorization: `Bearer ${token}` } });
        if (!res.ok || cancelled) return;
        const d = (await res.json()) as { startingCapital?: number };
        if (!cancelled) {
          setCapital(String(Number(d.startingCapital) || 100000));
          setLoaded(true);
        }
      } catch { /* leave default */ }
    })();
    return () => { cancelled = true; };
  }, [user]);

  if (!user || !loaded) return null;

  const parsed = Math.round(Number(capital));
  const invalid = !Number.isFinite(parsed) || parsed < 1;

  const save = async () => {
    if (invalid) return;
    setSaving(true);
    try {
      const token = await user.getIdToken();
      await fetch("/api/me/preferences", {
        method: "PUT",
        headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
        body: JSON.stringify({ startingCapital: parsed }),
      });
      setSavedAt(Date.now());
      onSaved?.();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-2xl border border-ink-900/[0.06] bg-cream-50 px-4 py-3">
      <div className="mb-2 text-[10px] uppercase tracking-[0.16em] text-ink-500">Starting capital</div>
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-ink-400">$</span>
          <input
            value={capital}
            onChange={(e) => { setCapital(e.target.value.replace(/[^0-9]/g, "").slice(0, 12)); setSavedAt(0); }}
            inputMode="numeric"
            aria-label="Starting capital"
            aria-invalid={invalid}
            className="num h-9 w-40 rounded-full border border-ink-900/10 bg-cream-100 pl-6 pr-3 text-sm text-ink-900 outline-none ring-focus"
          />
        </div>
        <button
          type="button"
          onClick={save}
          disabled={saving || invalid}
          className="ml-auto inline-flex h-9 items-center rounded-full bg-ink-900 px-4 text-sm font-medium text-cream-50 hover:bg-ink-800 ring-focus disabled:opacity-50"
        >
          {saving ? "Saving…" : savedAt ? "Saved ✓" : "Save"}
        </button>
      </div>
      <p className="mt-2 text-xs text-ink-500">
        Your Alpaca paper account&apos;s starting balance — the return is measured against this.
        Only applies when Alpaca is connected.
      </p>
    </div>
  );
}
