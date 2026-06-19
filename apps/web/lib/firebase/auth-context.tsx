"use client";
// Auth context — the single source of truth for "who is signed in" on the
// client. Phase D scaffolding.
//
// Shape is designed to degrade gracefully: when Firebase isn't configured
// (`configured === false`), `user` stays null and `loading` resolves
// immediately, so the header / dashboard can show the pre-auth pilot
// experience instead of a broken sign-in. Once the operator wires the
// NEXT_PUBLIC_FIREBASE_* vars, the same components light up with real
// Google SSO and no further code change.

import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
} from "react";
import {
  onAuthStateChanged, signInWithPopup, signOut as fbSignOut, type User,
} from "firebase/auth";
import { getFirebaseAuth, googleProvider, isFirebaseConfigured } from "./client";

/** POST the freshly-minted ID token to the server so it verifies it and
 *  upserts the users row. Best-effort: a sync failure must not block a
 *  successful client sign-in (the user is still authenticated; the row
 *  catches up on the next sign-in / token refresh). Logged loudly. */
async function syncUser(user: User): Promise<void> {
  try {
    const idToken = await user.getIdToken();
    const res = await fetch("/api/auth/sync", {
      method: "POST",
      headers: { authorization: `Bearer ${idToken}` },
    });
    if (!res.ok) console.error("auth.sync_non_ok", res.status);
  } catch (err) {
    console.error("auth.sync_failed", err);
  }
}

export type AuthState = {
  /** Whether the operator has wired a Firebase project yet. */
  configured: boolean;
  /** Resolving the initial auth state (always false when not configured). */
  loading: boolean;
  /** The signed-in Firebase user, or null. */
  user: User | null;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const configured = isFirebaseConfigured();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(configured);

  useEffect(() => {
    const auth = getFirebaseAuth();
    if (!auth) {
      setLoading(false);
      return;
    }
    const unsub = onAuthStateChanged(auth, (u) => {
      setUser(u);
      setLoading(false);
      // Fires on explicit sign-in AND on session restore (reload) — upsert
      // is idempotent, so this guarantees the users row exists + refreshes
      // last_login_at whenever an authenticated session is seen.
      if (u) void syncUser(u);
    });
    return unsub;
  }, []);

  const signInWithGoogle = useCallback(async () => {
    const auth = getFirebaseAuth();
    if (!auth) return;
    // The users-row upsert happens in the onAuthStateChanged handler above,
    // which fires right after the popup resolves.
    try {
      await signInWithPopup(auth, googleProvider());
    } catch (err) {
      const code = (err as { code?: string })?.code ?? "";
      // auth/unauthorized-domain fires when signing in from a domain not in
      // Firebase's authorized list — i.e. a Vercel per-deploy PREVIEW URL
      // (only the production alias / custom domain are authorized; ephemeral
      // preview domains can't all be added). Expected off-prod, not a bug.
      if (code === "auth/unauthorized-domain") {
        console.warn("auth.sign_in_unauthorized_domain", {
          host: typeof window !== "undefined" ? window.location.host : "",
          hint: "Sign in from the production site, not a preview deployment URL.",
        });
        return;
      }
      // User dismissed / double-clicked the popup — benign, don't report.
      if (["auth/popup-closed-by-user", "auth/cancelled-popup-request", "auth/popup-blocked"].includes(code)) {
        return;
      }
      throw err; // genuine failure — let it surface
    }
  }, []);

  const signOut = useCallback(async () => {
    const auth = getFirebaseAuth();
    if (!auth) return;
    await fbSignOut(auth);
  }, []);

  const value = useMemo<AuthState>(
    () => ({ configured, loading, user, signInWithGoogle, signOut }),
    [configured, loading, user, signInWithGoogle, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
