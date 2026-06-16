"use client";
// "Enable notifications" account-menu item. Hidden unless the browser
// supports FCM, a VAPID key is configured, the user is signed in, and
// permission hasn't already been granted — so it ships dark.

import { useEffect, useState } from "react";
import { Bell } from "lucide-react";
import { useAuth } from "@/lib/firebase/auth-context";
import { enableNotifications, pushSupported } from "@/lib/firebase/messaging";

export function NotificationsToggle({ onDone }: { onDone?: () => void }) {
  const { user } = useAuth();
  const [supported, setSupported] = useState(false);
  const [granted, setGranted] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void pushSupported().then(setSupported);
    if (typeof Notification !== "undefined") setGranted(Notification.permission === "granted");
  }, []);

  if (!user || !supported || granted) return null;

  return (
    <button
      type="button"
      role="menuitem"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          const token = await user.getIdToken();
          const res = await enableNotifications(token);
          if (res === "granted") setGranted(true);
        } finally {
          setBusy(false);
          onDone?.();
        }
      }}
      className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm text-ink-600 hover:bg-ink-900/[0.04] disabled:opacity-50"
    >
      <Bell className="h-4 w-4" /> {busy ? "Enabling…" : "Enable notifications"}
    </button>
  );
}
