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
    // RETURNING the prior flag + email so we can (a) confirm the write landed
    // and (b) send a one-off confirmation email only on the OFF→ON transition.
    const rows = await sql`
      WITH before AS (
        SELECT id, email, (preferences ->> 'email_notify') AS prev
        FROM users WHERE firebase_uid = ${user.uid}
      )
      UPDATE users u
      SET preferences = u.preferences || jsonb_build_object('email_notify', ${body.emailNotify}::boolean)
      FROM before b
      WHERE u.id = b.id
      RETURNING b.id AS id, b.email AS email, b.prev AS prev
    `;
    const row = rows[0] ?? {};
    const wasOn = (row.prev as string | null) === "true"; // strict: default-on counts as off until explicitly enabled
    const toEmail = (row.email as string | null) ?? user.email ?? "";

    // Closes the feedback loop: enabling alerts emails the user a confirmation
    // (so the toggle visibly "did something"), with a one-click unsubscribe
    // link. Best-effort — a send failure or unconfigured RESEND/secret never
    // fails the preference write.
    if (body.emailNotify && !wasOn && toEmail) {
      const unsub = await unsubscribeUrl((row.id as string | null) ?? "");
      const { subject, html } = emailAlertsWelcome(unsub);
      const ok = await sendEmail(toEmail, subject, html);
      console.info("preferences.welcome_email", { to: toEmail.replace(/(.).+(@.*)/, "$1***$2"), sent: ok });
    }
    return NextResponse.json({ emailNotify: body.emailNotify });
  } catch (err) {
    console.error("preferences.put_failed", err);
    return NextResponse.json({ error: "preferences update failed" }, { status: 500 });
  }
}
