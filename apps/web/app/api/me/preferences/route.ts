// GET/PUT /api/me/preferences — the signed-in user's notification prefs.
// Currently just emailNotify (rebalance email opt-in/out). Stored in
// users.preferences JSONB. User derived from the verified token only.

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
    console.error("preferences.verify_failed", err);
    return null;
  }
}

export async function GET(req: Request) {
  const user = await verify(req);
  if (!user) return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  try {
    const sql = getSql();
    const rows = await sql`
      SELECT preferences FROM users WHERE firebase_uid = ${user.uid}
    `;
    const prefs = (rows[0]?.preferences ?? {}) as Record<string, unknown>;
    // Default ON (opt-out model): email unless explicitly disabled.
    return NextResponse.json({ emailNotify: prefs.email_notify !== false });
  } catch (err) {
    console.error("preferences.get_failed", err);
    return NextResponse.json({ error: "preferences lookup failed" }, { status: 500 });
  }
}

export async function PUT(req: Request) {
  const user = await verify(req);
  if (!user) return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  const body = (await req.json().catch(() => ({}))) as { emailNotify?: boolean };
  if (typeof body.emailNotify !== "boolean") {
    return NextResponse.json({ error: "emailNotify (boolean) required" }, { status: 400 });
  }
  try {
    const sql = getSql();
    await sql`
      UPDATE users
      SET preferences = preferences || jsonb_build_object('email_notify', ${body.emailNotify}::boolean)
      WHERE firebase_uid = ${user.uid}
    `;
    return NextResponse.json({ emailNotify: body.emailNotify });
  } catch (err) {
    console.error("preferences.put_failed", err);
    return NextResponse.json({ error: "preferences update failed" }, { status: 500 });
  }
}
