-- 017_broker_connections.sql (2026-06-19) — Phase F scaffolding.
--
-- Structure for a user linking a real brokerage (Alpaca) via OAuth. The table
-- exists so the connect/callback flow + token storage have a home BEFORE any
-- live-trading code; it is NOT used in the pilot (live trading is OFF-gated —
-- see tessera_worker/execution/broker.py + FEATURE_LIVE_TRADING). No rows are
-- written until Phase E clears live trading.
--
-- Tokens are stored ENCRYPTED (app-layer) — never plaintext. status tracks the
-- connection lifecycle; one active connection per (user, provider).

CREATE TABLE IF NOT EXISTS broker_connections (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider      TEXT NOT NULL DEFAULT 'alpaca',
    status        TEXT NOT NULL DEFAULT 'disconnected'
                  CHECK (status IN ('disconnected', 'pending', 'connected', 'revoked')),
    -- App-layer-encrypted tokens. NULL until a real (post-Phase-E) connect.
    access_token_enc   TEXT,
    refresh_token_enc  TEXT,
    account_label      TEXT,            -- e.g. masked Alpaca account id
    connected_at  TIMESTAMPTZ,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_broker_conn_user_provider
    ON broker_connections (user_id, provider);

COMMENT ON TABLE broker_connections IS
    'Phase F scaffolding: a user''s linked brokerage (Alpaca OAuth). Unused in '
    'the pilot — live trading is OFF-gated; no rows until Phase E clears it. '
    'Tokens are app-layer-encrypted, never plaintext.';
