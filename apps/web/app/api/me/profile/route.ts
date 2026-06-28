// GET/PUT /api/me/profile — the signed-in user's public profile
// (nickname + is_public). User derived from the verified token only.

import { NextResponse } from "next/server";
import { getSql } from "@/lib/db";
import { verifyFirebaseToken } from "@/lib/firebase/verify-token";

export const runtime = "edge";

const NICK_MAX = 24;

async function verify(req: Request) {
  const authz = req.headers.get("authorization") ?? "";
  const token = authz.toLowerCase().startsWith("bearer ") ? authz.slice(7).trim() : "";
  if (!token) return null;
  try {
    return await verifyFirebaseToken(token);
  } catch (err) {
    console.error("profile.verify_failed", err);
    return null;
  }
}

export async function GET(req: Request) {
  const user = await verify(req);
  if (!user) return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  try {
    const sql = getSql();
    const rows = await sql`
      SELECT nickname, is_public, preferences FROM users WHERE firebase_uid = ${user.uid}
    `;
    const r = rows[0] ?? {};
    const prefs = (r.preferences ?? {}) as Record<string, unknown>;
    return NextResponse.json({
      nickname: (r.nickname as string | null) ?? null,
      isPublic: r.is_public !== false,
      startingCapital: Number(prefs.starting_capital) || 100_000,
    });
  } catch (err) {
    console.error("profile.get_failed", err);
    return NextResponse.json({ error: "profile lookup failed" }, { status: 500 });
  }
}

export async function PUT(req: Request) {
  const user = await verify(req);
  if (!user) return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  const body = (await req.json().catch(() => ({}))) as { nickname?: string; isPublic?: boolean };

  // Build a partial update; only touch fields actually provided.
  let nickname: string | null | undefined;
  if (body.nickname !== undefined) {
    const trimmed = (body.nickname ?? "").trim().slice(0, NICK_MAX);
    nickname = trimmed === "" ? null : trimmed;
  }
  const isPublic = typeof body.isPublic === "boolean" ? body.isPublic : undefined;
  if (nickname === undefined && isPublic === undefined) {
    return NextResponse.json({ error: "nothing to update" }, { status: 400 });
  }

  try {
    const sql = getSql();
    // COALESCE keeps the existing value when a field wasn't provided.
    const rows = await sql`
      UPDATE users SET
        nickname  = CASE WHEN ${nickname !== undefined} THEN ${nickname ?? null} ELSE nickname END,
        is_public = COALESCE(${isPublic ?? null}, is_public)
      WHERE firebase_uid = ${user.uid}
      RETURNING nickname, is_public
    `;
    const r = rows[0] ?? {};
    return NextResponse.json({
      nickname: (r.nickname as string | null) ?? null,
      isPublic: r.is_public !== false,
    });
  } catch (err) {
    console.error("profile.put_failed", err);
    return NextResponse.json({ error: "profile update failed" }, { status: 500 });
  }
}
