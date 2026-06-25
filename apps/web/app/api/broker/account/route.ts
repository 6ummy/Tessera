// GET /api/broker/account — the signed-in user's live Alpaca PAPER account
// summary (equity / cash / open-position count) for the dashboard tiles.
// Gated on FEATURE_BROKER_CONNECT. Edge.

import { NextResponse } from "next/server";
import { verifyFirebaseToken } from "@/lib/firebase/verify-token";
import { accountSummary, loadAlpacaKeys } from "@/lib/broker-mirror";
import { getSql } from "@/lib/db";

export const runtime = "edge";
export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  if (process.env.FEATURE_BROKER_CONNECT !== "true") {
    return NextResponse.json({ error: "broker connect disabled" }, { status: 403 });
  }
  const authz = req.headers.get("authorization") ?? "";
  const token = authz.toLowerCase().startsWith("bearer ") ? authz.slice(7).trim() : "";
  let uid: string;
  try {
    uid = (await verifyFirebaseToken(token)).uid;
  } catch {
    return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  }
  const keys = await loadAlpacaKeys(uid);
  if (!keys) return NextResponse.json({ error: "no Alpaca account connected" }, { status: 400 });

  try {
    const summary = await accountSummary(keys);
    // Persist only the RETURN (a fraction) — not the raw dollar equity — so the
    // PUBLIC leaderboard (CDN-cached, can't call Alpaca per user) can rank a
    // connected user by their real account. The return is exactly what the
    // leaderboard already exposes publicly, so this stores nothing more
    // sensitive than what's shown. Scoped to the authenticated user's own row;
    // the API keys themselves stay AES-encrypted in broker_connections.
    // Best-effort — never fail the read.
    try {
      const sql = getSql();
      const brokerReturn = summary.equity / 100_000 - 1;
      await sql`
        UPDATE users
        SET preferences = jsonb_set(coalesce(preferences, '{}'::jsonb),
                                    '{broker_return}', to_jsonb(${brokerReturn}::numeric), true)
        WHERE firebase_uid = ${uid}
      `;
    } catch (e) {
      console.error("broker_account.persist_return_failed", e);
    }
    return NextResponse.json(summary);
  } catch (err) {
    console.error("broker_account.failed", err);
    return NextResponse.json({ error: "could not load account" }, { status: 502 });
  }
}
