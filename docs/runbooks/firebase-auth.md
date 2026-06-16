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

## Not yet wired (next — follow + mirror engine)

- **"Follow this persona"**, `user_portfolios` writes, and the mirror
  engine (Plan §6) build on top of the verified `users.id` that
  `/api/auth/sync` now persists.
