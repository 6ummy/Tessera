// GET /api/cron/broker-sync — nightly refresh of every connected Alpaca paper
// account's return into users.preferences.broker_return, so the PUBLIC
// leaderboard ranks connected users by their REAL account independently of
// whether they opened their dashboard.
//
// Why a web cron (not the worker): the web is already the one place that holds
// the AES key + decrypts the per-user broker keys, so this adds NO new place
// that touches the keys. Decryption is in-memory + never logged; the keys stay
// AES-256-GCM encrypted at rest. Paper-only.
//
// Auth: Cloud Scheduler / Vercel cron sends `Authorization: Bearer ${CRON_SECRET}`.
// Trigger nightly after the worker's daily ingest.

import { NextResponse } from "next/server";
import { getSql } from "@/lib/db";
import { listAlpacaConnections, accountSummary } from "@/lib/broker-mirror";

export const runtime = "edge";
export const dynamic = "force-dynamic";

async function run(req: Request) {
  if (process.env.FEATURE_BROKER_CONNECT !== "true") {
    return NextResponse.json({ ok: false, error: "broker connect disabled" }, { status: 403 });
  }
  const cronSecret = process.env.CRON_SECRET;
  if (!cronSecret) {
    return NextResponse.json({ ok: false, error: "CRON_SECRET not set on the server" }, { status: 500 });
  }
  if ((req.headers.get("authorization") ?? "") !== `Bearer ${cronSecret}`) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }

  const sql = getSql();
  let conns: Awaited<ReturnType<typeof listAlpacaConnections>>;
  try {
    conns = await listAlpacaConnections();
  } catch (err) {
    console.error("cron_broker_sync.list_failed", err);
    return NextResponse.json({ ok: false, error: "could not list connections" }, { status: 502 });
  }

  let synced = 0;
  let failed = 0;
  for (const { userId, keys, startingCapital } of conns) {
    try {
      const summary = await accountSummary(keys);
      // Return is relative to the user's own starting capital (default $100K) —
      // each Alpaca paper account can start at a different balance.
      const brokerReturn = summary.equity / startingCapital - 1;
      await sql`
        UPDATE users
        SET preferences = jsonb_set(coalesce(preferences, '{}'::jsonb),
                                    '{broker_return}', to_jsonb(${brokerReturn}::numeric), true)
        WHERE id::text = ${userId}
      `;
      synced++;
    } catch (err) {
      console.error("cron_broker_sync.user_failed", userId, err);
      failed++;
    }
  }
  return NextResponse.json({ ok: true, connected: conns.length, synced, failed });
}

export const GET = run;
export const POST = run; // allow manual local testing with the same auth
