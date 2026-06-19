// Minimal Resend HTTP client for transactional emails sent from the web
// (Edge-compatible — plain fetch). Mirrors the worker's notify/email.py
// pattern (one secret, RESEND_API_KEY). Gated on RESEND_API_KEY — unset →
// no-op (returns false) so the caller never breaks when email isn't wired.
// EMAIL_FROM defaults to the Resend sandbox sender, which only delivers to
// the Resend account owner (fine for the F&F pilot); set a verified-domain
// sender on Vercel for real delivery.

const RESEND_URL = "https://api.resend.com/emails";
const SITE_URL = "https://tessera-ruby.vercel.app";

/** Send one email. Best-effort: returns true on a 2xx, false otherwise
 *  (and never throws). */
export async function sendEmail(to: string, subject: string, html: string): Promise<boolean> {
  const key = process.env.RESEND_API_KEY;
  if (!key || !to) return false;
  const from = process.env.EMAIL_FROM || "Convt <onboarding@resend.dev>";
  try {
    const res = await fetch(RESEND_URL, {
      method: "POST",
      headers: { authorization: `Bearer ${key}`, "content-type": "application/json" },
      body: JSON.stringify({ from, to: [to], subject, html }),
    });
    if (!res.ok) {
      console.error("email.send_non_2xx", res.status, (await res.text().catch(() => "")).slice(0, 200));
      return false;
    }
    return true;
  } catch (err) {
    console.error("email.send_failed", err);
    return false;
  }
}

/** Confirmation email sent when a user turns email alerts ON — closes the
 *  feedback loop so the toggle visibly "did something". `unsubUrl`, when
 *  present, is a one-click opt-out link in the footer. */
export function emailAlertsWelcome(unsubUrl?: string | null): { subject: string; html: string } {
  const url = `${SITE_URL}/dashboard`;
  const subject = "Email alerts are on — Convt";
  const optOut = unsubUrl
    ? `You can <a href="${unsubUrl}" style="color:#7C7870">unsubscribe in one click</a> or toggle alerts off in your dashboard.`
    : "You can turn alerts off anytime from your dashboard.";
  const html =
    '<div style="font-family:system-ui,-apple-system,sans-serif;max-width:520px">' +
    '<h2 style="font-weight:600;color:#1F1E1B">Email alerts are on.</h2>' +
    "<p style=\"color:#3B3A36;line-height:1.55\">You'll get an email whenever the analyst you " +
    "follow rebalances their book — so your paper portfolio's moves never take you by surprise.</p>" +
    `<p><a href="${url}" style="display:inline-block;background:#1F1E1B;color:#FAF9F5;` +
    'padding:10px 18px;border-radius:9999px;text-decoration:none">Open your dashboard</a></p>' +
    `<p style="color:#7C7870;font-size:12px">Paper trading only — no real money. ${optOut}</p>` +
    "</div>";
  return { subject, html };
}
