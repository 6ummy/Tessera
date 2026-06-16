-- 012_users.sql (2026-06-16) — Phase D auth: extend the existing users table.
--
-- IMPORTANT: `users` (and `user_portfolios`) ALREADY EXIST in prod — they
-- were created in 001_init.sql §5 "User layer (Phase D)" as the schema
-- foundation. This migration does NOT create the table; it ADDS the two
-- columns Firebase auth needs that 001 didn't have:
--   - photo_url      — Google account avatar (users.photoURL from the IdP)
--   - last_login_at  — touched by the auth-sync upsert on each sign-in
-- plus an email lookup index and column comments.
--
-- Why not just `CREATE TABLE IF NOT EXISTS` with the full shape (as the
-- first draft of this file did): on a DB where `users` already exists,
-- CREATE ... IF NOT EXISTS no-ops the ENTIRE statement, so the new columns
-- would silently never be added — the exact "silent partial no-op" this
-- codebase treats as a bug (see docs/case-studies.md CS-16). ALTER ... ADD
-- COLUMN IF NOT EXISTS is the correct additive form and is idempotent.
--
-- The CREATE below is kept ONLY so a brand-new/empty DB (fresh clone,
-- test instance that skipped 001's user layer) still gets a complete
-- table; on prod it harmlessly no-ops and the ALTERs do the real work.

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

-- Real work on the existing prod table (created by 001 without these):
ALTER TABLE users ADD COLUMN IF NOT EXISTS photo_url     TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;

-- firebase_uid already has a UNIQUE index (the only hot lookup: verify
-- token → fetch/insert by uid). Add an email lookup index for admin/search.
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

COMMENT ON TABLE users IS
    'Authenticated humans (Phase D). One row per Firebase user; firebase_uid '
    'is the IdP key, id is our stable internal PK for downstream FKs. Base '
    'table from 001_init; photo_url + last_login_at added in 012.';
COMMENT ON COLUMN users.photo_url IS
    'Google account avatar URL (Firebase user.photoURL). Nullable.';
COMMENT ON COLUMN users.last_login_at IS
    'Updated by the auth-sync upsert on each sign-in. NULL until first login.';
COMMENT ON COLUMN users.preferences IS
    'Schemaless user prefs (notification opt-ins, followed personas, UI). '
    'Phase D is still discovering the shape — promote to columns once stable.';
