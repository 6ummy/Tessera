// Sentry — browser bundle.
// Loaded automatically by @sentry/nextjs via withSentryConfig() in next.config.mjs.
//
// Cost guard (Phase B): errors only.
//   tracesSampleRate=0    → no performance traces
//   replaysSessionSampleRate=0 → no session replays
//   replaysOnErrorSampleRate=0 → no error replays
// Re-evaluate after Phase D when usage is known.

import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.NEXT_PUBLIC_VERCEL_ENV ?? "local",
  tracesSampleRate: 0,
  replaysSessionSampleRate: 0,
  replaysOnErrorSampleRate: 0,
  // Avoid sending request bodies / cookies to the public OSS project.
  sendDefaultPii: false,
});
