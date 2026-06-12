# Tessera migrations

Plain SQL files. Tool-agnostic — work with `psql`, drizzle-kit raw mode, or
any client. Numbered in apply order.

## Apply

```bash
# Local (running Postgres + Timescale + pgvector locally)
psql "$DATABASE_URL" -f migrations/001_init.sql

# Neon (free tier already has Timescale + pgvector available)
psql "postgresql://USER:PASS@HOST.neon.tech/tessera?sslmode=require" \
     -f migrations/001_init.sql
```

## Conventions

- File name: `NNN_short_description.sql`, three-digit zero-padded.
- Idempotent: every `CREATE TABLE` uses `IF NOT EXISTS`; `create_hypertable`
  uses `if_not_exists => TRUE`.
- One concept per migration. Don't bundle unrelated changes.
- Never edit a migration after it's applied to any environment. Add a new one.

## Current files

| # | What it adds |
|---|---|
| 001 | Initial schema: market data (ohlcv, fundamentals, filings, macro, news), pre-computed features, analyst reports + memory, paper ledger, user layer, llm_call_log |
| 002 | `persona_memory.embedding vector(1024)` for Voyage/pgvector recall |
| 003 | `backtest_reports` table for point-in-time LLM replay runs |
| 004 | Quality/growth feature columns on `ticker_features`: `peg`, `eps_cagr_3y`, `debt_to_equity`, `gross_margin`, `gross_margin_trend`, plus `market_cap_usd` and `operating_margin` support fields |
| 005 | `pe_trailing` + `pe_forward` columns on `ticker_features` |
| 006 | Canonical one-row-per-calendar-day cleanup of `ohlcv_1d` (Alpaca 04:00Z vs Yahoo-backfill 00:00Z duplicates) + orphaned `ticker_features` rows. **Run `ingest_daily --only features coverage` + SPY canary after applying.** |
| 007 | `hypothetical` flag on `persona_portfolios` + `persona_performance` — labels the frozen-book 1y backfill (look-ahead bias) apart from the real paper track. Run before `jobs/backfill_paper_history.py`. |
