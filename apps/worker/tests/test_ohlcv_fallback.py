"""Trading-days-behind gate for the ohlcv Yahoo fallback (pure, no DB/network)."""

from __future__ import annotations

from datetime import date

from tessera_worker.jobs.ingest_daily import _trading_days_behind


def test_none_is_very_stale() -> None:
    assert _trading_days_behind(None, date(2026, 6, 23)) == 999


def test_fresh_yesterday_not_stale() -> None:
    # Mon freshest, Tue today → 1 weekday behind (feed lag), not a gap.
    assert _trading_days_behind(date(2026, 6, 22), date(2026, 6, 23)) == 1


def test_weekend_does_not_count() -> None:
    # Fri (Jun 19) freshest, Mon (Jun 22) today → only Mon counts → 1.
    assert _trading_days_behind(date(2026, 6, 19), date(2026, 6, 22)) == 1


def test_real_gap_trips_the_gate() -> None:
    # The 2026-06-18 freeze: freshest Jun 18, today Jun 23 → Fri/Mon/Tue = 3 ≥ 2.
    assert _trading_days_behind(date(2026, 6, 18), date(2026, 6, 23)) == 3
