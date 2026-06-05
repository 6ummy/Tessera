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


# ─── pgvector recall (PR #41) ──────────────────────────────────────────


def test_fetch_memory_recall_falls_back_to_recency_when_no_query() -> None:
    """No query_text → similarity path bypassed → recency query runs."""
    from unittest.mock import MagicMock
    from tessera_worker.agents.prompt_assembler import fetch_memory_recall

    session = MagicMock()
    session.execute.return_value.all.return_value = []  # empty DB
    result = fetch_memory_recall(session, "warren", "AAPL")
    # Should have executed exactly one query (recency only), not similarity.
    assert session.execute.call_count == 1
    assert result == ""


def test_fetch_memory_recall_falls_back_when_voyage_unconfigured(monkeypatch) -> None:
    """query_text provided but VOYAGE_API_KEY blank → recency fallback."""
    from unittest.mock import MagicMock
    from tessera_worker.agents.prompt_assembler import fetch_memory_recall

    # Ensure voyage key is blank
    monkeypatch.setenv("VOYAGE_API_KEY", "")
    # Clear cached settings so blank key takes effect
    from tessera_worker.config import get_settings
    get_settings.cache_clear()

    session = MagicMock()
    session.execute.return_value.all.return_value = []
    fetch_memory_recall(session, "warren", "AAPL", query_text="earnings beat")
    # Similarity check exits early (empty list) → recency runs as fallback.
    assert session.execute.call_count == 1


def test_embed_thesis_returns_none_when_no_key(monkeypatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "")
    from tessera_worker.config import get_settings
    get_settings.cache_clear()
    from tessera_worker.agents.embeddings import embed_thesis
    assert embed_thesis("anything") is None


def test_to_pgvector_literal_format() -> None:
    from tessera_worker.agents.embeddings import to_pgvector_literal
    s = to_pgvector_literal([0.1, -0.5, 1.0])
    assert s == "[0.100000,-0.500000,1.000000]"
