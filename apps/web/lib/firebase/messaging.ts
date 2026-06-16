"use client";
// FCM web-push helpers. Optional + dark: with no VAPID key / unsupported
// browser, pushSupported() is false and the UI hides the toggle.
//
// The service worker (public/firebase-messaging-sw.js) handles background
// messages; we hand it the public Firebase config via its registration URL
// query string so nothing secret is committed.

import { deleteToken, getMessaging, getToken, isSupported } from "firebase/messaging";
import { firebaseConfig, getFirebaseApp } from "./client";

export function vapidKey(): string | undefined {
  return process.env.NEXT_PUBLIC_FIREBASE_VAPID_KEY;
}

/** True only when this browser supports FCM AND a VAPID key is configured. */
export async function pushSupported(): Promise<boolean> {
  if (typeof window === "undefined" || !("serviceWorker" in navigator)) return false;
  if (!vapidKey() || !getFirebaseApp()) return false;
  return isSupported().catch(() => false);
}

async function registerServiceWorker(): Promise<ServiceWorkerRegistration> {
  const c = firebaseConfig();
  const params = new URLSearchParams({
    apiKey: c.apiKey ?? "",
    authDomain: c.authDomain ?? "",
    projectId: c.projectId ?? "",
    appId: c.appId ?? "",
    messagingSenderId: c.messagingSenderId ?? "",
  });
  return navigator.serviceWorker.register(`/firebase-messaging-sw.js?${params.toString()}`);
}

export type EnableResult = "granted" | "denied" | "unsupported" | "error";

/** Request permission, mint the device token, and register it server-side. */
export async function enableNotifications(idToken: string): Promise<EnableResult> {
  if (!(await pushSupported())) return "unsupported";
  const app = getFirebaseApp();
  if (!app) return "unsupported";
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return "denied";
  try {
    const registration = await registerServiceWorker();
    const token = await getToken(getMessaging(app), {
      vapidKey: vapidKey(),
      serviceWorkerRegistration: registration,
    });
    if (!token) return "error";
    await fetch("/api/me/fcm-token", {
      method: "POST",
      headers: { authorization: `Bearer ${idToken}`, "content-type": "application/json" },
      body: JSON.stringify({ token }),
    });
    return "granted";
  } catch (err) {
    console.error("messaging.enable_failed", err);
    return "error";
  }
}

/** Drop this device's token (best-effort, both client SDK + server). */
export async function disableNotifications(idToken: string): Promise<void> {
  const app = getFirebaseApp();
  if (!app) return;
  try {
    const messaging = getMessaging(app);
    const token = await getToken(messaging, { vapidKey: vapidKey() }).catch(() => null);
    await deleteToken(messaging).catch(() => undefined);
    if (token) {
      await fetch("/api/me/fcm-token", {
        method: "DELETE",
        headers: { authorization: `Bearer ${idToken}`, "content-type": "application/json" },
        body: JSON.stringify({ token }),
      });
    }
  } catch (err) {
    console.error("messaging.disable_failed", err);
  }
}
