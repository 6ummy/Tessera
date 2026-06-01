/**
 * TEMPORARY — Sentry verify route (explicit capture).
 *
 * The first version (PR #12) relied on @sentry/nextjs auto-instrumentation
 * to catch a thrown error. That doesn't work reliably in Next.js 14 App
 * Router route handlers (the `onRequestError` hook is Next 15+ only), so
 * no event reached Sentry.
 *
 * This version calls Sentry.captureException explicitly before re-throwing,
 * which is the bulletproof path for Next 14. Use this pattern in real
 * route handlers too (or wrap them with try/catch + captureException).
 *
 * Auth-gated with CRON_SECRET. Delete this file in a follow-up PR after
 * a single test event has been observed in Sentry → tessera-web.
 *
 *   curl -i https://<domain>/api/sentry-verify -H "Authorization: Bearer $CRON_SECRET"
 *
 * Expected:
 *   - HTTP 500
 *   - 2 events in Sentry tessera-web within ~10s:
 *       1. "sentry-verify: explicit captureMessage..."
 *       2. "sentry-verify: explicit captureException..."
 */

import { NextResponse } from "next/server";
import * as Sentry from "@sentry/nextjs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const auth = req.headers.get("authorization") ?? "";
  const secret = process.env.CRON_SECRET;
  if (!secret || auth !== `Bearer ${secret}`) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }

  // 1) Explicit message — proves DSN + init work.
  const messageId = Sentry.captureMessage(
    "sentry-verify: explicit captureMessage from /api/sentry-verify",
    "info",
  );

  // 2) Explicit exception capture — bypasses auto-instrumentation.
  const err = new Error("sentry-verify: explicit captureException from /api/sentry-verify");
  const exceptionId = Sentry.captureException(err);

  // 3) Flush before Vercel freezes the function (default flush window is
  //    short on edge/serverless and events can be dropped without this).
  await Sentry.flush(2000);

  // 4) Return diagnostic IDs in the response so we can correlate with Sentry UI.
  return NextResponse.json(
    {
      ok: false,
      sent: { messageId, exceptionId },
      hint: "Check Sentry → tessera-web → Issues. Match exceptionId to event ID.",
    },
    { status: 500 },
  );
}
