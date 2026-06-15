-- 009_llm_call_log_cost_namespace.sql (2026-06-15, PR8)
--
-- Phase D carry-over from Plan §5. The 2026-06-14 baseline cut off at
-- replay 9/13 because the harness's $6.90 spend + same-day ingest_daily
-- $3+ tripped the prod LLM_MAX_DAILY_COST_USD=10 cap. The two should not
-- share a budget — the live system serves users while the baseline is
-- a deliberate one-off evaluation run.
--
-- This migration adds an optional `cost_namespace` column. When NULL,
-- behavior is identical to before (every call counts against the global
-- cap). When set (e.g. 'backtest_baseline'), `check_daily_budget` will
-- exclude those rows from the sum — the baseline keeps its own
-- accounting (`--max-cost`) while leaving the prod cap unaffected.
--
-- Lightweight: a single TEXT column + one partial index on the rows
-- check_daily_budget cares about (namespace IS NULL).

ALTER TABLE llm_call_log
    ADD COLUMN IF NOT EXISTS cost_namespace TEXT;

COMMENT ON COLUMN llm_call_log.cost_namespace IS
    'Optional bucket for excluding rows from check_daily_budget. '
    'NULL = counted against LLM_MAX_DAILY_COST_USD (default). '
    'Non-NULL (e.g. ''backtest_baseline'') = isolated from the global cap.';

-- Speeds up the cap-check query: filters by ts >= CURRENT_DATE AND
-- cost_namespace IS NULL, then sums cost_usd. Partial index keeps the
-- index small (only rows that hit the cap path).
CREATE INDEX IF NOT EXISTS llm_call_log_global_cap_idx
    ON llm_call_log (ts DESC)
    WHERE cost_namespace IS NULL;
