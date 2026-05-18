"""Feature builders. Pure pandas/numpy — no LLM, no I/O except DB reads.

These compute the pre-validated numerical features that LLMs read.
Per the hallucination defense pattern: the LLM never computes a number;
this module is the single source of truth for every numerical input.

Planned features (`compute_features.py`):
- ret_{1d, 5d, 30d, 90d, 1y}   (total return)
- vol_{30d, 90d}               (annualized volatility)
- rsi_14, sma_20, sma_50, macd
- fcf_yield, pe_fwd, peg, ev_ebitda
- volume_z, market_cap
- regime probabilities (Ray's input — from macro_series)

Hard requirement: property-based tests (hypothesis) + canary asserts
(e.g., SPY 1y return must match Yahoo within 10 bps).
"""
