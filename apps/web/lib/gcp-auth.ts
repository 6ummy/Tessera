/**
 * GCP service-account → identity token minter for Vercel Edge runtime.
 *
 * Why this exists: once `tessera-worker` Cloud Run flips to
 * `--no-allow-unauthenticated`, the only callers it accepts are
 * identities holding `roles/run.invoker`. Vercel Edge proxies are
 * outside GCP, so we sign a self-JWT with the `tessera-vercel` service
 * account's private key, exchange it at Google's token endpoint for an
 * audience-scoped identity token, and present that as `Bearer` to the
 * worker. The worker's IAM check validates the token issuer + audience
 * + invoker role and either accepts or 403s — no per-call shared secret.
 *
 * Why `jose` and not `google-auth-library`: the official Google libs
 * pull in Node-only APIs (fs, crypto) that Edge runtime doesn't expose.
 * `jose` is Web-Crypto-native and works in Edge without polyfills.
 *
 * Env shape: `GCP_SA_KEY_B64` — a single base64-encoded blob of the
 * SA JSON key file. Multi-line PEM private keys break Vercel's env
 * editor without the base64 wrapper. Decode at runtime here.
 *
 * Caching: id tokens are valid 1 hour. We cache per (target audience)
 * with a small safety margin (refresh at 50 min) so a steady proxy
 * mints maybe 24 tokens/day total across all routes.
 */

import { SignJWT, importPKCS8 } from "jose";

type CachedToken = { token: string; expiresAt: number };

const cache = new Map<string, CachedToken>();
const REFRESH_MARGIN_MS = 10 * 60 * 1000; // 10 min before the 1h expiry
const TOKEN_TTL_S = 3600;

type SaKey = {
  client_email: string;
  private_key: string;
  token_uri?: string;
};

let _saKeyCache: SaKey | null = null;

function loadSaKey(): SaKey | null {
  if (_saKeyCache) return _saKeyCache;
  const b64 = process.env.GCP_SA_KEY_B64;
  if (!b64) return null;
  try {
    // atob in Edge runtime returns a binary string; pass through
    // TextDecoder to get UTF-8 cleanly.
    const json = JSON.parse(
      new TextDecoder().decode(
        Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)),
      ),
    );
    if (!json.client_email || !json.private_key) return null;
    _saKeyCache = {
      client_email: json.client_email,
      private_key: json.private_key,
      token_uri: json.token_uri ?? "https://oauth2.googleapis.com/token",
    };
    return _saKeyCache;
  } catch (err) {
    console.error("gcp-auth.parse_failed", err);
    return null;
  }
}

/**
 * Returns an ID token usable as `Bearer <token>` against a Cloud Run
 * service whose audience matches `targetAudience` (i.e. the service URL
 * without a trailing path). Returns null when SA key isn't configured —
 * caller should fall back to the legacy `WORKER_WEBHOOK_SECRET` bearer
 * so a partial rollout stays unbroken.
 */
export async function getIdentityToken(
  targetAudience: string,
): Promise<string | null> {
  const sa = loadSaKey();
  if (!sa) return null;

  const cached = cache.get(targetAudience);
  if (cached && cached.expiresAt - REFRESH_MARGIN_MS > Date.now()) {
    return cached.token;
  }

  try {
    // Step 1 — sign a self-JWT addressed to Google's token endpoint with
    // a `target_audience` claim set to the Cloud Run service URL. The
    // identity-token flow swaps this for an OIDC token whose `aud`
    // matches that target_audience.
    const now = Math.floor(Date.now() / 1000);
    const privateKey = await importPKCS8(sa.private_key, "RS256");
    const assertion = await new SignJWT({
      target_audience: targetAudience,
    })
      .setProtectedHeader({ alg: "RS256", typ: "JWT" })
      .setIssuer(sa.client_email)
      .setSubject(sa.client_email)
      .setAudience(sa.token_uri ?? "https://oauth2.googleapis.com/token")
      .setIssuedAt(now)
      .setExpirationTime(now + TOKEN_TTL_S)
      .sign(privateKey);

    // Step 2 — exchange the assertion for an id_token via OAuth grant.
    const resp = await fetch(
      sa.token_uri ?? "https://oauth2.googleapis.com/token",
      {
        method: "POST",
        headers: { "content-type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
          assertion,
        }),
      },
    );
    if (!resp.ok) {
      const detail = await resp.text().catch(() => "");
      console.error("gcp-auth.token_exchange_failed", resp.status, detail);
      return null;
    }
    const body = (await resp.json()) as { id_token?: string };
    if (!body.id_token) return null;

    cache.set(targetAudience, {
      token: body.id_token,
      expiresAt: Date.now() + TOKEN_TTL_S * 1000,
    });
    return body.id_token;
  } catch (err) {
    console.error("gcp-auth.mint_failed", err);
    return null;
  }
}

/**
 * Build the Authorization header to send to the Cloud Run worker.
 *
 * Order of preference:
 *   1. GCP identity token (preferred — what `--no-allow-unauthenticated`
 *      validates against).
 *   2. Legacy bearer secret (used during the rollout window before the
 *      worker flips, and as a permanent fallback if SA key isn't set).
 *
 * Returns an empty object when neither is configured so the upstream
 * `fetch` call still goes through and the worker responds with a clear
 * 401 instead of a Vercel-side throw.
 */
export async function buildWorkerAuthHeader(
  workerBaseUrl: string,
): Promise<Record<string, string>> {
  const idToken = await getIdentityToken(workerBaseUrl);
  if (idToken) return { authorization: `Bearer ${idToken}` };
  const secret = process.env.WORKER_WEBHOOK_SECRET;
  if (secret) return { authorization: `Bearer ${secret}` };
  return {};
}

/**
 * Strip any `/jobs/<name>` or trailing slash to recover the base
 * Cloud Run service URL. That base is what `target_audience` expects
 * for the identity-token claim — appending the job path breaks the
 * audience match.
 */
export function workerBaseUrl(): string | null {
  const raw = process.env.WORKER_WEBHOOK_URL;
  if (!raw) return null;
  return raw.replace(/\/jobs\/[^/]+\/?$/, "").replace(/\/$/, "");
}
