// /api/follow — a user's "Follow this persona" relationship.
//
// A follow IS a paper portfolio: following persona X seeds a user_portfolios
// row (user_id, persona_id, $100K) and unfollowing deletes it. user_portfolios
// already exists from 001_init §5, so no migration is needed — this route is
// just its writer for the user-driven path.
//
//   GET    → { personaIds: [...] }   the caller's followed personas
//   POST   { personaId } → seed the $100K paper portfolio (idempotent)
//   DELETE { personaId } → unfollow (drop the portfolio)
//
// Every method derives the user from the verified Firebase token — never a
// client-supplied id. Edge runtime (jose + neon, both fetch-based).

import { NextResponse } from "next/server";
import { getSql } from "@/lib/db";
import { verifyFirebaseToken } from "@/lib/firebase/verify-token";

export const runtime = "edge";

// The four personas — server-side allowlist so a follow can't seed a
// portfolio for a bogus persona id.
const VALID_PERSONAS = new Set(["warren", "cathie", "ray", "peter"]);
const STARTING_CAPITAL = 100_000;

async function verify(req: Request) {
  const authz = req.headers.get("authorization") ?? "";
  const token = authz.toLowerCase().startsWith("bearer ") ? authz.slice(7).trim() : "";
  if (!token) return null;
  try {
    return await verifyFirebaseToken(token);
  } catch (err) {
    console.error("follow.verify_failed", err);
    return null;
  }
}

export async function GET(req: Request) {
  const user = await verify(req);
  if (!user) return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  try {
    const sql = getSql();
    const rows = await sql`
      SELECT p.persona_id
      FROM user_portfolios p
      JOIN users u ON u.id = p.user_id
      WHERE u.firebase_uid = ${user.uid}
    `;
    return NextResponse.json({ personaIds: rows.map((r) => r.persona_id) });
  } catch (err) {
    console.error("follow.list_failed", err);
    return NextResponse.json({ error: "follow lookup failed" }, { status: 500 });
  }
}

export async function POST(req: Request) {
  const user = await verify(req);
  if (!user) return NextResponse.json({ error: "unauthenticated" }, { status: 401 });

  const { personaId } = (await req.json().catch(() => ({}))) as { personaId?: string };
  if (!personaId || !VALID_PERSONAS.has(personaId)) {
    return NextResponse.json({ error: "invalid personaId" }, { status: 400 });
  }

  try {
    const sql = getSql();
    // Ensure the user row exists (it does after sign-in) AND seed the paper
    // portfolio in one statement. ON CONFLICT makes a repeat follow a no-op.
    await sql`
      WITH u AS (
        INSERT INTO users (firebase_uid, email, display_name, photo_url, last_login_at)
        VALUES (${user.uid}, ${user.email}, ${user.displayName}, ${user.photoUrl}, now())
        ON CONFLICT (firebase_uid) DO UPDATE SET last_login_at = now()
        RETURNING id
      )
      INSERT INTO user_portfolios
        (user_id, persona_id, starting_capital, current_cash, total_value, current_positions)
      SELECT u.id, ${personaId}, ${STARTING_CAPITAL}, ${STARTING_CAPITAL}, ${STARTING_CAPITAL}, '{}'::jsonb
      FROM u
      ON CONFLICT (user_id, persona_id) DO NOTHING
    `;
    return NextResponse.json({ following: true, personaId });
  } catch (err) {
    console.error("follow.create_failed", err);
    return NextResponse.json({ error: "follow failed" }, { status: 500 });
  }
}

export async function DELETE(req: Request) {
  const user = await verify(req);
  if (!user) return NextResponse.json({ error: "unauthenticated" }, { status: 401 });

  const { personaId } = (await req.json().catch(() => ({}))) as { personaId?: string };
  if (!personaId || !VALID_PERSONAS.has(personaId)) {
    return NextResponse.json({ error: "invalid personaId" }, { status: 400 });
  }

  try {
    const sql = getSql();
    await sql`
      DELETE FROM user_portfolios
      WHERE persona_id = ${personaId}
        AND user_id = (SELECT id FROM users WHERE firebase_uid = ${user.uid})
    `;
    return NextResponse.json({ following: false, personaId });
  } catch (err) {
    console.error("follow.delete_failed", err);
    return NextResponse.json({ error: "unfollow failed" }, { status: 500 });
  }
}
