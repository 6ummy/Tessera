// GET /api/me/portfolios — the signed-in user's paper portfolios (their
// follows). Powers the dashboard "My portfolio" tab. The positions/cash/
// total_value are kept current by the worker's nightly mirror engine.
//
// User derived from the verified Firebase token only. Edge runtime.

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
    console.error("me_portfolios.verify_failed", err);
    return NextResponse.json({ error: "invalid token" }, { status: 401 });
  }

  try {
    const sql = getSql();
    const rows = await sql`
      SELECT p.persona_id, p.starting_capital, p.current_cash, p.total_value,
             p.current_positions, p.started_at
      FROM user_portfolios p
      JOIN users u ON u.id = p.user_id
      WHERE u.firebase_uid = ${user.uid}
      ORDER BY p.started_at ASC
    `;
    const portfolios = rows.map((r) => ({
      personaId: r.persona_id as string,
      startingCapital: Number(r.starting_capital),
      currentCash: Number(r.current_cash),
      totalValue: Number(r.total_value),
      // current_positions is JSONB {ticker: {qty, close, value}} — empty
      // {} until the mirror engine runs the night after a follow.
      positions: (r.current_positions ?? {}) as Record<
        string,
        { qty: number; close: number; value: number }
      >,
      startedAt: r.started_at as string,
    }));
    return NextResponse.json({ portfolios });
  } catch (err) {
    console.error("me_portfolios.query_failed", err);
    return NextResponse.json({ error: "portfolio lookup failed" }, { status: 500 });
  }
}
