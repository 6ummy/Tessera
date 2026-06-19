// GET /api/unsubscribe?u=<userId>&t=<hmac> — one-click email opt-out from a
// link in a notification email. Public (no login), but the HMAC token over
// the user id means a link only disables ITS OWN account's alerts. Sets
// users.preferences.email_notify = false and renders a small confirmation
// page with a way back to re-enable.

import { getSql } from "@/lib/db";
import { verifyUnsubToken } from "@/lib/unsubscribe";

export const runtime = "edge";
export const dynamic = "force-dynamic";

const SITE_URL = "https://convt.xyz";

function page(title: string, body: string, status = 200): Response {
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title></head>
<body style="font-family:system-ui,-apple-system,sans-serif;background:#FAF9F5;color:#1F1E1B;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0">
<div style="max-width:460px;padding:32px;text-align:center">
<h1 style="font-weight:600;font-size:22px">${title}</h1>
<p style="color:#3B3A36;line-height:1.55">${body}</p>
<p><a href="${SITE_URL}/dashboard" style="display:inline-block;background:#1F1E1B;color:#FAF9F5;padding:10px 18px;border-radius:9999px;text-decoration:none">Go to dashboard</a></p>
</div></body></html>`;
  return new Response(html, {
    status,
    headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" },
  });
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const u = url.searchParams.get("u") ?? "";
  const t = url.searchParams.get("t") ?? "";

  if (!(await verifyUnsubToken(u, t))) {
    return page(
      "Link invalid or expired",
      "We couldn't verify this unsubscribe link. You can manage email alerts from your dashboard.",
      400,
    );
  }
  try {
    const sql = getSql();
    await sql`
      UPDATE users
      SET preferences = preferences || jsonb_build_object('email_notify', false)
      WHERE id = ${u}::uuid
    `;
    return page(
      "Email alerts off",
      "You won't receive rebalance emails anymore. You can turn them back on anytime from your dashboard.",
    );
  } catch (err) {
    console.error("unsubscribe.failed", err);
    return page(
      "Something went wrong",
      "We couldn't update your preference. Please try again from your dashboard.",
      500,
    );
  }
}
