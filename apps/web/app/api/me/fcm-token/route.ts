// POST /api/me/fcm-token  — register this device's FCM token for the user.
// DELETE /api/me/fcm-token — drop it (notifications disabled / sign-out).
//
// User derived from the verified Firebase token; the FCM token comes from the
// request body. Edge runtime.

import { NextResponse } from "next/server";
import { getSql } from "@/lib/db";
import { verifyFirebaseToken } from "@/lib/firebase/verify-token";

export const runtime = "edge";

async function verify(req: Request) {
  const authz = req.headers.get("authorization") ?? "";
  const token = authz.toLowerCase().startsWith("bearer ") ? authz.slice(7).trim() : "";
  if (!token) return null;
  try {
    return await verifyFirebaseToken(token);
  } catch (err) {
    console.error("fcm_token.verify_failed", err);
    return null;
  }
}

export async function POST(req: Request) {
  const user = await verify(req);
  if (!user) return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  const { token } = (await req.json().catch(() => ({}))) as { token?: string };
  if (!token) return NextResponse.json({ error: "missing token" }, { status: 400 });

  try {
    const sql = getSql();
    await sql`
      WITH u AS (SELECT id FROM users WHERE firebase_uid = ${user.uid})
      INSERT INTO fcm_tokens (token, user_id, last_seen_at)
      SELECT ${token}, u.id, now() FROM u
      ON CONFLICT (token) DO UPDATE SET user_id = EXCLUDED.user_id, last_seen_at = now()
    `;
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("fcm_token.register_failed", err);
    return NextResponse.json({ error: "register failed" }, { status: 500 });
  }
}

export async function DELETE(req: Request) {
  const user = await verify(req);
  if (!user) return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  const { token } = (await req.json().catch(() => ({}))) as { token?: string };
  if (!token) return NextResponse.json({ error: "missing token" }, { status: 400 });

  try {
    const sql = getSql();
    await sql`
      DELETE FROM fcm_tokens
      WHERE token = ${token}
        AND user_id = (SELECT id FROM users WHERE firebase_uid = ${user.uid})
    `;
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("fcm_token.delete_failed", err);
    return NextResponse.json({ error: "delete failed" }, { status: 500 });
  }
}
