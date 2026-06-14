-- 008_cross_source_disagreements.sql (2026-06-14, PR6)
--
-- Audit log for cross_validated() disagreements between data sources
-- (market cap candidates, debt_to_equity once it cross-validates, etc.).
-- Each row is one event: which feature, which ticker, the candidate
-- values, the spread (max/min), and which value the heuristic picked.
--
-- Grafana panel queries this table to surface systemic ones (GOOGL was
-- the canonical 2.06× spread before the dual-class override; we want to
-- see new patterns before they pollute the LLM prompt).
--
-- Lightweight: the existing `cross_validated()` warn-log already exists;
-- this table just persists the same payload so a SQL datasource can
-- aggregate it. Expected volume: < 50 rows/day across the universe at
-- steady state.

CREATE TABLE IF NOT EXISTS cross_source_disagreements (
    id         BIGSERIAL PRIMARY KEY,
    ts         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    feature    TEXT        NOT NULL,    -- e.g. 'market_cap'
    ticker     TEXT,
    spread     NUMERIC(10, 3) NOT NULL, -- max/min of candidate values
    decision   TEXT        NOT NULL,    -- 'max' | 'min' | 'first'
    candidates JSONB       NOT NULL     -- list of {label, value}
);

CREATE INDEX IF NOT EXISTS cross_source_disagreements_ts_idx
    ON cross_source_disagreements (ts DESC);
CREATE INDEX IF NOT EXISTS cross_source_disagreements_feature_ticker_idx
    ON cross_source_disagreements (feature, ticker, ts DESC);
