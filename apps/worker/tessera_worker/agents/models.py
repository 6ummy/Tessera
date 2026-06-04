"""LLM output contracts for the agents package.

Authoritative definitions live in tessera_shared; re-export here so agent code
imports from one place.
"""

from tessera_shared.schemas import (
    AnalystReport,
    PersonaId,
    Proposal,
    RegimeAllocation,
    RegimeProbabilities,
    RegimeReport,
    Side,
)

__all__ = [
    "AnalystReport",
    "PersonaId",
    "Proposal",
    "RegimeAllocation",
    "RegimeProbabilities",
    "RegimeReport",
    "Side",
]
