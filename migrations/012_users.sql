-- 012_users.sql (2026-06-16) — Phase D foundation: authenticated users.
--
-- First Phase D migration. Creates the `users` table that Firebase Auth
-- (Google SSO) maps onto: one row per signed-in human, keyed by their
-- stable Firebase UID. Nothing writes to it yet — the secure upsert
-- (a server route verifying the Firebase ID token with firebase-admin,
-- then INSERT ... ON CONFLICT) lands with the auth-sync PR. Shipping the
-- schema first so the operator can apply it ahead of the writer, the
-- same way every other column landed before its loader.
--
-- `firebase_uid` is the join key everywhere downstream:
--   - user_portfolios.user_id  → users.id           (mirror engine, next)
--   - follows.user_id          → users.id           (follow CTA, next)
-- We store id (UUID, our own PK) AND firebase_uid (the IdP's id) so a
-- future auth-provider swap only rewrites this table, not every FK.
--
-- preferences JSONB: notification opt-ins, followed personas cache, UI
-- prefs — schemaless on purpose; Phase D is still discovering its shape.

CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    firebase_uid  TEXT        NOT NULL UNIQUE,
    email         TEXT,
    display_name  TEXT,
    photo_url     TEXT,
    preferences   JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);

-- firebase_uid already has a UNIQUE index from the constraint above; that
-- covers the only hot lookup (verify token → fetch/insert by uid).
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

COMMENT ON TABLE users IS
    'Authenticated humans (Phase D). One row per Firebase user; firebase_uid '
    'is the IdP key, id is our stable internal PK for downstream FKs.';
COMMENT ON COLUMN users.preferences IS
    'Schemaless user prefs (notification opt-ins, followed personas, UI). '
    'Phase D is still discovering the shape — promote to columns once stable.';
