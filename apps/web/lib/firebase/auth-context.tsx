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
    });
    return unsub;
  }, []);

  const signInWithGoogle = useCallback(async () => {
    const auth = getFirebaseAuth();
    if (!auth) return;
    await signInWithPopup(auth, googleProvider());
    // TODO(auth-sync PR): POST the ID token to /api/auth/sync so the worker
    // verifies it (firebase-admin) and upserts the users row.
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
