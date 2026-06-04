"""Typed Anthropic thesis calls with validation, cost logging, and DB persist."""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import date
from typing import Any
from uuid import UUID

# Force UTF-8 stdout so thesis output (with Unicode arrows/box chars
# from sparklines, Korean text, etc.) doesn't crash Windows cp1252 consoles.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

import structlog
from anthropic import Anthropic
from sqlalchemy import text

from tessera_worker.agents.citation_validator import validate_citations
from tessera_worker.agents.models import AnalystReport, PersonaId, Proposal
from tessera_worker.agents.prompt_assembler import AssembledPrompt, assemble_prompt
from tessera_worker.config import get_settings
from tessera_worker.db import session_scope

log = structlog.get_logger(__name__)

# USD per 1M tokens (input, output) — update when Anthropic pricing changes.
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (0.8, 4.0),
    "claude-opus-4-7": (15.0, 75.0),
}

_JSON_FENCE = re.compile(r"^```(?:json)?\s*\n?", re.IGNORECASE)
_JSON_FENCE_END = re.compile(r"\n?```\s*$")


class LlmDailyBudgetExceeded(Exception):
    """Raised when today's logged LLM spend exceeds llm_max_daily_cost_usd."""


class LlmDisabledError(Exception):
    """Raised when FEATURE_REAL_LLM is false."""


def estimate_cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    in_rate, out_rate = _MODEL_PRICING.get(model, (3.0, 15.0))
    return (tokens_in * in_rate + tokens_out * out_rate) / 1_000_000


def _strip_json_fences(text: str) -> str:
    t = text.strip()
    t = _JSON_FENCE.sub("", t)
    t = _JSON_FENCE_END.sub("", t)
    return t.strip()


def parse_llm_json(raw: str) -> dict[str, Any]:
    return json.loads(_strip_json_fences(raw))


def _resolve_news_uuid(item: Any, allowed_news_ids: set[str]) -> UUID:
    if isinstance(item, UUID):
        return item
    s = str(item).strip()
    if s.startswith("n_"):
        prefix = s[2:].replace("-", "")
        for aid in allowed_news_ids:
            if aid.replace("-", "").startswith(prefix):
                return UUID(aid)
        raise ValueError(f"unknown short news id {s}")
    return UUID(s)


_CONVICTION_WORDS = {
    "low": 0.25, "weak": 0.25,
    "medium": 0.5, "moderate": 0.5, "neutral": 0.5,
    "high": 0.75, "strong": 0.75,
    "very high": 0.9, "very strong": 0.9, "max": 0.95,
}


def _normalize_conviction(p: dict[str, Any]) -> None:
    """Coerce common LLM mistakes into Proposal.conviction's [0,1] float.

    Observed in early Phase B runs: model occasionally returns conviction
    as a percent (55), an integer (1-10 scale), or a word ("high"). We
    normalize before Pydantic validation so we don't waste a retry on a
    purely-formatting error. Out-of-range remains a hard reject.
    """
    c = p.get("conviction")
    if c is None:
        return
    if isinstance(c, str):
        word = c.strip().lower()
        if word in _CONVICTION_WORDS:
            p["conviction"] = _CONVICTION_WORDS[word]
            return
        try:
            c = float(word)
            p["conviction"] = c  # store the float so scale-rescue can re-touch it
        except ValueError:
            return  # Let Pydantic raise the clearer error.
    if isinstance(c, (int, float)):
        if c > 1 and c <= 10:        # 1-10 scale
            p["conviction"] = c / 10.0
        elif c > 10 and c <= 100:    # percent
            p["conviction"] = c / 100.0


