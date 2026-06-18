// GET /api/leaderboard/users — PUBLIC investor leaderboard.
//
// Public users (is_public = true) ranked by their since-follow paper return
// (total_value / starting_capital − 1). Exposes ONLY a display handle
// (nickname, else "Anonymous") + the return + which persona they follow —
// never email or the Google display_name. No auth: this is the public board.

import { NextResponse } from "next/server";
import { getSql } from "@/lib/db";

export const runtime = "edge";

export async function GET() {
  try {
    const sql = getSql();
    const rows = await sql`
      SELECT u.nickname, p.persona_id, p.starting_capital, p.total_value, p.started_at
      FROM user_portfolios p
      JOIN users u ON u.id = p.user_id
      WHERE u.is_public = true AND p.starting_capital > 0
    `;
    const investors = rows
      .map((r) => ({
        nickname: ((r.nickname as string | null) ?? "").trim() || "Anonymous",
        personaId: r.persona_id as string,
        returnPct: Number(r.total_value) / Number(r.starting_capital) - 1,
        startedAt: r.started_at as string,
      }))
      .sort((a, b) => b.returnPct - a.returnPct);
    return NextResponse.json({ investors });
  } catch (err) {
    console.error("leaderboard_users.query_failed", err);
    return NextResponse.json({ error: "leaderboard lookup failed" }, { status: 500 });
  }
}
