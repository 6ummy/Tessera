"use client";
// Connect your Alpaca PAPER account by API key/secret. Phase F. Hidden in the
// pilot: renders null unless NEXT_PUBLIC_FEATURE_BROKER_CONNECT === "true".
// Keys are validated against the paper endpoint + stored encrypted server-side
// (/api/broker/keys) — they never persist in the browser. Paper money only.

import { useCallback, useEffect, useState } from "react";
import { Link2, Check } from "lucide-react";
import { useAuth } from "@/lib/firebase/auth-context";
import { cn } from "@/lib/utils";

const ENABLED = process.env.NEXT_PUBLIC_FEATURE_BROKER_CONNECT === "true";

type Status = { connected: boolean; accountLabel: string | null };

export function BrokerConnect() {
  const { user } = useAuth();
  const [status, setStatus] = useState<Status | null>(null);
  const [key, setKey] = useState("");
  const [secret, setSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!user) return;
    const token = await user.getIdToken();
    const res = await fetch("/api/broker/keys", { headers: { authorization: `Bearer ${token}` }, cache: "no-store" });
    if (res.ok) {
      const d = (await res.json()) as Status & { enabled: boolean };
      setStatus({ connected: d.connected, accountLabel: d.accountLabel });
    }
  }, [user]);

  useEffect(() => { if (ENABLED && user) void load(); }, [user, load]);

  if (!ENABLED || !user) return null;

  const connect = async () => {
    setBusy(true); setError(null);
    try {
      const token = await user.getIdToken();
      const res = await fetch("/api/broker/keys", {
        method: "POST",
        headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
        body: JSON.stringify({ key: key.trim(), secret: secret.trim() }),
      });
      const d = (await res.json()) as { connected?: boolean; accountLabel?: string; error?: string };
      if (!res.ok) { setError(d.error ?? "could not connect"); return; }
      setKey(""); setSecret("");
      setStatus({ connected: true, accountLabel: d.accountLabel ?? null });
    } finally { setBusy(false); }
  };

  const disconnect = async () => {
    setBusy(true);
    try {
      const token = await user.getIdToken();
      await fetch("/api/broker/keys", { method: "DELETE", headers: { authorization: `Bearer ${token}` } });
      setStatus({ connected: false, accountLabel: null });
    } finally { setBusy(false); }
  };

  return (
    <div className="mb-4 rounded-3xl border border-ink-900/[0.08] bg-cream-50 p-5">
      <div className="flex items-center gap-2">
        <Link2 className="h-4 w-4 text-coral-600" />
        <span className="text-xs font-medium uppercase tracking-[0.14em] text-coral-600">Alpaca paper account</span>
      </div>

      {status?.connected ? (
        <div className="mt-3 flex items-center justify-between gap-3">
          <span className="inline-flex items-center gap-2 text-sm text-ink-800">
            <Check className="h-4 w-4 text-sage-600" /> Connected · <span className="num">{status.accountLabel}</span>
          </span>
          <button type="button" onClick={() => void disconnect()} disabled={busy}
            className="h-8 rounded-full border border-ink-900/10 px-3 text-xs text-ink-700 hover:bg-ink-900/[0.04] ring-focus disabled:opacity-50">
            Disconnect
          </button>
        </div>
      ) : (
        <>
          <p className="mt-2 text-xs text-ink-500">
            Paste your Alpaca <span className="font-medium text-ink-700">paper</span> API key + secret
            (Alpaca dashboard → Paper account → API Keys). Stored encrypted — never shown again. No real money.
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
          {error && <p className={cn("mt-2 text-xs text-coral-600")}>{error}</p>}
        </>
      )}
    </div>
  );
}
