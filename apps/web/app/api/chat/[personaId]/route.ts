/**
 * Chat proxy — forwards user messages to the Cloud Run worker's
 * SSE-streaming Anthropic endpoint and pipes the stream back to the
 * client unchanged.
 *
 * Why proxy via Vercel rather than calling the worker directly from the
 * browser:
 *   - Single origin (no CORS dance), Vercel serves the whole site
 *   - Vercel injects the WORKER_WEBHOOK_SECRET so the browser never sees it
 *   - Future: same proxy adds auth (Phase D) + rate limiting per user
 *
 * Vercel Edge: 60s function timeout on hobby tier. Most Sonnet 4.6 chat
 * replies finish in 5–30s; the headroom is comfortable. If chat grows
 * beyond that, the worker can already stream for minutes — Edge limit
 * is the constraint, not Cloud Run.
 *
 * Request body: { message: string, history?: ChatMessage[] }
 * Response: text/event-stream — each token as `data: <delta>\n\n`, ends
 * with `data: [DONE]\n\n`.
 */

import { NextResponse } from "next/server";
import { buildWorkerAuthHeader, workerBaseUrl } from "@/lib/gcp-auth";

export const runtime = "edge";
export const dynamic = "force-dynamic";

const VALID_PERSONAS = new Set(["warren", "cathie", "ray", "peter", "michael"]);

// ── Abuse guards (2026-06-11 audit Step 2) ────────────────────────────
// This endpoint is public until Phase D auth lands. Three layers:
//   1. per-IP rate limit here (best-effort: the Map is per edge isolate,
//      so a determined attacker spread across regions sees a higher
//      effective limit — acceptable; the worker's budget pools are the
//      hard backstop)
//   2. message/history size caps here (cheap reject before the worker)
//   3. worker-side caps + a chat-only daily budget pool (the real gate)
const RATE_LIMIT_WINDOW_MS = 60_000;
const RATE_LIMIT_MAX_PER_WINDOW = 10;
const MAX_MESSAGE_CHARS = 4_000;
const MAX_HISTORY_TURNS = 20;

const rateHits = new Map<string, number[]>();

function isRateLimited(ip: string): boolean {
  const now = Date.now();
  const recent = (rateHits.get(ip) ?? []).filter(
    (t) => now - t < RATE_LIMIT_WINDOW_MS,
  );
  if (recent.length >= RATE_LIMIT_MAX_PER_WINDOW) {
    rateHits.set(ip, recent);
    return true;
  }
  recent.push(now);
  rateHits.set(ip, recent);
  // Bound the map so a scan across many IPs can't grow isolate memory.
  if (rateHits.size > 10_000) rateHits.clear();
  return false;
}

export async function POST(
  req: Request,
  { params }: { params: { personaId: string } },
) {
  const { personaId } = params;
  if (!VALID_PERSONAS.has(personaId)) {
    return NextResponse.json(
      { ok: false, error: `unknown persona: ${personaId}` },
      { status: 400 },
    );
  }

  const ip =
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "unknown";
  if (isRateLimited(ip)) {
    return NextResponse.json(
      { ok: false, error: "rate_limited", retryAfterSeconds: 60 },
      { status: 429, headers: { "retry-after": "60" } },
    );
  }

  const base = workerBaseUrl();
  if (!base) {
    return NextResponse.json(
      {
        ok: false,
        error: "WORKER_WEBHOOK_URL not configured",
        hint: "set on Vercel project env; format: https://tessera-worker-...run.app",
      },
      { status: 503 },
    );
  }

  const body = await req.json().catch(() => ({}));
  if (!body.message || typeof body.message !== "string") {
    return NextResponse.json(
      { ok: false, error: "missing or invalid 'message'" },
      { status: 400 },
    );
  }
  if (body.message.length > MAX_MESSAGE_CHARS) {
    return NextResponse.json(
      { ok: false, error: `message too long (max ${MAX_MESSAGE_CHARS} chars)` },
      { status: 400 },
    );
  }
  const history = Array.isArray(body.history)
    ? body.history.slice(-MAX_HISTORY_TURNS)
    : [];

  // Forward to the worker's /api/chat/<persona> endpoint. The worker
  // returns text/event-stream; we pipe it through unchanged.
  const chatUrl = `${base}/api/chat/${personaId}`;
  const authHeader = await buildWorkerAuthHeader(base);

  let upstream: Response;
  try {
    upstream = await fetch(chatUrl, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...authHeader,
      },
      body: JSON.stringify({
        message: body.message,
        history,
      }),
      // No AbortSignal.timeout here — we want the stream to run as long
      // as the worker keeps producing. Vercel's own 60s edge timeout is
      // the upper bound on the function.
    });
  } catch (err) {
    return NextResponse.json(
      {
        ok: false,
        error: "worker_unreachable",
        detail: err instanceof Error ? err.message : String(err),
      },
      { status: 502 },
    );
  }

  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text().catch(() => "");
    return NextResponse.json(
      { ok: false, error: "worker_error", status: upstream.status, body: text },
      { status: 502 },
    );
  }

  // Pipe the SSE stream through unchanged. Edge runtime supports
  // ReadableStream natively, so this is a one-liner.
  return new Response(upstream.body, {
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-cache, no-transform",
      "x-accel-buffering": "no",
    },
  });
}
