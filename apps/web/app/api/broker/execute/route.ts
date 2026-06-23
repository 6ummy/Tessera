// POST /api/broker/execute  { persona } — place the mirror orders on the user's
// Alpaca PAPER account as marketable-limit orders (slippage-capped). The diff is
// RECOMPUTED server-side from fresh data — the client only names the persona, so
// a stale/forged order list can't be executed. Confirmed by the user in the UI.
// Gated on FEATURE_BROKER_CONNECT. Edge.

import { NextResponse } from "next/server";
import { verifyFirebaseToken } from "@/lib/firebase/verify-token";
import { executeMirror, loadAlpacaKeys, type OrderType } from "@/lib/broker-mirror";

export const runtime = "edge";
export const dynamic = "force-dynamic";

const PERSONAS = new Set(["warren", "cathie", "ray", "peter"]);

export async function POST(req: Request) {
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
  const body = (await req.json().catch(() => ({}))) as { persona?: string; orderType?: string };
  const persona = body.persona ?? "";
  if (!PERSONAS.has(persona)) return NextResponse.json({ error: "unknown persona" }, { status: 400 });
  const orderType: OrderType = body.orderType === "market" ? "market" : "limit";

  const keys = await loadAlpacaKeys(uid);
  if (!keys) return NextResponse.json({ error: "no Alpaca account connected" }, { status: 400 });

  try {
    const results = await executeMirror(keys, persona, orderType);
    const placed = results.filter((r) => r.ok).length;
    return NextResponse.json({ placed, total: results.length, results });
  } catch (err) {
    console.error("broker_execute.failed", err);
    return NextResponse.json({ error: "could not place orders" }, { status: 502 });
  }
}
