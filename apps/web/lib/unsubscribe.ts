// One-click email-unsubscribe links. The link must work WITHOUT login (you
// click it from your inbox), so it carries an HMAC-SHA256 token over the
// user id — anyone can disable their OWN alerts, nobody can disable someone
// else's. The same scheme is minted on the worker side (notify/email.py) for
// rebalance emails, so the shared UNSUBSCRIBE_SECRET must match on both
// Vercel and Cloud Run. Unset → no link is produced (and verify fails closed).

const SITE_URL = "https://tessera-ruby.vercel.app";

async function hmacHex(secret: string, message: string): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Build the unsubscribe URL for a user id, or null when no secret is set. */
export async function unsubscribeUrl(userId: string): Promise<string | null> {
  const secret = process.env.UNSUBSCRIBE_SECRET;
  if (!secret || !userId) return null;
  const t = await hmacHex(secret, userId);
  return `${SITE_URL}/api/unsubscribe?u=${encodeURIComponent(userId)}&t=${t}`;
}

/** Constant-time verify of an unsubscribe token against the user id. */
export async function verifyUnsubToken(userId: string, token: string): Promise<boolean> {
  const secret = process.env.UNSUBSCRIBE_SECRET;
  if (!secret || !userId || !token) return false;
  const expected = await hmacHex(secret, userId);
  if (expected.length !== token.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i++) diff |= expected.charCodeAt(i) ^ token.charCodeAt(i);
  return diff === 0;
}
