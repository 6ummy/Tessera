"""Data ingestors. Each module pulls from one upstream source into Neon.

Modules planned for Phase A:
- alpaca:   EOD OHLCV for ~500 US equities + ETFs
- coinbase: EOD candles for major crypto (BTC, ETH, SOL, AVAX, LINK)
- fmp:      Quarterly fundamentals (income, balance, cash flow)
- edgar:    SEC 10-K / 10-Q / 8-K filings (headers + GCS blob for body)
- fred:     Macro series (yields, CPI, employment, breakevens)
- news:     NewsAPI + Reddit + embedding for vector recall

Contract: each ingestor exposes `run(session, asof: date) -> IngestResult`.
Idempotent: rerunning the same date should not duplicate rows.
"""
