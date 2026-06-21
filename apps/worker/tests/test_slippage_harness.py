"""Phase F slippage harness — pure comparison, observation only."""

from __future__ import annotations

from tessera_worker.execution.slippage import Fill, slippage_report


def test_empty_when_no_live_fills() -> None:
    # The pilot state: paper fills only → nothing to compare.
    rep = slippage_report([Fill("AAPL", "buy", 1, 100.0, "paper")])
    assert rep.n_compared == 0
    assert rep.avg_cost_bps is None
    assert rep.n_unmatched == 1


def test_buy_filled_higher_is_a_positive_cost() -> None:
    rep = slippage_report([
        Fill("AAPL", "buy", 1, 100.0, "paper"),
        Fill("AAPL", "buy", 1, 100.5, "live"),  # paid 0.5% more
    ])
    assert rep.n_compared == 1
    assert rep.pairs[0].slippage_bps == 50.0  # +50 bps cost
    assert rep.avg_cost_bps == 50.0


def test_sell_filled_lower_is_a_positive_cost() -> None:
    rep = slippage_report([
        Fill("MSFT", "sell", 1, 200.0, "paper"),
        Fill("MSFT", "sell", 1, 199.0, "live"),  # received 0.5% less
    ])
    assert rep.pairs[0].slippage_bps == 50.0  # selling lower is also a cost


def test_better_than_paper_is_negative_cost() -> None:
    rep = slippage_report([
        Fill("NVDA", "buy", 1, 100.0, "paper"),
        Fill("NVDA", "buy", 1, 99.0, "live"),  # bought cheaper than paper
    ])
    assert rep.pairs[0].slippage_bps == -100.0


def test_unmatched_counted() -> None:
    rep = slippage_report([
        Fill("AAPL", "buy", 1, 100.0, "paper"),
        Fill("AAPL", "buy", 1, 100.0, "live"),
        Fill("TSLA", "buy", 1, 50.0, "live"),  # no paper counterpart
    ])
    assert rep.n_compared == 1
    assert rep.n_unmatched == 1
