-- Tessera schema v1
-- Run order: extensions → market data → derived features → agent outputs → ledger
-- Idempotent. Safe to re-run; uses CREATE TABLE IF NOT EXISTS and create_hypertable on conflict.
--
-- Apply with:
--     psql "$DATABASE_URL" -f migrations/001_init.sql

-- ──────────────────────────────────────────────────────────────────────────
-- 0. Extensions
-- ──────────────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS vector;       -- pgvector
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ──────────────────────────────────────────────────────────────────────────
-- 1. Market data (Phase A) — raw rows, never touched by LLM
-- ──────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ohlcv_1d (
    ticker      TEXT        NOT NULL,
    ts          TIMESTAMPTZ NOT NULL,
    open        NUMERIC(18, 6),
    high        NUMERIC(18, 6),
    low         NUMERIC(18, 6),
    close       NUMERIC(18, 6),
    volume      BIGINT,
    vwap        NUMERIC(18, 6),
    source      TEXT        NOT NULL,        -- 'alpaca' | 'coinbase'
    PRIMARY KEY (ticker, ts)
);

SELECT create_hypertable('ohlcv_1d', 'ts', if_not_exists => TRUE, migrate_data => TRUE);

CREATE INDEX IF NOT EXISTS ohlcv_1d_ticker_idx ON ohlcv_1d (ticker, ts DESC);

-- Quarterly fundamentals from FMP (one row per filing, jsonb body)
CREATE TABLE IF NOT EXISTS fundamentals (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ticker          TEXT        NOT NULL,
    period_end      DATE        NOT NULL,
    filing_type     TEXT        NOT NULL,    -- 'income' | 'balance' | 'cash_flow'
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload         JSONB       NOT NULL,
    UNIQUE (ticker, period_end, filing_type)
);

CREATE INDEX IF NOT EXISTS fundamentals_ticker_period_idx ON fundamentals (ticker, period_end DESC);

-- SEC filings: headers in Postgres, body blob in GCS
CREATE TABLE IF NOT EXISTS filings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ticker          TEXT        NOT NULL,
    filing_type     TEXT        NOT NULL,    -- '10-K' | '10-Q' | '8-K'
    filing_date     DATE        NOT NULL,
    period_end      DATE,
    accession       TEXT        NOT NULL UNIQUE,
    raw_gcs_uri     TEXT        NOT NULL,    -- gs://bucket/edgar/<accession>.html
    text_summary    TEXT,                     -- short excerpt for LLM context (Phase B)
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS filings_ticker_date_idx ON filings (ticker, filing_date DESC);

-- Macro time series from FRED
CREATE TABLE IF NOT EXISTS macro_series (
    series_id   TEXT        NOT NULL,        -- e.g. 'DGS10', 'CPIAUCSL'
    ts          DATE        NOT NULL,
    value       NUMERIC(18, 6),
    PRIMARY KEY (series_id, ts)
);

CREATE INDEX IF NOT EXISTS macro_series_id_idx ON macro_series (series_id, ts DESC);

