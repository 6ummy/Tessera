"""Risk gateway and paper execution adapter (Phase C).

Deterministic Python only. No LLM calls. This is the leash that prevents the
LLM from causing harm.

- gateway.py    ✅ shipped 2026-06-11 — gate(report) -> RiskCheckResult.
                Universe membership, sum=1.0, single-name + sector caps.
                Wired into construct_portfolio's retry loop, so a rejection
                becomes specific feedback to the construction LLM.
                Parametric VaR + drawdown floor join once the paper engine
                provides live positions.

Planned (Phase C):
- adapter.py    ExecutionAdapter Protocol + PaperEngine + AlpacaLiveAdapter
                (live behind `feature.live_trading` flag, never default)
- mtm.py        EOD mark-to-market job: recompute persona_portfolios.total_value
- attribution.py  Ticker-level contribution to MTD return per persona
"""
