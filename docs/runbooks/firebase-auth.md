# Runbook — Firebase Auth (Google SSO) setup

Operator console steps to turn on sign-in. The repo side is scaffolded
(client SDK, auth context, header wiring, `users` migration); this is the
~15 min of Firebase + Vercel console work only the operator can do.

Until these env vars are set, the app runs the **pre-auth pilot
experience** — no sign-in button, the account chip shows the "jshin"
pilot identity. Setting them flips on real Google SSO with no code change.

---

## 1. Create the Firebase project (~5 min)

1. https://console.firebase.google.com → **Add project** (e.g. `tessera`).
   Google Analytics optional — skip for the pilot.
2. **Build → Authentication → Get started → Sign-in method →
   Google → Enable.** Set the support email. Save.
3. **Project settings (gear) → General → Your apps → Web (`</>`)**:
   register an app (nickname `tessera-web`). Copy the `firebaseConfig`
   values — you need `apiKey`, `authDomain`, `projectId`, `appId`.
4. **Authentication → Settings → Authorized domains**: add
   `tessera-ruby.vercel.app` (and any custom domain). `localhost` is
   present by default for local dev.

## 2. Apply migration 012 (Neon SQL editor)

Run `migrations/012_users.sql` in the Neon console. NOTE: `users` (and
`user_portfolios`) already exist in prod — they shipped in `001_init.sql`.
012 is purely ADDITIVE: it `ALTER ... ADD COLUMN IF NOT EXISTS`s the two
columns Firebase needs (`photo_url`, `last_login_at`) plus an email index
and comments. It's idempotent — safe to run once or re-run. Nothing
writes to the table yet; the secure upsert lands with the auth-sync PR.

Verify after applying (or ask Claude to run a read-only check):
```sql
SELECT column_name FROM information_schema.columns
WHERE table_name='users' ORDER BY ordinal_position;
-- expect photo_url + last_login_at present
```

## 3. Set the env vars

**Local** (`apps/web/.env.local`) and **Vercel** (Project → Settings →
Environment Variables, all environments) — from step 1.3:

```
NEXT_PUBLIC_FIREBASE_API_KEY=...
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=tessera.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=tessera
NEXT_PUBLIC_FIREBASE_APP_ID=1:...:web:...
```

The four above are PUBLIC values (they ship in the browser bundle by
design — `NEXT_PUBLIC_` prefix). Firebase web security comes from the
Auth provider config + authorized domains, NOT from hiding the key.

**Also add `DATABASE_URL`** (server-only, NO `NEXT_PUBLIC_` prefix) — the
same Neon connection string the worker uses. The `/api/auth/sync` route
needs it to upsert the `users` row on login:

```
DATABASE_URL=postgresql://...neon.tech/neondb?sslmode=require
```

No firebase-admin / service-account secret is required: the route
verifies ID tokens with `jose` against Google's public JWKS, using only
the public project id. Redeploy Vercel after setting the vars (env
changes need a fresh build).

## 4. Verify

- Visit the site: the header now shows a **Sign in** button.
- Click it → Google popup → pick an account → the chip shows your name
  + photo, and the account menu gains **Sign out**.
- Sign out returns to the Sign in button.
- **Sign-in now upserts a `users` row** (via `/api/auth/sync`). Verify in
  Neon: `SELECT firebase_uid, email, last_login_at FROM users;` — your
  account should appear, `last_login_at` refreshed on each sign-in.

If you still see the "jshin" pilot chip, the four `NEXT_PUBLIC_FIREBASE_*`
vars aren't taking — confirm they're set in the right Vercel environment
and the deploy is fresh. If sign-in works but `users` stays empty, check
`DATABASE_URL` is set on Vercel and look for `auth_sync.*` errors in the
Vercel function logs.

---

## 5. FCM push (optional — rebalance notifications)

Ships dark: with no VAPID key the "Enable notifications" toggle stays
hidden and the worker logs "would notify N" without sending.

### 5-1. Web Push certificate (VAPID key)
Firebase Console → ⚙️ Project settings → **Cloud Messaging → Web Push
certificates → Generate key pair**. Set on Vercel (public values):
```
NEXT_PUBLIC_FIREBASE_VAPID_KEY=<the generated key>
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=987211534763   # from firebaseConfig
```
Redeploy. The account menu now shows **Enable notifications** for
signed-in users; clicking it requests permission + registers the device
token (`fcm_tokens`).

