"""Validate LLM-cited news IDs against the prompt's news block."""

from __future__ import annotations

from tessera_worker.agents.models import AnalystReport


def validate_citations(
    report: AnalystReport,
    allowed_news_ids: set[str],
) -> list[str]:
    """Return cited UUIDs (as strings) that are not in allowed_news_ids."""
    bad: list[str] = []
    for proposal in report.proposals:
        for raw in proposal.cited_news_ids:
            key = str(raw)
            if key not in allowed_news_ids:
                bad.append(key)
    return bad
