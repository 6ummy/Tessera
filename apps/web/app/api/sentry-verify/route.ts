/**
 * TEMPORARY — Sentry verify route.
 *
 * Throws a deliberate error so we can confirm errors actually reach the
 * tessera-web Sentry project after the initial wiring lands. Auth-gated
 * with CRON_SECRET so random visitors can't trigger noise.
 *
 * Hit once after deploy:
 *   curl -i https://<domain>/api/sentry-verify \
 *        -H "Authorization: Bearer $CRON_SECRET"
 *
 * Expected:
 *   - HTTP 500 from this route (Next.js renders the error)
 *   - A new issue appears in Sentry → tessera-web within ~10s
 *
 * Delete this file in a follow-up PR once verified. (Not removing inline
 * because the wired-up onRequestError hook is what we want to test.)
 */

import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const auth = req.headers.get("authorization") ?? "";
  const secret = process.env.CRON_SECRET;
  if (!secret || auth !== `Bearer ${secret}`) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }
  // Distinct, greppable message so it's obvious in Sentry which event this is.
  throw new Error("sentry-verify: intentional test error from /api/sentry-verify");
}
