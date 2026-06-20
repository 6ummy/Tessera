-- 016_gross_margin_qtr_series.sql (2026-06-19)
--
-- Quarterly gross-margin TIME SERIES (backlog: "quarterly margin series
-- ingest"). `gross_margin_qtr_yoy_chg` (010) is a single YoY delta — it
-- tells you the latest quarter is up/down vs a year ago, but not the
-- TRAJECTORY. This column stores the last ~8 quarterly margins so a persona
-- can read steady expansion vs a one-quarter blip.
--
-- Shape: JSONB array, newest-first, each entry {"pe": "YYYY-MM-DD", "gm": 0.4321}
-- where gm = grossProfit/revenue for that quarter (same sanity envelope as
-- gross_margin). Quarterly cadence only (Q1-Q3; Q4 is folded into the FY
-- annual series elsewhere), so periods are labelled and may skip Q4.
-- Populated Friday-only via the fmp_quarterly ingest step. Additive — safe to
-- re-run.

ALTER TABLE ticker_features
    ADD COLUMN IF NOT EXISTS gross_margin_qtr_series JSONB;

COMMENT ON COLUMN ticker_features.gross_margin_qtr_series IS
    'Last ~8 quarterly gross margins, newest-first JSONB array of '
    '{pe, gm}. Shows the margin trajectory (vs the single YoY delta in '
    'gross_margin_qtr_yoy_chg). NULL with fewer than 2 valid quarters.';
