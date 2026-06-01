// Sentry — Edge runtime (used by /api/cron/daily and any edge middleware).
// Loaded by instrumentation.ts. Same cost-guard config as the server file.

import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: process.env.SENTRY_DSN,
  environment: process.env.VERCEL_ENV ?? "local",
  tracesSampleRate: 0,
  sendDefaultPii: false,
});
