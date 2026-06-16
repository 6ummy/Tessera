-- 013_follow_events.sql (2026-06-16) — Phase D: follow/unfollow audit log.
--
-- `user_portfolios` holds only CURRENT state (your active follows), so when
-- you unfollow, the row is deleted and the history is lost. The dashboard
-- account curve needs to know WHEN you followed / unfollowed each persona to
-- reconstruct the right trajectory — flat (cash) before a follow and after
-- an unfollow, tracking the persona in between. This append-only log is that
-- history.
--
-- One row per state-change event. /api/follow writes 'follow' on a new
-- follow and 'unfollow' on a drop (only when the portfolio row actually
-- changed, so a no-op re-follow doesn't double-log).

CREATE TABLE IF NOT EXISTS follow_events (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    persona_id  TEXT NOT NULL,
    action      TEXT NOT NULL CHECK (action IN ('follow', 'unfollow')),
    ts          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_follow_events_user_ts ON follow_events (user_id, ts);

COMMENT ON TABLE follow_events IS
    'Append-only follow/unfollow audit (Phase D). Source for reconstructing '
    'a user account curve across follow periods; user_portfolios holds only '
    'current state.';