### 5-2. Let the worker SEND (keyless cross-project IAM)
The worker (project `tessera-498200`) sends FCM v1 to the Firebase
project `tessera-641a5`. Grant its SA the messaging role on that project
— no key file:
```bash
gcloud projects add-iam-policy-binding tessera-641a5 \
  --member="serviceAccount:tessera-worker@tessera-498200.iam.gserviceaccount.com" \
  --role="roles/firebasecloudmessaging.admin"
```
Then flip the worker flag and redeploy:
```
FEATURE_FCM_PUSH=true   # apps/worker env (deploy scripts)
```
The worker mints its OAuth token from the Cloud Run metadata server
(cloud-platform scope) — no service-account secret to store/rotate.

### 5-3. Apply migration 014
`migrations/014_fcm_tokens.sql` in the Neon console.

### Verify
Enable notifications in the browser → `SELECT * FROM fcm_tokens;` shows
your token. On the next Friday persona batch (or a manual run), followers
get a "X rebalanced" push; worker logs `fcm.notified` (or `fcm.would_notify`
when the flag is off).

---

## 6. Email notifications — the SOLE notify channel (LIVE)

**FCM web push was dropped (2026-06-18) — email is the only channel.**
(The §5 FCM scaffolding stays in the tree, unused; leave `FEATURE_FCM_PUSH`
off.) Email is LIVE: `RESEND_API_KEY` + `FEATURE_EMAIL_NOTIFY=true` are set,
the worker is redeployed. Two senders use Resend:
- **Web** (`apps/web/lib/email.ts`, Edge) — the *confirmation* email when a
  user enables "Email alerts". Reads `process.env.RESEND_API_KEY` /
  `EMAIL_FROM` on **Vercel**.
- **Worker** (`notify/email.py`) — the *rebalance* email to followers on the
  Friday batch. Reads `RESEND_API_KEY` / `EMAIL_FROM` on **Cloud Run**.

Both emails carry a one-click unsubscribe link (HMAC over the user id,
shared `UNSUBSCRIBE_SECRET` on Vercel **and** Cloud Run; verified by the web
`/api/unsubscribe`).

### 6-1. Remaining task — verified-domain sender (so email reaches F&F)
The default `onboarding@resend.dev` (Resend sandbox) **only delivers to the
Resend account-owner's email** — fine for the operator's self-test, but it
will NOT reach other F&F users. To deliver to anyone:

1. **Resend → Domains → Add domain** (e.g. `tessera.app` or a subdomain you
   own). Add the **DNS records Resend shows** (SPF/DKIM TXT + MX) at your
   registrar; wait for Resend to mark it **Verified**.
2. Pick a from-address on that domain, e.g. `Tessera <alerts@tessera.app>`.
3. Set `EMAIL_FROM` to it in **all three** places (they must match):
   - **Vercel** env (Production) → `EMAIL_FROM = Tessera <alerts@tessera.app>`
     (redeploy / it applies on next deploy).
   - **`deploy_cloud_run.ps1`** + **`deploy_cloud_run_jobs.ps1`** → edit the
     `$EMAIL_FROM` variable near the top, then redeploy the worker. (It's
     kept in-script because `--set-env-vars` replaces the whole env on each
     deploy — a console-only value would be wiped on the next redeploy.)
4. Send yourself a test (enable "Email alerts" → confirmation email; toggle
   shows "✓ Email sent to …").

### Verify
- Enabling alerts → confirmation email arrives; the toggle reports the real
  send result. Web log: `preferences.welcome_email sent=true`.
- On the Friday batch (or a manual `persona-batch` run), followers with a
  `users.email` get a "X rebalanced" email; worker logs `email.notified`
  (or `email.would_email` when the flag/key is off).

---

## Done (no longer pending)

Auth + `/api/follow` + mirror engine + dashboard + account curve + public
profiles/leaderboard + email notify (confirmation + rebalance + one-click
unsubscribe) are all LIVE. **FCM dropped.** Remaining Phase D: onboard F&F
users + (optional) the verified-domain `EMAIL_FROM` above.
