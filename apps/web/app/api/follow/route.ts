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
const VALID_PERSONAS = new Set(["warren", "cathie", "ray", "peter", "michael"]);
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
    // Ensure the user row exists.
    const urows = await sql`
      INSERT INTO users (firebase_uid, email, display_name, photo_url, last_login_at)
      VALUES (${user.uid}, ${user.email}, ${user.displayName}, ${user.photoUrl}, now())
      ON CONFLICT (firebase_uid) DO UPDATE SET last_login_at = now()
      RETURNING id
    `;
    const userId = urows[0].id as string;

    // SINGLE-FOLLOW: following an analyst switches your paper book — drop any
    // OTHER follow first (product decision 2026-06-16). The follow_events log
    // keeps the history so the account curve shows the switch.
    const removed = await sql`
      DELETE FROM user_portfolios
      WHERE user_id = ${userId} AND persona_id <> ${personaId}
      RETURNING persona_id
    `;
    // Seed the new paper book (no-op if already following this one).
    const added = await sql`
      INSERT INTO user_portfolios
        (user_id, persona_id, starting_capital, current_cash, total_value, current_positions)
      VALUES (${userId}, ${personaId}, ${STARTING_CAPITAL}, ${STARTING_CAPITAL}, ${STARTING_CAPITAL}, '{}'::jsonb)
      ON CONFLICT (user_id, persona_id) DO NOTHING
      RETURNING persona_id
    `;
    // Best-effort audit events (never fail the follow over logging).
    for (const r of removed) {
      await logEvent(sql, userId, r.persona_id as string, "unfollow");
    }
    if (added.length > 0) {
      await logEvent(sql, userId, personaId, "follow");
    }
    return NextResponse.json({
      following: true,
      personaId,
      switchedFrom: removed.map((r) => r.persona_id as string),
    });
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
    const rows = await sql`
      DELETE FROM user_portfolios
      WHERE persona_id = ${personaId}
        AND user_id = (SELECT id FROM users WHERE firebase_uid = ${user.uid})
      RETURNING user_id
    `;
    // Best-effort 'unfollow' event only when a row was actually removed.
    if (rows.length > 0) {
      await logEvent(sql, rows[0].user_id as string, personaId, "unfollow");
    }
    return NextResponse.json({ following: false, personaId });
  } catch (err) {
    console.error("follow.delete_failed", err);
    return NextResponse.json({ error: "unfollow failed" }, { status: 500 });
  }
}

/** Append a follow/unfollow audit row. Best-effort: a missing follow_events
 *  table (migration 013 not yet applied) or any error must NOT fail the
 *  follow/unfollow itself — the portfolio mutation is the source of truth. */
async function logEvent(
  sql: ReturnType<typeof getSql>,
  userId: string,
  personaId: string,
  action: "follow" | "unfollow",
): Promise<void> {
  try {
    await sql`
      INSERT INTO follow_events (user_id, persona_id, action)
      VALUES (${userId}, ${personaId}, ${action})
    `;
  } catch (err) {
    console.error("follow.event_log_failed", action, err);
  }
}
