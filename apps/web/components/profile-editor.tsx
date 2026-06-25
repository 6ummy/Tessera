"use client";
// Public-profile editor: nickname + public/private toggle. Signed-in only.
// Public (default) → you appear on the Investors leaderboard by nickname.

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/firebase/auth-context";
import { cn } from "@/lib/utils";

export function ProfileEditor({ onSaved }: { onSaved?: () => void }) {
  const { user } = useAuth();
  const [nickname, setNickname] = useState("");
  const [isPublic, setIsPublic] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(0);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    (async () => {
      try {
        const token = await user.getIdToken();
        const res = await fetch("/api/me/profile", { headers: { authorization: `Bearer ${token}` } });
        if (!res.ok || cancelled) return;
        const d = (await res.json()) as { nickname: string | null; isPublic: boolean };
        if (!cancelled) {
          setNickname(d.nickname ?? "");
          setIsPublic(d.isPublic !== false);
          setLoaded(true);
        }
      } catch { /* leave defaults */ }
    })();
    return () => { cancelled = true; };
  }, [user]);

  if (!user || !loaded) return null;

  // A public profile must carry a nickname — otherwise the investor shows up
  // on the leaderboard as a blank row. Private profiles can leave it empty.
  const trimmedNickname = nickname.trim();
  const needsNickname = isPublic && trimmedNickname.length === 0;

  const save = async () => {
    if (needsNickname) return;
    setSaving(true);
    try {
      const token = await user.getIdToken();
      await fetch("/api/me/profile", {
        method: "PUT",
        headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
        body: JSON.stringify({ nickname, isPublic }),
      });
      setSavedAt(Date.now());
      onSaved?.();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-2xl border border-ink-900/[0.06] bg-cream-50 px-4 py-3">
      <div className="mb-2 text-[10px] uppercase tracking-[0.16em] text-ink-500">Public profile</div>
      <div className="flex flex-wrap items-center gap-3">
        <input
          value={nickname}
          onChange={(e) => { setNickname(e.target.value.slice(0, 24)); setSavedAt(0); }}
          placeholder="Nickname"
          aria-label="Nickname"
          aria-invalid={needsNickname}
          maxLength={24}
          className={cn(
            "h-9 w-40 rounded-full border bg-cream-100 px-3 text-sm text-ink-900 outline-none ring-focus placeholder:text-ink-400",
            needsNickname ? "border-coral-500/60" : "border-ink-900/10",
          )}
        />
        <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-ink-700">
          <button
            type="button"
            role="switch"
            aria-checked={isPublic}
            onClick={() => setIsPublic((v) => !v)}
            className={cn(
              "relative h-6 w-11 shrink-0 rounded-full transition-colors ring-focus",
              isPublic ? "bg-sage-500" : "bg-ink-900/15",
            )}
          >
            <span className={cn(
              "absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-cream-50 shadow transition-transform",
              isPublic ? "translate-x-5" : "translate-x-0",
            )} />
          </button>
          {isPublic ? "Public" : "Private"}
        </label>
        <button
          type="button"
          onClick={save}
          disabled={saving || needsNickname}
          title={needsNickname ? "Add a nickname to stay public" : undefined}
          className="ml-auto inline-flex h-9 items-center rounded-full bg-ink-900 px-4 text-sm font-medium text-cream-50 hover:bg-ink-800 ring-focus disabled:opacity-50"
        >
          {saving ? "Saving…" : savedAt ? "Saved ✓" : "Save"}
        </button>
      </div>
      <p className={cn("mt-2 text-xs", needsNickname ? "text-coral-700" : "text-ink-500")}>
        {needsNickname
          ? "Add a nickname to appear on the leaderboard — or switch to Private."
          : isPublic
          ? "Public — you appear on the leaderboard by nickname and return only. Never share personal info here."
          : "Hidden from the public leaderboard."}
      </p>
    </div>
  );
}
