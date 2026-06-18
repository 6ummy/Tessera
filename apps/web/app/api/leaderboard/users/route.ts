// GET /api/leaderboard/users — PUBLIC investor leaderboard.
//
// Public users (is_public = true) ranked by their SINCE-FIRST-FOLLOW paper
// return — reconstructed from follow_events the same way the dashboard
// account curve is, so switching analysts (Warren→Cathie) carries the gains
// instead of resetting to 0. Each row also carries the persona-leaderboard
// metric set (1y / 90d / Sharpe 30d / MDD 30d), blank until the account is
// old enough. Exposes ONLY a display handle (nickname, else "Anonymous") +
// returns + the currently-followed persona — never email or the Google
// display_name. No auth: this is the public board.

import { NextResponse } from "next/server";
import { getSql } from "@/lib/db";
import { computeAccountMetrics } from "@/lib/account-metrics";
import type { FollowEvent } from "@/lib/account-curve";

export const runtime = "edge";
export const dynamic = "force-dynamic"; // never cache — profile edits sync live

const noStore = (body: unknown) =>
  NextResponse.json(body, { headers: { "cache-control": "no-store" } });

export async function GET() {
  try {
    const sql = getSql();

    // Public users + their handles.
    const users = await sql`SELECT id::text, nickname FROM users WHERE is_public = true`;
    if (users.length === 0) return noStore({ investors: [] });
    const nickById = new Map(
      users.map((u) => [u.id as string, ((u.nickname as string | null) ?? "").trim()]),
    );

    // Their full follow/unfollow history (account-curve source of truth).
    const evRows = await sql`
      SELECT fe.user_id::text, fe.persona_id, fe.action, fe.ts::text AS ts
      FROM follow_events fe
      JOIN users u ON u.id = fe.user_id
      WHERE u.is_public = true
      ORDER BY fe.user_id, fe.ts ASC
    `;
    const eventsByUser = new Map<string, FollowEvent[]>();
    for (const r of evRows) {
      const uid = r.user_id as string;
      const arr = eventsByUser.get(uid) ?? [];
      arr.push({
        personaId: r.persona_id as string,
        action: r.action as "follow" | "unfollow",
        ts: r.ts as string,
      });
      eventsByUser.set(uid, arr);
    }
    if (eventsByUser.size === 0) return noStore({ investors: [] });

    // Persona daily NAV series (one row per persona-day, real snapshot
    // preferred over the hypothetical backfill on overlapping days).
    const perfRows = await sql`
      SELECT DISTINCT ON (persona_id, ts::date)
             persona_id, (ts::date)::text AS d, total_value
      FROM persona_portfolios
      ORDER BY persona_id, ts::date, hypothetical ASC
    `;
    const seriesByPersona: Record<string, { date: string; value: number }[]> = {};
    const axisSet = new Set<string>();
    for (const r of perfRows) {
      const pid = r.persona_id as string;
      const date = String(r.d).slice(0, 10);
      (seriesByPersona[pid] ??= []).push({ date, value: Number(r.total_value) });
      axisSet.add(date);
    }
    const axis = [...axisSet].sort();

    const investors = [];
    for (const [uid, events] of eventsByUser) {
      const { metrics, firstFollow, currentPersonaId } = computeAccountMetrics(
        events, seriesByPersona, axis,
      );
      if (!firstFollow) continue; // never actually followed → nothing to rank
      investors.push({
        nickname: (nickById.get(uid) || "") || "Anonymous",
        personaId: currentPersonaId, // null = currently in cash
        startedAt: firstFollow,
        returnPct: metrics.sinceInception ?? 0,
        return1y: metrics.return1y,
        return90d: metrics.return90d,
        sharpe30d: metrics.sharpe30d,
        mdd30d: metrics.mdd30d,
      });
    }
    investors.sort((a, b) => b.returnPct - a.returnPct);
    return noStore({ investors });
  } catch (err) {
    console.error("leaderboard_users.query_failed", err);
    return NextResponse.json({ error: "leaderboard lookup failed" }, { status: 500 });
  }
}
