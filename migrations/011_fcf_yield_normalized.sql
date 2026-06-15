-- 011_fcf_yield_normalized.sql (2026-06-15, PR10)
--
-- Phase D carry-over #2 (Plan §5). Optional enhancement (not a fix): a
-- parallel fcf_yield series that smooths one-time items so personas
-- with normalized/forward mandates can cite a stable yield even when
-- trailing GAAP is whipsawed by a single-year event.
--
-- Triggering case (UNH, 2026-06-14): trailing GAAP FCF $19.67B / mcap
-- $371B = 5.30% — mathematically correct, but inflated by the 2024
-- cyber-attack recovery timing. The analyst-consensus "normalized" yield
-- is closer to 3% because they project a steady-state FCF nearer $13B.
-- See docs/case-studies.md CS-13 for the framing (not a bug, different
-- metric).
--
-- Definition: fcf_yield_normalized = (median of last 5 fiscal-year
-- annual FCFs, in USD) / mcap. Median > average so a single outlier
-- year (UNH 2024, or a one-off divestiture gain) doesn't distort.
--
-- Range matches fcf_yield: ±FCF_YIELD_SANITY_BOUND (1.0). NULL when
-- fewer than 3 annual rows are available — median of <3 points is
-- essentially the latest value with extra steps.

ALTER TABLE ticker_features
    ADD COLUMN IF NOT EXISTS fcf_yield_normalized NUMERIC(8, 4);

COMMENT ON COLUMN ticker_features.fcf_yield_normalized IS
    'Median of last 5 fiscal-year annual FCFs (USD-converted, currency '
    'envelope applied) divided by current market cap. Smooths one-time '
    'items vs the trailing-TTM fcf_yield column. NULL when fewer than '
    '3 annual rows exist or computation falls outside ±100% sanity bound.';
