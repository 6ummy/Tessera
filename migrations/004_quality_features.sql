-- Phase C quality / growth features.
-- Safe to run repeatedly against existing Neon branches.

ALTER TABLE ticker_features
    ADD COLUMN IF NOT EXISTS peg NUMERIC(6, 2),
    ADD COLUMN IF NOT EXISTS market_cap_usd BIGINT,
    ADD COLUMN IF NOT EXISTS operating_margin NUMERIC(6, 4),
    ADD COLUMN IF NOT EXISTS eps_cagr_3y NUMERIC(6, 4),
    ADD COLUMN IF NOT EXISTS debt_to_equity NUMERIC(8, 4),
    ADD COLUMN IF NOT EXISTS gross_margin NUMERIC(6, 4),
    ADD COLUMN IF NOT EXISTS gross_margin_trend NUMERIC(6, 4);
