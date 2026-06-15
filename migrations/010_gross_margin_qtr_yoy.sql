-- 010_gross_margin_qtr_yoy.sql (2026-06-15, PR9)
--
-- Phase D carry-over #3 (Plan §5). Quarterly margin signal for personas
-- that care about momentum (Peter / Cathie). Existing `gross_margin` is
-- a static level off the latest FY annual; `gross_margin_trend` is
-- 3y-ago annual delta. Neither captures recent quarters.
--
-- New column: gross_margin_qtr_yoy_chg = latest_quarter_margin minus
-- same_quarter_prior_year_margin. Strips seasonality (compare Q2 to Q2,
-- not Q2 to Q1) and surfaces accelerations / decelerations that an
-- annual-only series misses by 6-12 months.
--
-- Range: roughly -1.0 to +1.0; populated only when both quarter rows
-- exist (NULL otherwise — sanity-bounded by the same margin envelope
-- as gross_margin itself).

ALTER TABLE ticker_features
    ADD COLUMN IF NOT EXISTS gross_margin_qtr_yoy_chg NUMERIC(6, 4);

COMMENT ON COLUMN ticker_features.gross_margin_qtr_yoy_chg IS
    'Latest quarterly gross margin minus the same quarter of the prior '
    'fiscal year. Captures margin momentum YoY; NULL if either quarter '
    'is missing or computation falls outside the standard margin '
    'sanity bound (±100%).';
