// GET /api/broker/status — the signed-in user's brokerage connection state.
// Read-only. Phase F scaffolding: in the pilot every user is "disconnected"
// (live trading is OFF-gated; broker_connections has no rows). User derived
// from the verified token only. Edge runtime.

import { NextResponse } from "next/server";
import { getSql } from "@/lib/db";
import { verifyFirebaseToken } from "@/lib/firebase/verify-token";
import { DISCONNECTED, liveTradingEnabled, type BrokerStatus } from "@/lib/broker";

export const runtime = "edge";

export async function GET(req: Request) {
  const authz = req.headers.get("authorization") ?? "";
  const token = authz.toLowerCase().startsWith("bearer ") ? authz.slice(7).trim() : "";
  if (!token) return NextResponse.json({ error: "unauthenticated" }, { status: 401 });

  let user;
  try {
    user = await verifyFirebaseToken(token);
  } catch (err) {
    console.error("broker_status.verify_failed", err);
    return NextResponse.json({ error: "invalid token" }, { status: 401 });
  }

  // Off-gated: no connection is possible in the pilot, so report disconnected
  // without even querying. (Keeps the surface honest + cheap.)
  if (!liveTradingEnabled()) {
    return NextResponse.json({ liveTradingEnabled: false, ...DISCONNECTED });
  }

  try {
    const sql = getSql();
    const rows = await sql`
      SELECT bc.provider, bc.status, bc.account_label
      FROM broker_connections bc
      JOIN users u ON u.id = bc.user_id
      WHERE u.firebase_uid = ${user.uid}
      ORDER BY bc.updated_at DESC
      LIMIT 1
    `;
    const r = rows[0];
    const status: BrokerStatus = r
      ? {
          connected: r.status === "connected",
          provider: (r.provider as string) ?? null,
          status: r.status as BrokerStatus["status"],
          accountLabel: (r.account_label as string | null) ?? null,
        }
      : DISCONNECTED;
    return NextResponse.json({ liveTradingEnabled: true, ...status });
  } catch (err) {
    console.error("broker_status.query_failed", err);
    return NextResponse.json({ error: "broker status lookup failed" }, { status: 500 });
  }
}
