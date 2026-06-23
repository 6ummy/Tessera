// GET /api/broker/sync-preview?persona=cathie — dry-run: the orders that would
// make the signed-in user's Alpaca PAPER account match the persona's book.
// Places nothing. Gated on FEATURE_BROKER_CONNECT. Edge.

import { NextResponse } from "next/server";
import { verifyFirebaseToken } from "@/lib/firebase/verify-token";
import { buildPreview, loadAlpacaKeys } from "@/lib/broker-mirror";

export const runtime = "edge";
export const dynamic = "force-dynamic";

const PERSONAS = new Set(["warren", "cathie", "ray", "peter"]);

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
  const persona = new URL(req.url).searchParams.get("persona") ?? "";
  if (!PERSONAS.has(persona)) return NextResponse.json({ error: "unknown persona" }, { status: 400 });

  const keys = await loadAlpacaKeys(uid);
  if (!keys) return NextResponse.json({ error: "no Alpaca account connected" }, { status: 400 });

  try {
    return NextResponse.json(await buildPreview(keys, persona));
  } catch (err) {
    console.error("broker_sync_preview.failed", err);
    return NextResponse.json({ error: "could not build preview" }, { status: 502 });
  }
}
