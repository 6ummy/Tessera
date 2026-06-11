"""Unit tests for chat backend — system prompt assembly + persona_loader chat
section extraction. Streaming itself isn't unit-tested (requires Anthropic);
it's smoke-tested via curl after deploy.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from tessera_worker.agents.persona_loader import (
    clear_cache,
    get_chat_spec,
    load_chat_specs,
    load_universal_chat_policies,
)

# ─── Chat spec parsing ────────────────────────────────────────────────


def test_load_chat_specs_returns_four_personas():
    clear_cache()
    specs = load_chat_specs()
    assert set(specs.keys()) == {"warren", "cathie", "ray", "peter"}


def test_chat_spec_contains_signature_phrases_section():
    clear_cache()
    warren = get_chat_spec("warren")
    assert "Signature phrases" in warren
    assert "Cash is a position" in warren


def test_chat_spec_contains_forbidden_phrases_section():
    clear_cache()
    warren = get_chat_spec("warren")
    assert "Forbidden phrases" in warren or "Forbidden" in warren


def test_chat_spec_does_not_bleed_into_next_persona():
    """Spec extraction must respect persona boundaries — Warren's spec
    shouldn't include Cathie's signature phrases."""
    clear_cache()
    warren = get_chat_spec("warren")
    cathie = get_chat_spec("cathie")
    # Cathie's distinctive vocab shouldn't appear in Warren's spec
    assert "S-curve" not in warren or warren.count("S-curve") == 0
    # Warren's distinctive vocab shouldn't appear in Cathie's spec
    assert "Cash is a position" not in cathie


def test_universal_chat_policies_loads():
    clear_cache()
    policies = load_universal_chat_policies()
    assert "personalized portfolio advice" in policies.lower() or \
           "no personalized" in policies.lower()
    assert "hallucination" in policies.lower() or "invent" in policies.lower()


def test_universal_chat_policies_does_not_include_per_persona():
    """The universal section ends before the first per-persona chat spec."""
    clear_cache()
    policies = load_universal_chat_policies()
    # The "## 1. Warren — Chat fine-tuning spec" header should NOT appear
    assert "Warren — Chat fine-tuning" not in policies
    assert "Cathie — Chat fine-tuning" not in policies


# ─── System prompt assembly ────────────────────────────────────────────


def test_assemble_chat_system_prompt_includes_all_sections(monkeypatch):
    """Builds the 6-part system prompt with mocked DB. Verifies each
    required section is present so a regression breaks a test."""
    from tessera_worker.agents import chat

    # Mock session — no actual DB hit. Return empty rows for both block builders.
    session = MagicMock()
    session.execute.return_value.all.return_value = []

    # Disable ticker resolver Haiku call for unit test
    monkeypatch.setattr(chat, "resolve_tickers", lambda text, allow_haiku=True: [])

    system, tickers = chat.assemble_chat_system_prompt(
        session, "warren", "What do you think about value investing?",
    )
    assert "UNIVERSAL CHAT POLICIES" in system
    assert "YOUR INVESTING PHILOSOPHY" in system
    assert "YOUR CHAT VOICE" in system
    assert "YOUR RECENT PUBLISHED REPORTS" in system
    assert "CRITICAL REMINDERS" in system
    assert tickers == []


def test_assemble_chat_includes_features_block_when_ticker_resolved(monkeypatch):
    from tessera_worker.agents import chat

    session = MagicMock()
    # Mock both queries: recent reports (empty), features (one row)
    session.execute.return_value.all.return_value = []

    def mocked_resolve(text, allow_haiku=True):
        return ["AAPL"] if "apple" in text.lower() else []

    monkeypatch.setattr(chat, "resolve_tickers", mocked_resolve)
    monkeypatch.setattr(chat, "_build_ticker_features_block",
                        lambda s, t: f"<features tickers=\"{','.join(t)}\">mock</features>")

    system, tickers = chat.assemble_chat_system_prompt(
        session, "warren", "What do you think about Apple?",
    )
    assert "AAPL" in tickers
    assert "TODAY'S NUMBERS FOR TICKERS" in system
    assert "<features" in system


def test_assemble_chat_omits_features_when_no_ticker(monkeypatch):
    from tessera_worker.agents import chat

    session = MagicMock()
    session.execute.return_value.all.return_value = []
    monkeypatch.setattr(chat, "resolve_tickers", lambda text, allow_haiku=True: [])

    system, tickers = chat.assemble_chat_system_prompt(
        session, "cathie", "What's your overall philosophy?",
    )
    assert tickers == []
    assert "TODAY'S NUMBERS FOR TICKERS" not in system


def test_assemble_chat_critical_reminders_present(monkeypatch):
    """Compliance reminders MUST appear in every system prompt regardless
    of persona / context — they're the last line of defense before the LLM
    forgets the universal policies under user pressure."""
    from tessera_worker.agents import chat
    session = MagicMock()
    session.execute.return_value.all.return_value = []
    monkeypatch.setattr(chat, "resolve_tickers", lambda text, allow_haiku=True: [])

    system, _ = chat.assemble_chat_system_prompt(session, "peter", "hi")
    assert "Never tell the user what to buy/sell" in system
    assert "do not invent" in system.lower() or "not invent" in system.lower()


# ─── Errors are exported ───────────────────────────────────────────────


def test_chat_errors_exported():
    from tessera_worker.agents.chat import ChatBudgetExceeded, ChatDisabledError
    assert issubclass(ChatDisabledError, RuntimeError)
    assert issubclass(ChatBudgetExceeded, RuntimeError)
