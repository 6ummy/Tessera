// POST /api/auth/sync — verify the caller's Firebase ID token and upsert
// their `users` row. Called by the client right after Google sign-in (and on
// token refresh). This is the ONLY writer of the users table; nothing trusts
// a client-supplied uid — we derive it from the verified token.
//
// Edge runtime: both jose (verification) and @neondatabase/serverless (the
// upsert) are fetch-based and Edge-native, matching the rest of the web app.

import { NextResponse } from "next/server";
import { getSql } from "@/lib/db";
import { verifyFirebaseToken } from "@/lib/firebase/verify-token";

export const runtime = "edge";

export async function POST(req: Request) {
  // Bearer <Firebase ID token>. The token is the trust boundary — the uid
  // and profile fields come from its verified claims, never from the body.
  const authz = req.headers.get("authorization") ?? "";
  const idToken = authz.toLowerCase().startsWith("bearer ")
    ? authz.slice(7).trim()
    : "";
  if (!idToken) {
    return NextResponse.json({ error: "missing bearer token" }, { status: 401 });
  }

  let user;
  try {
    user = await verifyFirebaseToken(idToken);
  } catch (err) {
    // Bad signature / wrong project / expired — all 401, logged for audit.
    console.error("auth_sync.verify_failed", err);
    return NextResponse.json({ error: "invalid token" }, { status: 401 });
  }

  try {
    const sql = getSql();
    const rows = await sql`
      INSERT INTO users (firebase_uid, email, display_name, photo_url, last_login_at)
      VALUES (${user.uid}, ${user.email}, ${user.displayName}, ${user.photoUrl}, now())
      ON CONFLICT (firebase_uid) DO UPDATE SET
        email         = EXCLUDED.email,
        display_name  = EXCLUDED.display_name,
        photo_url     = EXCLUDED.photo_url,
        last_login_at = now()
      RETURNING id, firebase_uid, email, display_name, photo_url, created_at, last_login_at
    `;
    return NextResponse.json({ user: rows[0] });
  } catch (err) {
    // Don't leak DB internals to the client; log loudly (no silent failures).
    console.error("auth_sync.upsert_failed", err);
    return NextResponse.json({ error: "user sync failed" }, { status: 500 });
  }
}
