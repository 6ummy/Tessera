"""Load per-persona operational system prompts from personalities.md.

Phase B persona runner uses these strings as the cached Anthropic system block
(cache_control: ephemeral). Chat fine-tuning sections are excluded.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Final, Literal

PersonaId = Literal["warren", "cathie", "ray", "peter"]

_PERSONA_IDS: Final[tuple[PersonaId, ...]] = ("warren", "cathie", "ray", "peter")

# Display names in personalities.md operational section headers.
_NAME_BY_ID: Final[dict[PersonaId, str]] = {
    "warren": "Warren",
    "cathie": "Cathie",
    "ray": "Ray",
    "peter": "Peter",
}

_OPERATIONAL_HEADER = re.compile(
    r"^##\s+(Warren|Cathie|Ray|Peter)\s+—\s+Operational system prompt\s*$",
    re.MULTILINE,
)

# Match ANY level-1 or level-2 header (`# ...` or `## ...`). Used to cap the
# LAST persona's body so it doesn't run to EOF and swallow the
# "# Chat fine-tuning specifications" level-1 divider + the subsequent
# `## Universal chat policies`, per-persona chat specs, Manager Agent, and
# Versioning sections that follow Peter's operational prompt.
_ANY_TOP_HEADER = re.compile(r"^#{1,2}\s+", re.MULTILINE)

_ID_BY_NAME: Final[dict[str, PersonaId]] = {
    name: pid for pid, name in _NAME_BY_ID.items()
}


def personalities_path() -> Path:
    """Resolve repo-root personalities.md by walking up from this package."""
    start = Path(__file__).resolve()
    for parent in start.parents:
        candidate = parent / "personalities.md"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "personalities.md not found above tessera_worker/agents; "
        "run from the Tessera monorepo checkout."
    )


def _split_operational_sections(text: str) -> dict[PersonaId, str]:
    matches = list(_OPERATIONAL_HEADER.finditer(text))
    if len(matches) != len(_PERSONA_IDS):
        raise ValueError(
            f"expected {len(_PERSONA_IDS)} operational prompts, found {len(matches)}"
        )

    out: dict[PersonaId, str] = {}
    for i, match in enumerate(matches):
        name = match.group(1)
        pid = _ID_BY_NAME[name]
        start = match.end()
        # End at the next persona operational header (interior personas) OR
        # the next ANY `## ` header (last persona — Peter — to avoid
        # absorbing chat fine-tuning + universal + versioning sections that
        # come after the operational block).
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            next_top = _ANY_TOP_HEADER.search(text, start)
            end = next_top.start() if next_top else len(text)
        body = text[start:end].strip()
        # Drop trailing horizontal rule before the next major doc section.
        body = re.sub(r"\n---\s*$", "", body).strip()
        out[pid] = body

    missing = [p for p in _PERSONA_IDS if p not in out]
    if missing:
        raise ValueError(f"missing operational prompts for: {missing}")
    return out


@lru_cache(maxsize=1)
def load_persona_specs(path: str | Path | None = None) -> dict[PersonaId, str]:
    """Return operational system prompt body per persona (no markdown header)."""
    md_path = Path(path) if path is not None else personalities_path()
    text = md_path.read_text(encoding="utf-8")
    return _split_operational_sections(text)


def get_persona_spec(persona_id: PersonaId, path: str | Path | None = None) -> str:
    """Single persona operational prompt (Identity … Hard rules)."""
    return load_persona_specs(path)[persona_id]


def clear_cache() -> None:
    """Test helper: invalidate cached personalities.md parse."""
    load_persona_specs.cache_clear()
    load_chat_specs.cache_clear()
    load_universal_chat_policies.cache_clear()


# ─────────────────────────────────────────────────────────────────────────
# Chat fine-tuning sections (separate from the operational prompt).
# Used by /api/chat/{persona_id} to inject voice + format rules into the
# system block. The operational prompt produces structured JSON; the chat
# spec produces prose in the persona's voice.
# ─────────────────────────────────────────────────────────────────────────

_CHAT_HEADER = re.compile(
    r"^##\s+\d+\.\s+(Warren|Cathie|Ray|Peter)\s+—\s+Chat fine-tuning spec\s*$",
    re.MULTILINE,
)

_UNIVERSAL_CHAT_HEADER = re.compile(
    r"^##\s+Universal chat policies[^\n]*$",
    re.MULTILINE,
)


def _split_chat_sections(text: str) -> dict[PersonaId, str]:
    matches = list(_CHAT_HEADER.finditer(text))
    if len(matches) != len(_PERSONA_IDS):
        raise ValueError(
            f"expected {len(_PERSONA_IDS)} chat fine-tuning specs, "
            f"found {len(matches)}"
        )
    out: dict[PersonaId, str] = {}
    for i, match in enumerate(matches):
        name = match.group(1)
        pid = _ID_BY_NAME[name]
        start = match.end()
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            next_top = _ANY_TOP_HEADER.search(text, start)
            end = next_top.start() if next_top else len(text)
        body = text[start:end].strip()
        body = re.sub(r"\n---\s*$", "", body).strip()
        out[pid] = body
    return out


def _extract_universal_chat(text: str) -> str:
    match = _UNIVERSAL_CHAT_HEADER.search(text)
    if not match:
        raise ValueError("'## Universal chat policies' section not found")
    start = match.end()
    next_top = _ANY_TOP_HEADER.search(text, start)
    end = next_top.start() if next_top else len(text)
    body = text[start:end].strip()
    body = re.sub(r"\n---\s*$", "", body).strip()
    return body


@lru_cache(maxsize=1)
def load_chat_specs(path: str | Path | None = None) -> dict[PersonaId, str]:
    """Per-persona chat fine-tuning spec (response shape, voice, forbidden phrases)."""
    md_path = Path(path) if path is not None else personalities_path()
    text = md_path.read_text(encoding="utf-8")
    return _split_chat_sections(text)


@lru_cache(maxsize=1)
def load_universal_chat_policies(path: str | Path | None = None) -> str:
    """Universal chat policies (compliance, no personalized advice, identity, …)."""
    md_path = Path(path) if path is not None else personalities_path()
    text = md_path.read_text(encoding="utf-8")
    return _extract_universal_chat(text)


def get_chat_spec(persona_id: PersonaId, path: str | Path | None = None) -> str:
    """Single persona chat fine-tuning spec."""
    return load_chat_specs(path)[persona_id]
