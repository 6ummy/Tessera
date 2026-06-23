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
    return NextResponse.json({ points: await accountHistory(keys) });
  } catch (err) {
    console.error("broker_portfolio_history.failed", err);
    return NextResponse.json({ error: "could not load history" }, { status: 502 });
  }
}
