/* Firebase Cloud Messaging service worker — handles background push.
 *
 * Service workers can't read the app bundle's env, so the public Firebase
 * config is passed in via this script's registration URL query string
 * (see lib/firebase/messaging.ts → registerServiceWorker). Nothing secret
 * lives here: these are the same public values that ship in the client
 * bundle, gated by Firebase Auth rules + authorized domains.
 */
/* eslint-disable */
importScripts("https://www.gstatic.com/firebasejs/11.10.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/11.10.0/firebase-messaging-compat.js");

const params = new URL(self.location).searchParams;
const config = {
  apiKey: params.get("apiKey"),
  authDomain: params.get("authDomain"),
  projectId: params.get("projectId"),
  appId: params.get("appId"),
  messagingSenderId: params.get("messagingSenderId"),
};

if (config.apiKey && config.messagingSenderId) {
  firebase.initializeApp(config);
  const messaging = firebase.messaging();
  messaging.onBackgroundMessage((payload) => {
    const n = payload.notification || {};
    self.registration.showNotification(n.title || "Tessera", {
      body: n.body || "",
      icon: "/icon.svg",
      data: payload.data || {},
    });
  });
}

// Focus / open the app when a notification is clicked.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.link) || "/dashboard";
  event.waitUntil(
    self.clients.matchAll({ type: "window" }).then((clients) => {
      for (const c of clients) {
        if ("focus" in c) return c.focus();
      }
      return self.clients.openWindow(url);
    }),
  );
});
