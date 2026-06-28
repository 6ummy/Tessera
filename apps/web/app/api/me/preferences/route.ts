// GET/PUT /api/me/preferences — the signed-in user's notification prefs.
// Currently just emailNotify (rebalance email opt-in/out). Stored in
// users.preferences JSONB. User derived from the verified token only.

import { NextResponse } from "next/server";
import { getSql } from "@/lib/db";
import { verifyFirebaseToken } from "@/lib/firebase/verify-token";
import { sendEmail, emailAlertsWelcome } from "@/lib/email";
import { unsubscribeUrl } from "@/lib/unsubscribe";

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
    return NextResponse.json({
      emailNotify: prefs.email_notify !== false,
      startingCapital: Number(prefs.starting_capital) || 100_000,
    });
  } catch (err) {
    console.error("preferences.get_failed", err);
    return NextResponse.json({ error: "preferences lookup failed" }, { status: 500 });
  }
}

export async function PUT(req: Request) {
  const user = await verify(req);
  if (!user) return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  const body = (await req.json().catch(() => ({}))) as { emailNotify?: boolean; startingCapital?: number };

  // Starting-capital update (Alpaca users set their real paper account's
  // starting balance — the return denominator). Independent of emailNotify;
  // handled first and returns on its own.
  if (typeof body.startingCapital === "number") {
    const cap = Math.round(body.startingCapital);
    if (!Number.isFinite(cap) || cap < 1) {
      return NextResponse.json({ error: "startingCapital must be a positive number" }, { status: 400 });
    }
    try {
      const sql = getSql();
      await sql`
        UPDATE users
        SET preferences = coalesce(preferences, '{}'::jsonb) || jsonb_build_object('starting_capital', ${cap}::int)
        WHERE firebase_uid = ${user.uid}
      `;
      return NextResponse.json({ startingCapital: cap });
    } catch (err) {
      console.error("preferences.capital_put_failed", err);
      return NextResponse.json({ error: "preferences update failed" }, { status: 500 });
    }
  }

  if (typeof body.emailNotify !== "boolean") {
    return NextResponse.json({ error: "emailNotify (boolean) or startingCapital (number) required" }, { status: 400 });
  }
  try {
    const sql = getSql();
    const rows = await sql`
      UPDATE users
      SET preferences = preferences || jsonb_build_object('email_notify', ${body.emailNotify}::boolean)
      WHERE firebase_uid = ${user.uid}
      RETURNING id::text AS id, email
    `;
    const row = rows[0] ?? {};
    const toEmail = (row.email as string | null) ?? user.email ?? "";

    // Turning alerts ON sends a confirmation email (with a one-click
    // unsubscribe link) every time, so the toggle visibly "did something"
    // and the UI can report the real send result. Best-effort — a failure or
    // unconfigured RESEND never fails the preference write.
    let welcome: { sent: boolean; to: string } | null = null;
    if (body.emailNotify) {
      if (toEmail) {
        const unsub = await unsubscribeUrl((row.id as string | null) ?? "");
        const { subject, html } = emailAlertsWelcome(unsub);
        const sent = await sendEmail(toEmail, subject, html);
        welcome = { sent, to: maskEmail(toEmail) };
        console.info("preferences.welcome_email", { to: maskEmail(toEmail), sent });
      } else {
        welcome = { sent: false, to: "" }; // no email on file
        console.warn("preferences.welcome_email_no_address", { uid: user.uid });
      }
    }
    return NextResponse.json({ emailNotify: body.emailNotify, welcome });
  } catch (err) {
    console.error("preferences.put_failed", err);
    return NextResponse.json({ error: "preferences update failed" }, { status: 500 });
  }
}

function maskEmail(e: string): string {
  return e.replace(/(.).+(@.*)/, "$1***$2");
}
