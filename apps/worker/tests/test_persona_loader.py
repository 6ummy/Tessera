"""Tests for personalities.md operational prompt parsing."""

from __future__ import annotations

from tessera_worker.agents.persona_loader import (
    _PERSONA_IDS,
    get_persona_spec,
    load_persona_specs,
    personalities_path,
)


def test_personalities_md_exists() -> None:
    assert personalities_path().name == "personalities.md"


def test_load_all_operational_prompts() -> None:
    specs = load_persona_specs()
    assert set(specs.keys()) == set(_PERSONA_IDS)
    for pid in _PERSONA_IDS:
        body = specs[pid]
        assert len(body) > 200
        assert "### Identity" in body
        assert "### Hard rules" in body or "Hard rules" in body


def test_warren_spec_mentions_value_voice() -> None:
    warren = get_persona_spec("warren")
    assert "value-investing" in warren.lower() or "Value" in warren
    assert "RSI" in warren or "momentum" in warren


def test_no_persona_spec_absorbs_other_personas_chat_sections() -> None:
    """Regression: the last operational section (Peter) used to run to EOF
    and pull in the chat fine-tuning sections + universal policies + the
    versioning block, contaminating Peter's system prompt with content
    meant for chat, including other personas' chat specs. Cap at the
    next `##` header instead."""
    for pid in _PERSONA_IDS:
        body = get_persona_spec(pid)
        # Chat fine-tuning sections are explicitly NOT part of any
        # operational prompt.
        assert "Chat fine-tuning spec" not in body, (
            f"{pid} operational prompt should not contain chat fine-tuning "
            f"content (got {len(body)} chars — likely absorbed neighbouring "
            f"sections)"
        )
        assert "Universal chat policies" not in body, (
            f"{pid} operational prompt should not contain universal chat policies"
        )
        assert "Manager Agent" not in body, (
            f"{pid} operational prompt should not contain Manager Agent section"
        )


def test_persona_spec_lengths_are_in_same_order_of_magnitude() -> None:
    """All four operational prompts target ~600 lines / a few KB of text.
    A 10x outlier means the parser absorbed neighbouring sections."""
    lengths = {pid: len(get_persona_spec(pid)) for pid in _PERSONA_IDS}
    assert all(800 < n < 10_000 for n in lengths.values()), (
        f"some prompts are outside the 800–10K range: {lengths}"
    )
    longest = max(lengths.values())
    shortest = min(lengths.values())
    assert longest / shortest < 3, (
        f"max/min ratio too wide ({longest}/{shortest}); parser likely "
        f"over-included a section. Per-persona lengths: {lengths}"
    )
