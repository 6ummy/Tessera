"use client";
// Firebase client SDK — lazy, env-driven, and OPTIONAL.
//
// Phase D auth scaffolding. The whole app must keep working before the
// operator wires a Firebase project, so this never throws at import time:
// if the NEXT_PUBLIC_FIREBASE_* vars are absent, `getFirebaseAuth()`
// returns null and the UI falls back to the pre-auth pilot experience.
//
// Only the public web config lives here (apiKey etc. are NOT secrets for
// Firebase web apps — access is gated by Auth rules + authorized domains,
// not by hiding the key). Server-side token verification (firebase-admin
// + a service-account secret) lands with the auth-sync route.

import { type FirebaseApp, getApps, initializeApp } from "firebase/app";
import { type Auth, getAuth, GoogleAuthProvider } from "firebase/auth";

const config = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
  // Only needed by FCM (messaging). Safe to be undefined when push is unused.
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
};

/** The public web config (used by FCM messaging + the SW registration). */
export function firebaseConfig() {
  return config;
}

/** True once the operator has set the NEXT_PUBLIC_FIREBASE_* env vars. */
export function isFirebaseConfigured(): boolean {
  return Boolean(config.apiKey && config.authDomain && config.projectId);
}

let _app: FirebaseApp | null = null;
let _auth: Auth | null = null;

/** The initialized Firebase app, or null when not configured. */
export function getFirebaseApp(): FirebaseApp | null {
  if (!isFirebaseConfigured()) return null;
  if (!_app) _app = getApps()[0] ?? initializeApp(config);
  return _app;
}

/** The Auth instance, or null when Firebase isn't configured yet. */
export function getFirebaseAuth(): Auth | null {
  const app = getFirebaseApp();
  if (!app) return null;
  if (!_auth) _auth = getAuth(app);
  return _auth;
}

/** Google provider with account chooser forced (so a shared machine can
 *  switch users). */
export function googleProvider(): GoogleAuthProvider {
  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({ prompt: "select_account" });
  return provider;
}
