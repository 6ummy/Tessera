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
