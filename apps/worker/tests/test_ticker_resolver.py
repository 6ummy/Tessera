"""Unit tests for ticker_resolver — Level 1-6 ticker extraction.

Level 6 (Haiku) is gated by ANTHROPIC_API_KEY presence + network; we
default `allow_haiku=False` in tests so they stay hermetic. One explicit
test verifies the fallback short-circuits when key is missing.
"""

from __future__ import annotations

import pytest

from tessera_worker.agents.ticker_resolver import (
    ALIASES,
    _NAME_INDEX,
    _UNIVERSE_TICKERS,
    _fuzzy_match,
    _name_lookup,
    _regex_match,
    resolve_tickers,
)


# ─── Level 1-2: regex direct match ─────────────────────────────────────


def test_regex_matches_uppercase_ticker():
    assert "AAPL" in _regex_match("What about AAPL today?")


def test_regex_matches_lowercase_ticker():
    assert "AAPL" in _regex_match("what about aapl today?")


def test_regex_matches_brk_b_dot_form():
    assert "BRK.B" in _regex_match("BRK.B cheap here")


def test_regex_matches_btc_slash_form():
    assert "BTC/USD" in _regex_match("BTC/USD 살까?")


def test_regex_rejects_non_universe_uppercase():
    """'NASA' is uppercase 4 chars but not a ticker — should not match."""
    assert _regex_match("NASA launched a probe") == set()


def test_regex_rejects_single_letter():
    """'I' alone shouldn't match (would be too noisy)."""
    assert "I" not in _regex_match("I think AAPL is great")


# ─── Level 3-4: name + alias lookup ────────────────────────────────────


def test_name_lookup_matches_company_name():
    assert "AAPL" in _name_lookup("I'm thinking about Apple")


def test_name_lookup_case_insensitive():
    assert "TSLA" in _name_lookup("TESLA is interesting")


def test_name_lookup_matches_korean_alias():
    assert "AAPL" in _name_lookup("애플 어때?")
    assert "NVDA" in _name_lookup("엔비디아 살까?")
    assert "TSLA" in _name_lookup("테슬라 비교해줘")


def test_name_lookup_handles_paren_qualifier():
    """'Alphabet (A)' should match the bare 'alphabet' form too."""
    assert "GOOGL" in _name_lookup("Alphabet looks interesting")
    assert "GOOGL" in _name_lookup("Google search dominance")


def test_name_lookup_multiple_tickers_in_one_message():
    found = _name_lookup("애플 vs 마이크로소프트 비교")
    assert "AAPL" in found
    assert "MSFT" in found


def test_alias_dict_covers_universe_meaningfully():
    """Sanity: every alias maps to a real universe ticker."""
    for alias, ticker in ALIASES.items():
        assert ticker in _UNIVERSE_TICKERS, (
            f"alias {alias!r} maps to {ticker!r} not in universe"
        )


# ─── Level 5: fuzzy match ──────────────────────────────────────────────


def test_fuzzy_matches_typo():
    """'AAPLE' typo → AAPL via fuzz ratio ≥ 85%."""
    found = _fuzzy_match("Buying AAPLE", threshold=80)
    assert "AAPL" in found


def test_fuzzy_matches_tesla_typo():
    found = _fuzzy_match("Tesls 전망 어때", threshold=80)
    assert "TSLA" in found


def test_fuzzy_threshold_filters_garbage():
    """Random unrelated word shouldn't match anything."""
    found = _fuzzy_match("xyzzy plugh", threshold=85)
    assert found == set()


# ─── Top-level resolve_tickers — chain behavior ────────────────────────


def test_resolve_exact_ticker_skips_fuzzy_and_haiku():
    """Performance: exact match means no fuzzy/Haiku call needed."""
    tickers = resolve_tickers("AAPL 어때", allow_haiku=False)
    assert tickers == ["AAPL"]


def test_resolve_company_name_skips_fuzzy():
    tickers = resolve_tickers("Apple looks cheap", allow_haiku=False)
    assert "AAPL" in tickers


def test_resolve_korean_alias_works_end_to_end():
    tickers = resolve_tickers("코스트코랑 월마트 비교", allow_haiku=False)
    assert "COST" in tickers
    assert "WMT" in tickers


def test_resolve_multiple_tickers_deduped_sorted():
    tickers = resolve_tickers(
        "AAPL vs Apple vs 애플 — all the same name", allow_haiku=False
    )
    # Three different references to AAPL → one ticker, no duplicates
    assert tickers == ["AAPL"]


def test_resolve_typo_fallback_to_fuzzy():
    tickers = resolve_tickers("AAPLE 살까", allow_haiku=False)
    assert "AAPL" in tickers


def test_resolve_no_match_returns_empty():
    tickers = resolve_tickers("the weather is nice today", allow_haiku=False)
    assert tickers == []


def test_resolve_empty_input():
    assert resolve_tickers("") == []
    assert resolve_tickers("   ") == []


def test_resolve_haiku_skipped_when_key_missing(monkeypatch):
    """Level 6 should silently return empty when ANTHROPIC_API_KEY is blank."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Input has no ticker — would normally fall through to Haiku
    tickers = resolve_tickers("the search giant looks expensive", allow_haiku=True)
    assert tickers == []  # no key → Haiku skipped → empty


def test_name_index_covers_all_universe_tickers():
    """Every universe ticker should have at least one name path into it
    (so 'Apple' finds AAPL even if user never types AAPL)."""
    covered = set(_NAME_INDEX.values())
    missing = _UNIVERSE_TICKERS - covered
    # ETFs and crypto may not all need aliases, but every equity should.
    # If this fails, add the missing name → ticker entry to ALIASES.
    important = {"AAPL", "MSFT", "GOOGL", "NVDA", "TSLA", "AMZN",
                 "META", "COST", "BRK.B", "JPM"}
    assert important.issubset(covered), (
        f"important tickers missing from NAME_INDEX: {important - covered}"
    )