def build_analyst_report(
    parsed: dict[str, Any],
    *,
    persona_id: PersonaId,
    as_of: date,
    inputs_hash: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    allowed_news_ids: set[str],
) -> AnalystReport:
    proposals_raw = parsed.get("proposals") or []
    for p in proposals_raw:
        _normalize_conviction(p)
        ids = p.get("cited_news_ids") or []
        p["cited_news_ids"] = [_resolve_news_uuid(x, allowed_news_ids) for x in ids]
    proposals = [Proposal.model_validate(p) for p in proposals_raw]
    return AnalystReport(
        persona_id=persona_id,
        as_of=as_of,
        proposals=proposals,
        cash_target=float(parsed.get("cash_target", 0)),
        notes_to_manager=str(parsed.get("notes_to_manager") or ""),
        inputs_hash=inputs_hash,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
    )


def check_daily_budget(session) -> float:
    settings = get_settings()
    row = session.execute(
        text("""
            SELECT COALESCE(SUM(cost_usd), 0) AS spent
            FROM llm_call_log
            WHERE ts >= CURRENT_DATE
        """),
    ).mappings().first()
    spent = float(row["spent"] if row else 0)
    if spent >= settings.llm_max_daily_cost_usd:
        raise LlmDailyBudgetExceeded(
            f"LLM spend today ${spent:.4f} >= cap ${settings.llm_max_daily_cost_usd}"
        )
    return spent


def log_llm_call(
    session,
    *,
    persona_id: PersonaId | None,
    stage: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    latency_ms: int,
    success: bool,
    error: str | None = None,
    cached_tokens: int = 0,
) -> None:
    session.execute(
        text("""
            INSERT INTO llm_call_log
                (persona_id, stage, model, tokens_in, tokens_out,
                 cached_tokens, cost_usd, latency_ms, success, error)
            VALUES (:p, :stage, :model, :ti, :to, :cached, :cost, :lat, :ok, :err)
        """),
        {
            "p": persona_id,
            "stage": stage,
            "model": model,
            "ti": tokens_in,
            "to": tokens_out,
            "cached": cached_tokens,
            "cost": cost_usd,
            "lat": latency_ms,
            "ok": success,
            "err": error,
        },
    )


def persist_analyst_report(
    session,
    report: AnalystReport,
    *,
    raw_response: str,
    rejected: bool = False,
    reject_reasons: list[str] | None = None,
) -> UUID:
    row = session.execute(
        text("""
            INSERT INTO analyst_reports
                (persona_id, as_of_date, inputs_hash, raw_response, parsed,
                 model, tokens_in, tokens_out, cost_usd, rejected, reject_reasons)
            VALUES
                (:p, :d, :h, :raw, CAST(:parsed AS jsonb),
                 :model, :ti, :to, :cost, :rej, :reasons)
            RETURNING id
        """),
        {
            "p": report.persona_id,
            "d": report.as_of,
            "h": report.inputs_hash,
            "raw": raw_response,
            "parsed": report.model_dump_json(),
            "model": report.model,
            "ti": report.tokens_in,
            "to": report.tokens_out,
            "cost": report.cost_usd,
            "rej": rejected,
            "reasons": reject_reasons or [],
        },
    ).first()
    return row[0]


