// GET /api/broker/portfolio-history — the signed-in user's real Alpaca PAPER
// account equity curve (for the "Alpaca · Live" line on the account chart).
// Gated on FEATURE_BROKER_CONNECT. Edge.

import { NextResponse } from "next/server";
import { verifyFirebaseToken } from "@/lib/firebase/verify-token";
import { accountHistory, loadAlpacaKeys } from "@/lib/broker-mirror";

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
    const points = await accountHistory(keys);
    // The Alpaca curve should start when the user SYNCED, not from account
    // creation — drop pre-sync equity (by exact timestamp now that the points
    // are intraday) so the line reflects the mirrored period only.
    // Trim by exact timestamp; if connected_at can't be parsed (Postgres text
    // offset format), fall back to a date-string compare so we never silently
    // drop everything.
    const cStr = keys.connectedAt ?? "";
    const cMs = cStr ? Date.parse(cStr.replace(" ", "T")) : NaN;
    const cDate = cStr.slice(0, 10);
    const trimmed = cStr
      ? points.filter((p) => (Number.isFinite(cMs) ? p.t >= cMs : p.date >= cDate))
      : points;
    return NextResponse.json({ points: trimmed });
  } catch (err) {
    console.error("broker_portfolio_history.failed", err);
    return NextResponse.json({ error: "could not load history" }, { status: 502 });
  }
}
