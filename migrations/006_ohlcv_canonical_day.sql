-- 006: one canonical row per (ticker, calendar day) in ohlcv_1d.
--
-- Why: ohlcv_1d's PK is (ticker, ts) with ts TIMESTAMPTZ. The daily Alpaca
-- ingest stamps bars at 04:00:00+00 while the 2026-06-02 yfinance backfill
-- stamped 00:00:00+00 — so the same trading day coexisted as TWO rows for
-- the ~6-year window where both sources overlap (2020-07 → present).
-- Every feature in features/compute.py is a row-window computation
-- (ret_30d = 30 rows, vol_30d, rsi_14, sma_*, volume_z), so duplicated days
-- silently halved the effective horizon of every price feature the LLM
-- prompt reads. See docs/improvement-plan-2026-06-11.md P0-1.
--
-- What this does:
--   1. Deletes duplicate calendar-day rows, keeping the preferred source:
--      daily-cron feeds (alpaca, coinbase) > backfill (yahoo) > anything else.
--      Ties (same rank, same day) keep the later ts.
--   2. Deletes ticker_features rows orphaned by step 1 (rows keyed at a ts
--      that no longer exists in ohlcv_1d). Price features are only ever
--      written at ohlcv ts values, so this touches exactly the stale
--      duplicate-day rows.
--
-- What this does NOT do: add a (ticker, ts::date) UNIQUE index. TimescaleDB
-- requires unique indexes on a hypertable to include the raw partitioning
-- column, and an expression index on ts does not qualify. Recurrence is
-- instead prevented in code:
--   - jobs/backfill_history.py::backfill_yahoo skips days already covered
--     by a non-yahoo source,
--   - features/compute.py::_load_ohlcv and main.py::/api/prices dedup with
--     DISTINCT ON (ticker, ts::date) as defense in depth.
--
-- AFTER APPLYING, the operator must rebuild features and re-verify:
--   python -m tessera_worker.jobs.ingest_daily --only features coverage
--   python -m scripts.ingest_spy_canary
-- (step 2 deletes the latest ticker_features row for affected tickers, which
-- also carries the fundamentals-derived quality columns — the rebuild's
-- fundamentals pass repopulates them in the same run.)
--
-- Idempotent: re-running finds no duplicates / no orphans and deletes 0 rows.

-- 1. Deduplicate ohlcv_1d per (ticker, calendar day).
DELETE FROM ohlcv_1d a
USING ohlcv_1d b
WHERE a.ticker = b.ticker
  AND a.ts::date = b.ts::date
  AND a.ts IS DISTINCT FROM b.ts
  AND (
        (CASE a.source WHEN 'alpaca' THEN 1 WHEN 'coinbase' THEN 1 WHEN 'yahoo' THEN 2 ELSE 3 END)
      > (CASE b.source WHEN 'alpaca' THEN 1 WHEN 'coinbase' THEN 1 WHEN 'yahoo' THEN 2 ELSE 3 END)
     OR (
        (CASE a.source WHEN 'alpaca' THEN 1 WHEN 'coinbase' THEN 1 WHEN 'yahoo' THEN 2 ELSE 3 END)
      = (CASE b.source WHEN 'alpaca' THEN 1 WHEN 'coinbase' THEN 1 WHEN 'yahoo' THEN 2 ELSE 3 END)
        AND a.ts < b.ts
     )
  );

-- 2. Remove ticker_features rows now orphaned (their ts was a duplicate-day
--    row deleted above). The next features build recreates every row at the
--    canonical ts with correct windows.
DELETE FROM ticker_features f
WHERE NOT EXISTS (
    SELECT 1 FROM ohlcv_1d o
    WHERE o.ticker = f.ticker AND o.ts = f.ts
);
