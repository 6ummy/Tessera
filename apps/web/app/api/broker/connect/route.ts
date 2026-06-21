// POST /api/broker/connect — begin linking a brokerage (Alpaca OAuth).
// Phase F scaffolding: HARD-GATED. Returns 403 unless FEATURE_LIVE_TRADING is
// "true" (it never is in the pilot), so no OAuth ever starts. Even when
// enabled it only returns the authorize URL — it does NOT exchange tokens or
// place orders (the token-exchange callback + order routing land post-Phase-E).
// User derived from the verified token only. Edge runtime.

import { NextResponse } from "next/server";
import { verifyFirebaseToken } from "@/lib/firebase/verify-token";
import { alpacaAuthorizeUrl, liveTradingEnabled } from "@/lib/broker";

export const runtime = "edge";

export async function POST(req: Request) {
  const authz = req.headers.get("authorization") ?? "";
  const token = authz.toLowerCase().startsWith("bearer ") ? authz.slice(7).trim() : "";
  if (!token) return NextResponse.json({ error: "unauthenticated" }, { status: 401 });

  let user;
  try {
    user = await verifyFirebaseToken(token);
  } catch (err) {
    console.error("broker_connect.verify_failed", err);
    return NextResponse.json({ error: "invalid token" }, { status: 401 });
  }

  // The gate. Live trading requires Phase E clearance; until then this path is
  // closed and no brokerage OAuth can start.
  if (!liveTradingEnabled()) {
    return NextResponse.json(
      { error: "live trading is not enabled", code: "live_trading_disabled" },
      { status: 403 },
    );
  }

  const authorizeUrl = alpacaAuthorizeUrl(user.uid);
  if (!authorizeUrl) {
    return NextResponse.json({ error: "broker OAuth not configured" }, { status: 503 });
  }
  // NOTE: returning the authorize URL only. The /callback token exchange +
  // encrypted storage is a deliberate, reviewed post-Phase-E change.
  return NextResponse.json({ authorizeUrl });
}
