// GET /api/broker/account — the signed-in user's live Alpaca PAPER account
// summary (equity / cash / open-position count) for the dashboard tiles.
// Gated on FEATURE_BROKER_CONNECT. Edge.

import { NextResponse } from "next/server";
import { verifyFirebaseToken } from "@/lib/firebase/verify-token";
import { accountSummary, loadAlpacaKeys } from "@/lib/broker-mirror";

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
    return NextResponse.json(await accountSummary(keys));
  } catch (err) {
    console.error("broker_account.failed", err);
    return NextResponse.json({ error: "could not load account" }, { status: 502 });
  }
}
