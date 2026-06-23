// /api/broker/keys — connect a user's Alpaca PAPER account by API key/secret.
//   GET    → connection status for the signed-in user
//   POST   → validate the keys against the Alpaca PAPER API, then store them
//            ENCRYPTED (lib/broker-crypto); rejects anything the paper endpoint
//            doesn't accept, so live keys can't be stored here.
//   DELETE → disconnect (status=disconnected, secrets cleared)
//
// Gated on FEATURE_BROKER_CONNECT (default off). Paper money only — every call
// hits paper-api.alpaca.markets. Reuses the broker_connections table (017):
// access_token_enc = encrypted API key, refresh_token_enc = encrypted secret.
// User derived from the verified token only. Edge runtime.

import { NextResponse } from "next/server";
import { getSql } from "@/lib/db";
import { verifyFirebaseToken } from "@/lib/firebase/verify-token";
import { encryptSecret, encryptionReady } from "@/lib/broker-crypto";

export const runtime = "edge";
export const dynamic = "force-dynamic";

const ALPACA_PAPER = "https://paper-api.alpaca.markets";
const enabled = () => process.env.FEATURE_BROKER_CONNECT === "true";
const maskAccount = (a: string) => (a.length <= 5 ? a : `${a.slice(0, 2)}…${a.slice(-3)}`);

async function authed(req: Request) {
  const authz = req.headers.get("authorization") ?? "";
  const token = authz.toLowerCase().startsWith("bearer ") ? authz.slice(7).trim() : "";
  if (!token) return null;
  try {
    return await verifyFirebaseToken(token);
  } catch {
    return null;
  }
}

export async function GET(req: Request) {
  const user = await authed(req);
  if (!user) return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  if (!enabled()) return NextResponse.json({ enabled: false, connected: false });
  try {
    const sql = getSql();
    const rows = await sql`
      SELECT bc.status, bc.account_label
      FROM broker_connections bc JOIN users u ON u.id = bc.user_id
      WHERE u.firebase_uid = ${user.uid} AND bc.provider = 'alpaca'
      ORDER BY bc.updated_at DESC LIMIT 1
    `;
    const r = rows[0];
    return NextResponse.json({
      enabled: true,
      connected: r?.status === "connected",
      accountLabel: (r?.account_label as string | null) ?? null,
    });
  } catch (err) {
    console.error("broker_keys.status_failed", err);
    return NextResponse.json({ error: "status lookup failed" }, { status: 500 });
  }
}

export async function POST(req: Request) {
  const user = await authed(req);
  if (!user) return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  if (!enabled()) return NextResponse.json({ error: "broker connect disabled" }, { status: 403 });
  if (!encryptionReady()) return NextResponse.json({ error: "encryption not configured" }, { status: 503 });

  const body = (await req.json().catch(() => ({}))) as { key?: string; secret?: string };
  const key = (body.key ?? "").trim();
  const secret = (body.secret ?? "").trim();
  if (!key || !secret) return NextResponse.json({ error: "key and secret required" }, { status: 400 });

  // Validate against the PAPER endpoint — confirms the keys work AND that they
  // belong to a paper account (live keys are rejected by paper-api).
  let accountNumber: string;
  try {
    const res = await fetch(`${ALPACA_PAPER}/v2/account`, {
      headers: { "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret },
      cache: "no-store",
    });
    if (!res.ok) {
      return NextResponse.json(
        { error: "Alpaca rejected these keys (use your PAPER account API key/secret)" },
        { status: 400 },
      );
    }
    const acct = (await res.json()) as { account_number?: string };
    accountNumber = acct.account_number ?? "paper";
  } catch (err) {
    console.error("broker_keys.validate_failed", err);
    return NextResponse.json({ error: "could not reach Alpaca to validate" }, { status: 502 });
  }

  try {
    const keyEnc = await encryptSecret(key);
    const secEnc = await encryptSecret(secret);
    if (!keyEnc || !secEnc) return NextResponse.json({ error: "encryption failed" }, { status: 503 });
    const label = maskAccount(accountNumber);
    const sql = getSql();
    await sql`
      INSERT INTO broker_connections
        (user_id, provider, status, access_token_enc, refresh_token_enc, account_label, connected_at, updated_at)
      SELECT u.id, 'alpaca', 'connected', ${keyEnc}, ${secEnc}, ${label}, now(), now()
      FROM users u WHERE u.firebase_uid = ${user.uid}
      ON CONFLICT (user_id, provider) DO UPDATE SET
        status = 'connected', access_token_enc = EXCLUDED.access_token_enc,
        refresh_token_enc = EXCLUDED.refresh_token_enc, account_label = EXCLUDED.account_label,
        connected_at = now(), updated_at = now()
    `;
    return NextResponse.json({ connected: true, accountLabel: label });
  } catch (err) {
    console.error("broker_keys.store_failed", err);
    return NextResponse.json({ error: "could not save connection" }, { status: 500 });
  }
}

export async function DELETE(req: Request) {
  const user = await authed(req);
  if (!user) return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  if (!enabled()) return NextResponse.json({ error: "broker connect disabled" }, { status: 403 });
  try {
    const sql = getSql();
    await sql`
      UPDATE broker_connections SET status = 'disconnected',
        access_token_enc = NULL, refresh_token_enc = NULL, updated_at = now()
      FROM users u WHERE u.id = broker_connections.user_id
        AND u.firebase_uid = ${user.uid} AND broker_connections.provider = 'alpaca'
    `;
    return NextResponse.json({ connected: false });
  } catch (err) {
    console.error("broker_keys.disconnect_failed", err);
    return NextResponse.json({ error: "could not disconnect" }, { status: 500 });
  }
}