-- News + Reddit + embeddings for vector recall
CREATE TABLE IF NOT EXISTS news (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ts          TIMESTAMPTZ NOT NULL,
    source      TEXT        NOT NULL,         -- 'newsapi' | 'reddit'
    url         TEXT,
    title       TEXT        NOT NULL,
    body        TEXT,
    tickers     TEXT[]      NOT NULL DEFAULT '{}',
    sentiment   NUMERIC(4, 3),                -- -1.0 .. 1.0
    embedding   VECTOR(1536),
    raw_gcs_uri TEXT,                         -- original HTML / API payload
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS news_ts_idx ON news (ts DESC);
CREATE INDEX IF NOT EXISTS news_tickers_idx ON news USING GIN (tickers);
CREATE INDEX IF NOT EXISTS news_embedding_idx ON news USING ivfflat (embedding vector_cosine_ops);

-- ──────────────────────────────────────────────────────────────────────────
-- 2. Pre-computed features (Phase A) — the only numbers the LLM sees
-- ──────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ticker_features (
    ticker          TEXT        NOT NULL,
    ts              TIMESTAMPTZ NOT NULL,
    -- returns
    ret_1d          NUMERIC(8, 4),
    ret_5d          NUMERIC(8, 4),
    ret_30d         NUMERIC(8, 4),
    ret_90d         NUMERIC(8, 4),
    ret_1y          NUMERIC(8, 4),
    -- volatility & momentum
    vol_30d         NUMERIC(8, 4),
    rsi_14          NUMERIC(6, 2),
    sma_20          NUMERIC(18, 6),
    sma_50          NUMERIC(18, 6),
    volume_z        NUMERIC(6, 2),
    -- valuation (derived from fundamentals)
    pe_fwd          NUMERIC(8, 2),
    peg             NUMERIC(6, 2),
    fcf_yield       NUMERIC(6, 4),
    ev_ebitda       NUMERIC(8, 2),
    -- size / quality
    market_cap_usd  BIGINT,
    operating_margin NUMERIC(6, 4),
    eps_cagr_3y     NUMERIC(6, 4),
    -- sentiment & news
    news_sentiment_7d NUMERIC(4, 3),
    news_count_7d   INT,
    PRIMARY KEY (ticker, ts)
);

CREATE INDEX IF NOT EXISTS ticker_features_ts_idx ON ticker_features (ts DESC);

-- ──────────────────────────────────────────────────────────────────────────
-- 3. Agent outputs (Phase B) — what each persona produced
-- ──────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS analyst_reports (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    persona_id      TEXT        NOT NULL,    -- 'warren' | 'cathie' | 'ray' | 'peter'
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    as_of_date      DATE        NOT NULL,
    inputs_hash     TEXT        NOT NULL,    -- SHA256 of feature snapshot fed to LLM
    inputs_uri      TEXT,                     -- gs://… for full input replay
    raw_response    TEXT,                     -- LLM raw output for audit
    parsed          JSONB       NOT NULL,    -- Pydantic-validated AnalystReport
    model           TEXT        NOT NULL,
    tokens_in       INT,
    tokens_out      INT,
    cost_usd        NUMERIC(8, 4),
    rejected        BOOLEAN     NOT NULL DEFAULT FALSE,
    reject_reasons  TEXT[]
);

CREATE INDEX IF NOT EXISTS analyst_reports_persona_date_idx
    ON analyst_reports (persona_id, as_of_date DESC);
CREATE INDEX IF NOT EXISTS analyst_reports_inputs_hash_idx
    ON analyst_reports (inputs_hash);

-- Persona memory recall: prior thesis snippets + embeddings
CREATE TABLE IF NOT EXISTS persona_memory (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    persona_id  TEXT        NOT NULL,
    ticker      TEXT        NOT NULL,
    ts          TIMESTAMPTZ NOT NULL,
    thesis_md   TEXT        NOT NULL,
    embedding   VECTOR(1536) NOT NULL,
    report_id   UUID REFERENCES analyst_reports(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS persona_memory_persona_ticker_idx
    ON persona_memory (persona_id, ticker, ts DESC);
CREATE INDEX IF NOT EXISTS persona_memory_embedding_idx
    ON persona_memory USING ivfflat (embedding vector_cosine_ops);

-- ──────────────────────────────────────────────────────────────────────────
-- 4. Paper / live execution ledger (Phase C)
-- ──────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS persona_portfolios (
    persona_id   TEXT        NOT NULL,
    ts           TIMESTAMPTZ NOT NULL,
    cash         NUMERIC(18, 2) NOT NULL,
    positions    JSONB       NOT NULL DEFAULT '{}'::jsonb,
    total_value  NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (persona_id, ts)
);

CREATE INDEX IF NOT EXISTS persona_portfolios_ts_idx
    ON persona_portfolios (ts DESC);

CREATE TABLE IF NOT EXISTS persona_trades (
    id          BIGSERIAL PRIMARY KEY,
    persona_id  TEXT        NOT NULL,
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ticker      TEXT        NOT NULL,
    side        TEXT        NOT NULL,    -- 'buy' | 'sell'
    qty         NUMERIC(18, 6) NOT NULL,
    price       NUMERIC(18, 6) NOT NULL,
    report_id   UUID REFERENCES analyst_reports(id) ON DELETE SET NULL,
    rationale_md TEXT,
    mode        TEXT        NOT NULL DEFAULT 'paper'  -- 'paper' | 'live'
);

CREATE INDEX IF NOT EXISTS persona_trades_persona_ts_idx
    ON persona_trades (persona_id, ts DESC);
CREATE INDEX IF NOT EXISTS persona_trades_ticker_idx
    ON persona_trades (ticker, ts DESC);

CREATE TABLE IF NOT EXISTS persona_performance (
    persona_id   TEXT        NOT NULL,
    date         DATE        NOT NULL,
    pnl_day      NUMERIC(18, 2),
    pnl_cum      NUMERIC(18, 2),
    return_day   NUMERIC(8, 4),
    return_cum   NUMERIC(8, 4),
    sharpe_30d   NUMERIC(6, 3),
    mdd_30d      NUMERIC(6, 3),
    hit_rate     NUMERIC(5, 3),
    trades_count INT NOT NULL DEFAULT 0,
    PRIMARY KEY (persona_id, date)
);

-- ──────────────────────────────────────────────────────────────────────────
-- 5. User layer (Phase D)
-- ──────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    firebase_uid    TEXT UNIQUE NOT NULL,
    email           TEXT,
    display_name    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    preferences     JSONB       NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS user_portfolios (
    id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    persona_id         TEXT NOT NULL,
    started_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    starting_capital   NUMERIC(18, 2) NOT NULL,
    current_positions  JSONB NOT NULL DEFAULT '{}'::jsonb,
    current_cash       NUMERIC(18, 2) NOT NULL,
    total_value        NUMERIC(18, 2) NOT NULL,
    mode               TEXT NOT NULL DEFAULT 'paper',  -- 'paper' | 'live'
    UNIQUE (user_id, persona_id)
);

CREATE INDEX IF NOT EXISTS user_portfolios_user_idx
    ON user_portfolios (user_id);

-- ──────────────────────────────────────────────────────────────────────────
-- 6. Operations log (LLM cost, audit trail)
-- ──────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS llm_call_log (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    persona_id  TEXT,
    stage       TEXT,                    -- 'screen' | 'thesis' | 'chat' | 'review'
    model       TEXT NOT NULL,
    tokens_in   INT NOT NULL,
    tokens_out  INT NOT NULL,
    cached_tokens INT NOT NULL DEFAULT 0,
    cost_usd    NUMERIC(8, 4) NOT NULL,
    latency_ms  INT,
    success     BOOLEAN NOT NULL,
    error       TEXT
);

CREATE INDEX IF NOT EXISTS llm_call_log_ts_idx ON llm_call_log (ts DESC);
CREATE INDEX IF NOT EXISTS llm_call_log_persona_stage_idx ON llm_call_log (persona_id, stage, ts DESC);
