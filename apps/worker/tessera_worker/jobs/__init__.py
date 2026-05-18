"""Cloud Run Job entry points. One module per scheduled batch.

Run via:  python -m tessera_worker.jobs.<name>

Planned:
- ingest_daily.py    Pull EOD market data + news + fundamentals updates
- features_build.py  Recompute ticker_features after ingestion
- persona_batch.py   Run all personas (Haiku screen + Sonnet thesis)
- mtm_eod.py         Mark-to-market and persona_performance update
"""
