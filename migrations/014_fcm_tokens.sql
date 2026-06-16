-- 014_fcm_tokens.sql (2026-06-16) — Phase D: FCM device tokens for push.
--
-- One row per (browser/device) push registration. The web app registers a
-- token on "Enable notifications"; the worker reads them to push a rebalance
-- alert to everyone following the persona that just published a new book.
--
-- token is the PK (FCM registration tokens are globally unique). A device
-- re-registering refreshes its user_id + last_seen_at. ON DELETE CASCADE so
-- tokens vanish with the user.

CREATE TABLE IF NOT EXISTS fcm_tokens (
    token        TEXT PRIMARY KEY,
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fcm_tokens_user ON fcm_tokens (user_id);

COMMENT ON TABLE fcm_tokens IS
    'FCM web-push registration tokens (Phase D). token is unique per device; '
    'worker joins user_portfolios → users → fcm_tokens to notify a persona''s '
    'followers on rebalance.';
