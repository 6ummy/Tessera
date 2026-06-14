"""Regression: the equity OHLCV step must never hand a crypto pair to
Alpaca's stock feed.

CS-12: `_step_ohlcv_equity` passed the FULL universe (`TICKERS`, crypto
included) to `alpaca_eod.ingest`, which batches every symbol into one
`StockBarsRequest`. Alpaca rejects a crypto symbol (AVAX/USD) and fails
the WHOLE request, so equity OHLCV silently froze for ~9 days — invisible
because the Service path ignored the non-zero exit code; the Cloud Run
Job surfaced it. This pins that the step's ticker list is equity+ETF only.
"""

from __future__ import annotations

from unittest.mock import patch

from tessera_worker.jobs import ingest_daily
from tessera_worker.universe import META_BY_TICKER, by_asset_class


def test_ohlcv_equity_step_sends_no_crypto_to_alpaca() -> None:
    captured: dict[str, list[str]] = {}

    class _Result:
        rows_upserted = 0
        tickers: list[str] = []
        duration_ms = 0

    def _fake_ingest(tickers, *, start, end):  # type: ignore[no-untyped-def]
        captured["tickers"] = list(tickers)
        return _Result()

    with patch.object(ingest_daily.alpaca_eod, "ingest", _fake_ingest):
        ingest_daily._step_ohlcv_equity()

    sent = captured["tickers"]
    assert sent, "equity step sent no tickers"
    # No crypto pairs (asset_class == 'crypto') may reach Alpaca.
    crypto = {t.ticker for t in by_asset_class("crypto")}
    assert not (set(sent) & crypto), f"crypto leaked to Alpaca: {set(sent) & crypto}"
    # And every sent ticker is a real equity/ETF in the universe.
    for t in sent:
        assert META_BY_TICKER[t].asset_class in ("equity", "etf")