def call_anthropic_thesis(
    assembled: AssembledPrompt,
    *,
    feedback: str | None = None,
) -> tuple[str, int, int, int, int]:
    """Return (raw_text, tokens_in, tokens_out, cached_tokens, latency_ms)."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set")
    client = Anthropic(api_key=settings.anthropic_api_key)
    user_content = assembled.user_message
    if feedback:
        user_content = f"{user_content}\n\n---\nValidation failed:\n{feedback}\nFix JSON only."

    t0 = time.perf_counter()
    resp = client.messages.create(
        model=settings.llm_model_thesis,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": assembled.system_prompt,
                "cache_control": {"type": "ephemeral"},
            },
        ],
        messages=[{"role": "user", "content": user_content}],
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    raw = resp.content[0].text if resp.content else ""
    usage = resp.usage
    tokens_in = usage.input_tokens
    tokens_out = usage.output_tokens
    cached = getattr(usage, "cache_read_input_tokens", 0) or 0
    log.info(
        "anthropic_thesis_ok",
        persona=assembled.persona_id,
        ticker=assembled.ticker,
        latency_ms=latency_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )
    return raw, tokens_in, tokens_out, cached, latency_ms


def run_thesis(
    persona: PersonaId,
    ticker: str,
    *,
    as_of: date | None = None,
    persist: bool = True,
) -> AnalystReport:
    """Assemble prompt, call Claude, validate, optionally save to analyst_reports."""
    settings = get_settings()
    if not settings.feature_real_llm:
        raise LlmDisabledError(
            "FEATURE_REAL_LLM=false — set FEATURE_REAL_LLM=true in apps/worker/.env to call Anthropic"
        )

    assembled = assemble_prompt(persona, ticker, as_of=as_of)
    model = settings.llm_model_thesis
    raw = ""
    tokens_in = tokens_out = cached = latency_ms = 0
    last_error: str | None = None

    with session_scope() as session:
        check_daily_budget(session)

        for attempt in range(2):
            feedback = last_error if attempt > 0 else None
            try:
                raw, tokens_in, tokens_out, cached, latency_ms = call_anthropic_thesis(
                    assembled, feedback=feedback
                )
                cost = estimate_cost_usd(model, tokens_in, tokens_out)
                parsed = parse_llm_json(raw)
                report = build_analyst_report(
                    parsed,
                    persona_id=persona,
                    as_of=assembled.as_of,
                    inputs_hash=assembled.inputs_hash,
                    model=model,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost,
                    allowed_news_ids=set(assembled.news_ids),
                )
                bad_cites = validate_citations(report, set(assembled.news_ids))
                if bad_cites:
                    last_error = f"Invalid cited_news_ids: {bad_cites}"
                    if attempt == 0:
                        continue
                    log_llm_call(
                        session,
                        persona_id=persona,
                        stage="thesis",
                        model=model,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        cost_usd=cost,
                        latency_ms=latency_ms,
                        success=False,
                        error=last_error,
                        cached_tokens=cached,
                    )
                    if persist:
                        persist_analyst_report(
                            session,
                            report,
                            raw_response=raw,
                            rejected=True,
                            reject_reasons=[last_error],
                        )
                    raise ValueError(last_error)

                log_llm_call(
                    session,
                    persona_id=persona,
                    stage="thesis",
                    model=model,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost,
                    latency_ms=latency_ms,
                    success=True,
                    cached_tokens=cached,
                )
                if persist:
                    persist_analyst_report(session, report, raw_response=raw)
                session.commit()
                return report

            except (json.JSONDecodeError, ValueError) as exc:
                last_error = str(exc)
                cost = estimate_cost_usd(model, tokens_in, tokens_out)
                log_llm_call(
                    session,
                    persona_id=persona,
                    stage="thesis",
                    model=model,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost,
                    latency_ms=latency_ms,
                    success=False,
                    error=last_error,
                    cached_tokens=cached,
                )
                if attempt == 1:
                    session.commit()
                    raise

        raise RuntimeError("unreachable")


# ─────────────────────────────────────────────────────────────────────────
# Ray-specific runner — outputs RegimeReport (asset-class allocations +
# regime probabilities) instead of AnalystReport (stock picks).
# Shares prompt_assembler + persona spec + Claude wrapper, only the
# response schema differs.
# ─────────────────────────────────────────────────────────────────────────
from tessera_worker.agents.models import RegimeReport  # noqa: E402


def build_regime_report(
    parsed: dict[str, Any],
    *,
    as_of: date,
    inputs_hash: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
) -> RegimeReport:
    parsed.setdefault("persona_id", "ray")
    parsed.setdefault("as_of", as_of.isoformat())
    parsed["inputs_hash"] = inputs_hash
    parsed["model"] = model
    parsed["tokens_in"] = tokens_in
    parsed["tokens_out"] = tokens_out
    parsed["cost_usd"] = cost_usd
    return RegimeReport.model_validate(parsed)


def persist_regime_report(
    session,
    report: RegimeReport,
    *,
    raw_response: str,
    rejected: bool = False,
    reject_reasons: list[str] | None = None,
) -> UUID:
    """Reuse the analyst_reports table; persona_id='ray' is the discriminator."""
    row = session.execute(
        text("""
            INSERT INTO analyst_reports
                (persona_id, as_of_date, inputs_hash, raw_response, parsed,
                 model, tokens_in, tokens_out, cost_usd, rejected, reject_reasons)
            VALUES
                (:p, :d, :h, :raw, CAST(:parsed AS jsonb),
                 :model, :ti, :to, :cost, :rej, :reasons)
            RETURNING id
        """),
        {
            "p": "ray",
            "d": report.as_of,
            "h": report.inputs_hash,
            "raw": raw_response,
            "parsed": report.model_dump_json(),
            "model": report.model,
            "ti": report.tokens_in,
            "to": report.tokens_out,
            "cost": report.cost_usd,
            "rej": rejected,
            "reasons": reject_reasons or [],
        },
    ).first()
    return row[0]


def run_regime_thesis(
    *,
    as_of: date | None = None,
    persist: bool = True,
) -> RegimeReport:
    """Ray-specific path. No ticker — Ray writes a portfolio-level regime read."""
    settings = get_settings()
    if not settings.feature_real_llm:
        raise LlmDisabledError(
            "FEATURE_REAL_LLM=false — set in apps/worker/.env to call Anthropic"
        )

    # Ticker passed to assemble_prompt is unused in Ray's user_message
    # (prompt_assembler branches on persona == 'ray'), but the macros_for()
    # call needs *something*; "PORTFOLIO" is just a label.
    assembled = assemble_prompt("ray", "PORTFOLIO", as_of=as_of)
    model = settings.llm_model_thesis
    raw = ""
    tokens_in = tokens_out = cached = latency_ms = 0
    last_error: str | None = None

    with session_scope() as session:
        check_daily_budget(session)

        for attempt in range(2):
            feedback = last_error if attempt > 0 else None
            try:
                raw, tokens_in, tokens_out, cached, latency_ms = call_anthropic_thesis(
                    assembled, feedback=feedback
                )
                cost = estimate_cost_usd(model, tokens_in, tokens_out)
                parsed = parse_llm_json(raw)
                report = build_regime_report(
                    parsed,
                    as_of=assembled.as_of,
                    inputs_hash=assembled.inputs_hash,
                    model=model,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost,
                )
                log_llm_call(
                    session, persona_id="ray", stage="regime", model=model,
                    tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost,
                    latency_ms=latency_ms, success=True, cached_tokens=cached,
                )
                if persist:
                    persist_regime_report(session, report, raw_response=raw)
                session.commit()
                return report

            except (json.JSONDecodeError, ValueError) as exc:
                last_error = str(exc)
                cost = estimate_cost_usd(model, tokens_in, tokens_out)
                log_llm_call(
                    session, persona_id="ray", stage="regime", model=model,
                    tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost,
                    latency_ms=latency_ms, success=False, error=last_error,
                    cached_tokens=cached,
                )
                if attempt == 1:
                    session.commit()
                    raise

        raise RuntimeError("unreachable")


def main() -> int:
    """CLI: python -m tessera_worker.agents.anthropic_runner <persona> [ticker]
    Ray takes no ticker (portfolio-level): `... ray`
    Others require a ticker:              `... warren AAPL`
    """
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m tessera_worker.agents.anthropic_runner <persona> [ticker]")
        return 1
    persona = sys.argv[1]
    if persona == "ray":
        report = run_regime_thesis()
        print(report.model_dump_json(indent=2))
        return 0
    if len(sys.argv) < 3:
        print(f"Persona '{persona}' requires a ticker arg.")
        return 1
    ticker = sys.argv[2].upper()
    report = run_thesis(persona, ticker)  # type: ignore[arg-type]
    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
