-- 007: `hypothetical` flag on the paper-track tables.
--
-- Why: the landing-page performance chart needs ~1 year of history, but
-- the real paper track only started 2026-06-11. Decision (2026-06-12,
-- see docs/improvement-plan-2026-06-11.md Step 3): backfill a
-- frozen-book history — "the persona's CURRENT holdings, held unchanged
-- for the past year" — which is cheap and deterministic but carries
-- look-ahead bias (the book was chosen with 2026 knowledge), so those
-- rows MUST be distinguishable from real ones everywhere they're read.
-- This flag is that label: the API exposes it and the UI must render
-- hypothetical segments as such ("Hypothetical — current book held 1y").
--
-- Real rows keep DEFAULT false; the engine's inserts don't name the
-- column. jobs/backfill_paper_history.py writes hypothetical = true and
-- its upserts are guarded so they can never overwrite a real row.
--
-- Idempotent.

ALTER TABLE persona_portfolios
    ADD COLUMN IF NOT EXISTS hypothetical BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE persona_performance
    ADD COLUMN IF NOT EXISTS hypothetical BOOLEAN NOT NULL DEFAULT false;
