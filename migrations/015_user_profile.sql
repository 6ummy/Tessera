-- 015_user_profile.sql (2026-06-16) — Phase D: public profiles + leaderboard.
--
-- Adds a display nickname and a public/private flag to users. When public
-- (default), the user appears on the dashboard "Investors" leaderboard by
-- NICKNAME (never email or Google display_name) with their since-follow
-- return. Private hides them from the public board.
--
-- Additive (users exists from 001). nickname stays NULL until the user sets
-- one — the public leaderboard shows "Anonymous" for public users without a
-- nickname (real names are never exposed).

ALTER TABLE users ADD COLUMN IF NOT EXISTS nickname  TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_public BOOLEAN NOT NULL DEFAULT true;

-- Partial index for the public-leaderboard scan.
CREATE INDEX IF NOT EXISTS idx_users_public ON users (is_public) WHERE is_public;

COMMENT ON COLUMN users.nickname IS
    'User-chosen public handle for the leaderboard. NULL → shown as Anonymous.';
COMMENT ON COLUMN users.is_public IS
    'Default true. When false the user is hidden from the public leaderboard.';
