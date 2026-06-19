"use client";
// Email-alerts switch for the dashboard. Reads/writes the user's
// preferences.email_notify (opt-out; default ON). Independent of the FCM
// web-push toggle in the header.

import { useEffect, useState } from "react";
import { Mail } from "lucide-react";
import { useAuth } from "@/lib/firebase/auth-context";
import { cn } from "@/lib/utils";

type Flash = { ok: boolean; text: string };

export function EmailNotifyToggle() {
  const { user } = useAuth();
  const [on, setOn] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<Flash | null>(null);

  useEffect(() => {
    if (!user) { setOn(null); return; }
    let cancelled = false;
    (async () => {
      try {
        const token = await user.getIdToken();
        const res = await fetch("/api/me/preferences", { headers: { authorization: `Bearer ${token}` }, cache: "no-store" });
        if (!res.ok || cancelled) return;
        const { emailNotify } = (await res.json()) as { emailNotify: boolean };
        if (!cancelled) setOn(!!emailNotify);
      } catch { /* leave null — toggle hidden */ }
    })();
    return () => { cancelled = true; };
  }, [user]);

  // Auto-clear the flash message after a few seconds.
  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(null), 5000);
    return () => clearTimeout(t);
  }, [flash]);

  if (!user || on === null) return null;

  const toggle = async () => {
    setBusy(true);
    setFlash(null);
    const next = !on;
    try {
      const token = await user.getIdToken();
      const res = await fetch("/api/me/preferences", {
        method: "PUT",
        headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
        body: JSON.stringify({ emailNotify: next }),
      });
      if (!res.ok) { setFlash({ ok: false, text: "Couldn't update" }); return; }
      const data = (await res.json()) as { emailNotify: boolean; welcome?: { sent: boolean; to: string } | null };
      setOn(data.emailNotify);
      // Confirmation feedback when turning alerts ON.
      if (data.emailNotify && data.welcome) {
        setFlash(data.welcome.sent
          ? { ok: true, text: data.welcome.to ? `Email sent to ${data.welcome.to}` : "Email sent" }
          : { ok: false, text: "Couldn't send email" });
      }
    } catch {
      setFlash({ ok: false, text: "Couldn't update" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="inline-flex flex-wrap items-center gap-2">
      <Mail className="h-4 w-4 text-ink-500" />
      <span className="text-sm text-ink-700">Email alerts</span>
      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-label="Toggle email alerts"
        title="Email me when my analyst rebalances"
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
      {flash && (
        <span
          role="status"
          className={cn("text-xs", flash.ok ? "text-sage-600" : "text-coral-600")}
        >
          {flash.ok ? "✓ " : ""}{flash.text}
        </span>
      )}
    </div>
  );
}
