// GET /api/me/portfolios — the signed-in user's paper portfolios (their
// follows). Powers the dashboard "My portfolio" tab.
//
// Positions are PROJECTED LIVE on read from the persona's latest book +
// the freshest ohlcv close per ticker — the exact same weight projection
// the nightly mirror engine persists (risk/mirror.py::project_follower_book),
// run here at request time so a fresh follow/switch shows positions
// immediately instead of waiting for the next nightly sync. The stored
// current_positions/cash/total_value are the fallback when the persona has
// no snapshot yet.
//
// User derived from the verified Firebase token only. Edge runtime.

import { NextResponse } from "next/server";
import { getSql } from "@/lib/db";
import { verifyFirebaseToken } from "@/lib/firebase/verify-token";

export const runtime = "edge";

type Position = { qty: number; close: number; value: number };

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
    const follows = await sql`
      SELECT p.persona_id, p.starting_capital, p.current_cash, p.total_value,
             p.current_positions, p.started_at
      FROM user_portfolios p
      JOIN users u ON u.id = p.user_id
      WHERE u.firebase_uid = ${user.uid} AND p.mode = 'paper'
      ORDER BY p.started_at ASC
    `;
    if (follows.length === 0) return NextResponse.json({ portfolios: [] });

    // Latest persona book snapshot per followed persona ({ticker:{qty,close,value}}).
    const personaIds = [...new Set(follows.map((f) => f.persona_id as string))];
    const snaps = await sql`
      SELECT DISTINCT ON (persona_id) persona_id, positions, cash, total_value
      FROM persona_portfolios
      WHERE persona_id = ANY(${personaIds})
      ORDER BY persona_id, ts DESC
    `;
    const snapByPersona = new Map(snaps.map((s) => [s.persona_id as string, s]));

    // Freshest close per ticker across every snapshot (ohlcv invariant:
    // newest calendar day, source priority alpaca/coinbase > yahoo > other).
    const tickers = new Set<string>();
    for (const s of snapByPersona.values()) {
      for (const t of Object.keys((s.positions ?? {}) as Record<string, unknown>)) tickers.add(t);
    }
    const closeByTicker = new Map<string, number>();
    if (tickers.size > 0) {
      const closes = await sql`
        SELECT DISTINCT ON (ticker) ticker, close
        FROM ohlcv_1d
        WHERE ticker = ANY(${[...tickers]})
        ORDER BY ticker, ts::date DESC,
          CASE source WHEN 'alpaca' THEN 0 WHEN 'coinbase' THEN 0 WHEN 'yahoo' THEN 1 ELSE 2 END
      `;
      for (const c of closes) closeByTicker.set(c.ticker as string, Number(c.close));
    }

    const portfolios = [];
    for (const f of follows) {
      const personaId = f.persona_id as string;
      const snap = snapByPersona.get(personaId);
      let positions = (f.current_positions ?? {}) as Record<string, Position>;
      let currentCash = Number(f.current_cash);
      let totalValue = Number(f.total_value);
      let live = false;

      const navToday = snap ? Number(snap.total_value) : 0;
      if (snap && navToday > 0) {
        // Persona NAV on the latest snapshot at/before the follow date = baseline.
        const baseRows = await sql`
          SELECT total_value FROM persona_portfolios
          WHERE persona_id = ${personaId} AND ts::date <= ${f.started_at}::date
          ORDER BY ts DESC LIMIT 1
        `;
        const base = baseRows.length > 0 ? Number(baseRows[0].total_value) : navToday;
        if (base > 0) {
          // follower_nav = starting_capital * (nav_today / nav_at_start) — so
          // the follower's return since following == the persona's. Holdings
          // carry the persona's weights, re-priced at the freshest close.
          const followerNav = Number(f.starting_capital) * (navToday / base);
          const raw = (snap.positions ?? {}) as Record<string, Position>;
          const out: Record<string, Position> = {};
          for (const [ticker, pos] of Object.entries(raw)) {
            const qty = Number(pos?.qty) || 0;
            if (qty <= 0) continue;
            const price = closeByTicker.get(ticker) ?? Number(pos?.close) ?? 0;
            if (!price || price <= 0) continue; // dropped weight falls to cash
            const weight = (qty * price) / navToday;
            const value = followerNav * weight;
            out[ticker] = { qty: Number((value / price).toFixed(6)), close: price, value: Number(value.toFixed(2)) };
          }
          positions = out;
          currentCash = Number((followerNav * (Number(snap.cash) / navToday)).toFixed(2));
          totalValue = Number(followerNav.toFixed(2));
          live = true;
        }
      }

      portfolios.push({
        personaId,
        startingCapital: Number(f.starting_capital),
        currentCash,
        totalValue,
        positions,
        startedAt: f.started_at as string,
        live,
      });
    }
    return NextResponse.json({ portfolios });
  } catch (err) {
    console.error("me_portfolios.query_failed", err);
    return NextResponse.json({ error: "portfolio lookup failed" }, { status: 500 });
  }
}
