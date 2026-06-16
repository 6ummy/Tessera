// Neon serverless SQL client for the web app's USER layer (Phase D).
//
// Boundary note: the worker (Cloud Run) still owns the market-data plane —
// the UI reads personas/performance/etc. through worker HTTP endpoints. This
// direct Neon connection is ONLY for the user-account layer (users, and
// later user_portfolios / follows), which is web-driven because auth happens
// here. Same Neon database, different bounded context.
//
// `neon()` is the HTTP query driver — one fetch per query, no pooling, ideal
// for Vercel's serverless/edge functions (no connection-leak risk across
// invocations). Reads DATABASE_URL (server-only, NOT NEXT_PUBLIC).

import { neon } from "@neondatabase/serverless";

export function getSql() {
  const url = process.env.DATABASE_URL;
  if (!url) {
    throw new Error(
      "DATABASE_URL is not set — the auth-sync route needs it to upsert users",
    );
  }
  return neon(url);
}
