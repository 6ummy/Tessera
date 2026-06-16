// GET /api/me/timeline — the signed-in user's follow/unfollow history, used
// by the dashboard to reconstruct the account curve (flat cash periods +
// per-persona tracking segments). User derived from the verified token only.

import { NextResponse } from "next/server";
import { getSql } from "@/lib/db";
import { verifyFirebaseToken } from "@/lib/firebase/verify-token";

export const runtime = "edge";

export async function GET(req: Request) {
  const authz = req.headers.get("authorization") ?? "";
  const token = authz.toLowerCase().startsWith("bearer ") ? authz.slice(7).trim() : "";
  if (!token) return NextResponse.json({ error: "unauthenticated" }, { status: 401 });

  let user;
  try {
    user = await verifyFirebaseToken(token);
  } catch (err) {
    console.error("me_timeline.verify_failed", err);
    return NextResponse.json({ error: "invalid token" }, { status: 401 });
  }

  try {
    const sql = getSql();
    const rows = await sql`
      SELECT e.persona_id, e.action, e.ts
      FROM follow_events e
      JOIN users u ON u.id = e.user_id
      WHERE u.firebase_uid = ${user.uid}
      ORDER BY e.ts ASC
    `;
    const events = rows.map((r) => ({
      personaId: r.persona_id as string,
      action: r.action as "follow" | "unfollow",
      ts: r.ts as string,
    }));
    return NextResponse.json({ events });
  } catch (err) {
    console.error("me_timeline.query_failed", err);
    return NextResponse.json({ error: "timeline lookup failed" }, { status: 500 });
  }
}
