// Sentry — Node.js server runtime (default for app router server components + route handlers).
// Loaded by instrumentation.ts on cold start. See client config for cost-guard rationale.

import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: process.env.SENTRY_DSN,
  environment: process.env.VERCEL_ENV ?? "local",
  tracesSampleRate: 0,
  sendDefaultPii: false,
});
