"""Unit tests for prompt_assembler rendering (no DB)."""

from __future__ import annotations

from tessera_worker.agents.prompt_assembler import (
    build_user_message,
    compute_inputs_hash,
    render_features,
    render_news,
)


def test_render_features_minimal() -> None:
    block = render_features(
        {
            "ts": "2026-05-29",
            "ret_1d": 0.01,
            "ret_5d": 0.02,
            "ret_30d": 0.03,
            "ret_90d": 0.04,
            "ret_1y": 0.05,
            "vol_30d": 0.2,
            "rsi_14": 50.0,
            "sma_20": 100.0,
            "sma_50": 95.0,
            "volume_z": 0.5,
        }
    )
    assert "<features>" in block
    assert "RSI14=50" in block


def test_render_news_short_ids() -> None:
    from datetime import datetime, timezone

    block = render_news(
        [
            {
                "id": "b7a434db-1234-5678-9abc-def012345678",
                "ts": datetime(2026, 5, 31, tzinfo=timezone.utc),
                "source": "Reuters",
                "title": "Apple headline",
            }
        ]
    )
    assert "[n_b7a434db]" in block


def test_inputs_hash_stable() -> None:
    msg = "hello"
    assert compute_inputs_hash(msg) == compute_inputs_hash(msg)
    assert compute_inputs_hash("a") != compute_inputs_hash("b")


def test_build_user_message_includes_ticker() -> None:
    msg = build_user_message(
        "warren",
        "AAPL",
        {
            "features": None,
            "prices_full": [],
            "fundamentals": {},
            "fundamentals_annual": {},
            "macros": {},
            "news": [],
            "filing": None,
            "memory": "",
        },
    )
    assert "AAPL" in msg
    assert "AnalystReport" in msg
