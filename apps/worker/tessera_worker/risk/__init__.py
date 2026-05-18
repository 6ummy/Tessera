"""Risk gateway and paper execution adapter (Phase C).

Deterministic Python only. No LLM calls. This is the leash that prevents the
LLM from causing harm.

Planned (Phase C):
- gateway.py    validate(portfolio, persona) -> Result; checks ticker exists,
                weight caps, sector concentration, parametric VaR, DD floor
- adapter.py    ExecutionAdapter Protocol + PaperEngine + AlpacaLiveAdapter
                (live behind `feature.live_trading` flag, never default)
- mtm.py        EOD mark-to-market job: recompute persona_portfolios.total_value
- attribution.py  Ticker-level contribution to MTD return per persona
"""
