"""Unit tests for prompt_assembler rendering (no DB)."""

from __future__ import annotations

from datetime import UTC

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
    from datetime import datetime

    block = render_news(
        [
            {
                "id": "b7a434db-1234-5678-9abc-def012345678",
                "ts": datetime(2026, 5, 31, tzinfo=UTC),
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


# ─── Backtest leakage tests (Phase B Week 3) ───────────────────────────
# Verifies that fetch_inputs(as_of=X) cannot leak data with ts > X into
# the LLM prompt. We capture every SQL parameter dict the function emits
# and assert the cutoff is present (or that the query has no temporal
# field). Cheaper and tighter than a real-DB integration check.


def test_fetch_inputs_passes_cutoff_to_every_query() -> None:
    """Every SQL the assembler runs against time-series tables must carry
    the cutoff. Missing it = backtest replay sees future data = leakage."""
    import datetime as _dt
    from unittest.mock import MagicMock

    from tessera_worker.agents.prompt_assembler import fetch_inputs

    cutoff = _dt.date(2025, 6, 1)
    session = MagicMock()
    # Default chain returns empty so the function completes; we don't care
    # about return values, only that calls carry cutoff.
    session.execute.return_value.mappings.return_value.first.return_value = None
    session.execute.return_value.mappings.return_value.all.return_value = []
    session.execute.return_value.all.return_value = []

    fetch_inputs(session, "warren", "AAPL", as_of=cutoff)  # type: ignore[arg-type]

    queries_with_temporal_bind = 0
    for call in session.execute.call_args_list:
        params = call.args[1] if len(call.args) > 1 else {}
        if not isinstance(params, dict):
            continue
        # Any param key that's a date carries the cutoff (or a derived
        # since-window). Walk the values.
        date_values = [v for v in params.values() if isinstance(v, _dt.date)]
        if date_values:
            queries_with_temporal_bind += 1
            # The latest date in this query must be ≤ cutoff (since-window
            # may be older, but cutoff itself can never be exceeded).
            assert max(date_values) <= cutoff, (
                f"leakage: query bound to date > cutoff {cutoff}, "
                f"params={params}"
            )

    # Sanity: features + prices + fundamentals (×2 paths × 3 filing types) +
    # macros + news + filings + memory = at least 5 queries should bind
    # cutoff. If this drops to 0, fetch_inputs lost its temporal guards.
    assert queries_with_temporal_bind >= 5, (
        f"only {queries_with_temporal_bind} queries carried cutoff — "
        "fetch_inputs lost some point-in-time guards"
    )


def test_fetch_inputs_with_no_as_of_uses_today() -> None:
    """No as_of → cutoff = today. Production prod path (live cron) doesn't
    pass as_of explicitly; ensure it still binds something rather than
    emitting an unbounded query."""
    import datetime as _dt
    from unittest.mock import MagicMock

    from tessera_worker.agents.prompt_assembler import fetch_inputs

    today = _dt.date.today()
    session = MagicMock()
    session.execute.return_value.mappings.return_value.first.return_value = None
    session.execute.return_value.mappings.return_value.all.return_value = []
    session.execute.return_value.all.return_value = []

    fetch_inputs(session, "warren", "AAPL")  # type: ignore[arg-type]

    # At least one execute call should carry a date ≤ today.
    any_temporal = False
    for call in session.execute.call_args_list:
        params = call.args[1] if len(call.args) > 1 else {}
        if not isinstance(params, dict):
            continue
        date_values = [v for v in params.values() if isinstance(v, _dt.date)]
        if date_values:
            any_temporal = True
            assert max(date_values) <= today
    assert any_temporal, "no temporal bind found — leakage guard missing"


def test_fetch_memory_recall_recency_path_respects_cutoff() -> None:
    """The recency fallback path also has to respect cutoff. Embedding
    similarity path is harder to mock (needs Voyage); recency is the
    safety net and the one production hits when Voyage is unavailable."""
    import datetime as _dt
    from unittest.mock import MagicMock

    from tessera_worker.agents.prompt_assembler import fetch_memory_recall

    cutoff = _dt.date(2025, 6, 1)
    session = MagicMock()
    session.execute.return_value.all.return_value = []

    # No query_text → similarity bypassed → recency runs.
    fetch_memory_recall(session, "warren", "AAPL", as_of=cutoff)

    assert session.execute.call_count == 1
    params = session.execute.call_args.args[1]
    assert "cutoff" in params, (
        f"memory recall recency query didn't bind cutoff: {params}"
    )
    assert params["cutoff"] == cutoff


def test_fetch_memory_recall_no_as_of_skips_cutoff_clause() -> None:
    """When as_of is None, the cutoff clause must be omitted from SQL
    (not just bound to None — that would still filter). Verify by
    inspecting the raw SQL text emitted."""
    from unittest.mock import MagicMock

    from tessera_worker.agents.prompt_assembler import fetch_memory_recall

    session = MagicMock()
    session.execute.return_value.all.return_value = []

    fetch_memory_recall(session, "warren", "AAPL")

    sql_text = str(session.execute.call_args.args[0])
    # Without as_of the temporal predicate must not appear at all.
    assert "ts::date <= :cutoff" not in sql_text, (
        "recency query injected cutoff clause without an as_of value"
    )


def test_fetch_memory_recall_renders_sim_tags(monkeypatch) -> None:
    """The 2026-06-12 bug: SQLAlchemy Rows are immutable, so the sim=
    tag assignment silently no-op'd under suppress(AttributeError) and
    EVERY recall rendered as 'recency' even when similarity produced it.
    Pin that similarity results now carry their sim= tag end-to-end."""
    from datetime import datetime
    from types import SimpleNamespace

    from tessera_worker.agents import prompt_assembler as pa

    fake_rows = [
        SimpleNamespace(thesis_md="moat thesis " * 5,
                        ts=datetime(2026, 6, 10, tzinfo=UTC),
                        _recall_tag="sim=0.367"),
        SimpleNamespace(thesis_md="margin thesis " * 5,
                        ts=datetime(2026, 6, 5, tzinfo=UTC),
                        _recall_tag="sim=0.371"),
    ]
    monkeypatch.setattr(pa, "_fetch_by_similarity",
                        lambda *a, **k: fake_rows)
    block = pa.fetch_memory_recall(None, "peter", "COST",
                                   query_text="costco economics")
    assert "sim=0.367" in block and "sim=0.371" in block
    assert "recency" not in block
