-- Phase C feature additions: trailing & forward P/E from yfinance fallback
-- + room for a future eps_cagr backfill once a historical-EPS ingestor lands.
-- Safe to run repeatedly against existing Neon branches.

ALTER TABLE ticker_features
    ADD COLUMN IF NOT EXISTS pe_trailing NUMERIC(8, 2),
    ADD COLUMN IF NOT EXISTS pe_forward  NUMERIC(8, 2);
