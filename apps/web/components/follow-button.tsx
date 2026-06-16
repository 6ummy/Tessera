"use client";
// "Follow this persona" CTA. Following seeds a $100K paper portfolio for the
// signed-in user (POST /api/follow); unfollowing drops it.
//
// States:
//   - Firebase unconfigured (pilot mode) → render nothing.
//   - signed out                          → "Sign in to follow" (opens SSO).
//   - signed in, status loading           → disabled spinner-ish label.
//   - signed in, not following            → "Follow".
//   - signed in, following                → "Following ✓" (click to unfollow).

import { useCallback, useEffect, useState } from "react";
import { Check, Plus } from "lucide-react";
import { useAuth } from "@/lib/firebase/auth-context";
import { Button } from "./ui/button";

export function FollowButton({
  personaId,
  personaName,
  onChange,
}: {
  personaId: string;
  personaName: string;
  /** Called after a successful follow/unfollow so parents can refetch. */
  onChange?: (following: boolean) => void;
}) {
  const { configured, user, signInWithGoogle } = useAuth();
  const [following, setFollowing] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);

  // Load current follow status whenever the signed-in user changes.
  useEffect(() => {
    if (!user) {
      setFollowing(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const token = await user.getIdToken();
        const res = await fetch("/api/follow", { headers: { authorization: `Bearer ${token}` } });
        if (!res.ok || cancelled) return;
        const { personaIds } = (await res.json()) as { personaIds: string[] };
        if (!cancelled) setFollowing(personaIds.includes(personaId));
      } catch {
        /* leave status null — button stays actionable, toggle will surface errors */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user, personaId]);

  const toggle = useCallback(async () => {
    if (!user) {
      void signInWithGoogle();
      return;
    }
    setBusy(true);
    try {
      const token = await user.getIdToken();
      const method = following ? "DELETE" : "POST";
      const res = await fetch("/api/follow", {
        method,
        headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
        body: JSON.stringify({ personaId }),
      });
      if (res.ok) {
        setFollowing(!following);
        onChange?.(!following);
      } else console.error("follow.toggle_non_ok", res.status);
    } catch (err) {
      console.error("follow.toggle_failed", err);
    } finally {
      setBusy(false);
    }
  }, [user, following, personaId, signInWithGoogle, onChange]);

  // No follow affordance until Firebase is wired (pilot mode).
  if (!configured) return null;

  if (!user) {
    return (
      <Button size="sm" variant="outline" onClick={toggle}>
        Sign in to follow
      </Button>
    );
  }

  return (
    <Button
      size="sm"
      variant={following ? "outline" : "primary"}
      onClick={toggle}
      disabled={busy || following === null}
      aria-pressed={!!following}
      aria-label={following ? `Unfollow ${personaName}` : `Follow ${personaName}`}
    >
      {following ? <Check className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
      {following ? "Following" : "Follow"}
    </Button>
  );
}
