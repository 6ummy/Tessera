-- 003_backtest_reports.sql
--
-- Separate table for the backtest harness's historical replays. Keeps
-- production analyst_reports clean (UI / risk gateway / leaderboard all
-- read from analyst_reports; they must not accidentally surface a
-- replayed thesis as today's view).
--
-- Schema mirrors analyst_reports + (run_id, replay_as_of). One run_id
-- groups all reports from one invocation of the harness — easy to
-- delete or audit a full run.

CREATE TABLE IF NOT EXISTS backtest_reports (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id          UUID        NOT NULL,
    replay_as_of    DATE        NOT NULL,
    persona_id      TEXT        NOT NULL,
    as_of_date      DATE        NOT NULL,
    inputs_hash     TEXT        NOT NULL,
    raw_response    TEXT        NOT NULL,
    parsed          JSONB,
    model           TEXT        NOT NULL,
    tokens_in       INT         NOT NULL,
    tokens_out      INT         NOT NULL,
    cost_usd        NUMERIC(8, 4) NOT NULL,
    rejected        BOOLEAN     NOT NULL DEFAULT FALSE,
    reject_reasons  TEXT[]      NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS backtest_reports_run_id_idx
    ON backtest_reports (run_id);

CREATE INDEX IF NOT EXISTS backtest_reports_persona_replay_idx
    ON backtest_reports (persona_id, replay_as_of DESC);
