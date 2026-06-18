"use client";
// Email-alerts switch for the dashboard. Reads/writes the user's
// preferences.email_notify (opt-out; default ON). Independent of the FCM
// web-push toggle in the header.

import { useEffect, useState } from "react";
import { Mail } from "lucide-react";
import { useAuth } from "@/lib/firebase/auth-context";
import { cn } from "@/lib/utils";

export function EmailNotifyToggle() {
  const { user } = useAuth();
  const [on, setOn] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!user) { setOn(null); return; }
    let cancelled = false;
    (async () => {
      try {
        const token = await user.getIdToken();
        const res = await fetch("/api/me/preferences", { headers: { authorization: `Bearer ${token}` } });
        if (!res.ok || cancelled) return;
        const { emailNotify } = (await res.json()) as { emailNotify: boolean };
        if (!cancelled) setOn(!!emailNotify);
      } catch { /* leave null — toggle hidden */ }
    })();
    return () => { cancelled = true; };
  }, [user]);

  if (!user || on === null) return null;

  const toggle = async () => {
    setBusy(true);
    const next = !on;
    try {
      const token = await user.getIdToken();
      const res = await fetch("/api/me/preferences", {
        method: "PUT",
        headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
        body: JSON.stringify({ emailNotify: next }),
      });
      if (res.ok) setOn(next);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center justify-between rounded-2xl border border-ink-900/[0.06] bg-cream-50 px-4 py-3">
      <div className="flex items-center gap-2.5">
        <Mail className="h-4 w-4 text-ink-500" />
        <div>
          <div className="text-sm font-medium text-ink-900">Email alerts</div>
          <div className="text-xs text-ink-500">Email me when my analyst rebalances</div>
        </div>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-label="Toggle email alerts"
        disabled={busy}
        onClick={toggle}
        className={cn(
          "relative h-6 w-11 shrink-0 rounded-full transition-colors ring-focus disabled:opacity-50",
          on ? "bg-sage-500" : "bg-ink-900/15",
        )}
      >
        <span
          className={cn(
            "absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-cream-50 shadow transition-transform",
            on ? "translate-x-5" : "translate-x-0",
          )}
        />
      </button>
    </div>
  );
}
