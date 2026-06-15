"""Typed Anthropic thesis calls with validation, cost logging, and DB persist."""

from __future__ import annotations

import contextlib
import json
import re
import sys
import time
from datetime import date
from typing import Any
from uuid import UUID

# Force UTF-8 stdout so thesis output (with Unicode arrows/box chars
# from sparklines, Korean text, etc.) doesn't crash Windows cp1252 consoles.
with contextlib.suppress(AttributeError):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

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
    """Parse the first complete JSON object from the LLM response,
    tolerating BOTH leading prose and trailing chatter.

    Trailing: `raw_decode` returns (obj, end_index); anything past
    end_index is logged + ignored (2026-06-04 backtest: ~5% of Cathie
    cells appended commentary after the brace).

    Leading: scan forward from each '{' until one parses. Found
    2026-06-12 — construction RETRY calls failed 4-for-4 with
    "Expecting value: char 0" because the model prefixes its reworked
    book with an explanation of what it changed, despite "Return ONLY
    the JSON" (the retry feedback invites exactly that). The responses
    carried full valid books (2-4.5K tokens) that we were throwing
    away, costing warren+cathie their weekly rebalance.
    """
    text_in = _strip_json_fences(raw).strip()
    decoder = json.JSONDecoder()
    try:
        obj, end_idx = decoder.raw_decode(text_in)
    except json.JSONDecodeError:
        # Leading prose: try each '{' until something parses. Prose can
        # itself contain braces ("a {weight} of..."), hence the loop
        # rather than a single find.
        start = text_in.find("{")
        obj = None
        end_idx = 0
        while start != -1:
            try:
                obj, inner_end = decoder.raw_decode(text_in[start:])
                end_idx = start + inner_end
                break
            except json.JSONDecodeError:
                start = text_in.find("{", start + 1)
        if obj is None:
            raise
        log.info("parse_llm_json.leading_text_ignored",
                 chars_dropped=start, preview=text_in[:120])
    trailing = text_in[end_idx:].strip()
    if trailing:
        log.info("parse_llm_json.trailing_text_ignored",
                 chars_dropped=len(trailing), preview=trailing[:120])
    if not isinstance(obj, dict):
        raise ValueError(f"Expected JSON object, got {type(obj).__name__}")
    return obj


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

    Observed in early Phase B runs:
      - percent (55), 1-10 scale (7), word ("high"). Normalize before
        Pydantic validation so a purely-formatting error doesn't burn a
        retry. Out-of-range still hard-rejects.
      - **field omitted entirely** — seen in 2026-06-04 backtest, Cathie
        outputs the full proposal but drops `conviction`. The retry
        feedback usually fixes it but not always. Fill the median (0.5)
        rather than reject; log it so we can see if this gets common.
    """
    # Defensive alias: personalities.md spec drifted to "confidence" at
    # one point (2026-06-04 backtest: 100% of cells missing `conviction`,
    # all defaulted to 0.5, signal completely lost). The spec is fixed
    # but accept the alias here so any future drift can't silently
    # collapse the signal again — we promote `confidence` → `conviction`
    # and let the rest of the function normalize the value.
    if "conviction" not in p and "confidence" in p:
        p["conviction"] = p.pop("confidence")
    if "conviction" not in p:
        log.info("conviction.missing_defaulted_to_median",
                 ticker=p.get("ticker"), side=p.get("side"))
        p["conviction"] = 0.5
        return
    c = p.get("conviction")
    if c is None:
        log.info("conviction.null_defaulted_to_median", ticker=p.get("ticker"))
        p["conviction"] = 0.5
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


def check_daily_budget(session: Any) -> float:
    """Sum today's LLM spend in the GLOBAL namespace and trip the cap if
    we're over. Namespaced calls (e.g. cost_namespace='backtest_baseline')
    are excluded — they have their own accounting via the caller's
    --max-cost flag, so a one-off evaluation run doesn't starve the
    live system."""
    settings = get_settings()
    row = session.execute(
        text("""
            SELECT COALESCE(SUM(cost_usd), 0) AS spent
            FROM llm_call_log
            WHERE ts >= CURRENT_DATE
              AND cost_namespace IS NULL
        """),
    ).mappings().first()
    spent = float(row["spent"] if row else 0)
    if spent >= settings.llm_max_daily_cost_usd:
        raise LlmDailyBudgetExceeded(
            f"LLM spend today ${spent:.4f} >= cap ${settings.llm_max_daily_cost_usd}"
        )
    return spent


def log_llm_call(
    session: Any,
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
    cost_namespace: str | None = None,
) -> None:
    """Append one call to the audit log. `cost_namespace=None` (default)
    means the call counts against the global daily cap; non-None isolates
    it (e.g. 'backtest_baseline' for one-off evaluation runs)."""
    session.execute(
        text("""
            INSERT INTO llm_call_log
                (persona_id, stage, model, tokens_in, tokens_out,
                 cached_tokens, cost_usd, latency_ms, success, error,
                 cost_namespace)
            VALUES (:p, :stage, :model, :ti, :to, :cached, :cost, :lat,
                    :ok, :err, :ns)
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
            "ns": cost_namespace,
        },
    )


def persist_analyst_report(
    session: Any,
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
    report_id: UUID = row[0]

    # Best-effort persona_memory write — one row per proposal so future
    # similarity recall can land on per-(persona, ticker) thesis text.
    # Rejected reports skip memory (we don't want bad theses retrieved).
    if not rejected:
        try:
            _persist_persona_memory(session, report, report_id=report_id)
        except Exception as e:
            log.warning("persona_memory.write_failed",
                        persona=report.persona_id, error=str(e))

    return report_id


def _persist_persona_memory(session: Any, report: AnalystReport, *, report_id: UUID) -> int:
    """One row per proposal into persona_memory with a Voyage embedding.

    Embedding write is best-effort:
      - voyage_api_key blank or library missing → embedding=NULL row
        still inserted (recency-only recall continues to work).
      - Embedding API failure → embedding=NULL row inserted, warning logged.
    """
    from tessera_worker.agents.embeddings import embed_thesis, to_pgvector_literal

    if not report.proposals:
        return 0

    written = 0
    embedded = 0
    for prop in report.proposals:
        vec = embed_thesis(prop.thesis_md)
        if vec is not None:
            session.execute(
                text("""
                    INSERT INTO persona_memory
                        (persona_id, ticker, ts, thesis_md, embedding, report_id)
                    VALUES
                        (:p, :t, NOW(), :md, CAST(:emb AS vector), :rid)
                """),
                {"p": report.persona_id, "t": prop.ticker,
                 "md": prop.thesis_md, "emb": to_pgvector_literal(vec),
                 "rid": str(report_id)},
            )
            embedded += 1
        else:
            session.execute(
                text("""
                    INSERT INTO persona_memory
                        (persona_id, ticker, ts, thesis_md, embedding, report_id)
                    VALUES
                        (:p, :t, NOW(), :md, NULL, :rid)
                """),
                {"p": report.persona_id, "t": prop.ticker,
                 "md": prop.thesis_md, "rid": str(report_id)},
            )
        written += 1
    log.info("persona_memory.written",
             persona=report.persona_id, rows=written, with_embeddings=embedded)
    return written


def _retry_guidance_for(error_message: str) -> str:
    """Pick a corrective instruction tuned to the actual failure mode.
    Generic 'fix it' guidance lets the model repeat the same mistake
    (especially Cathie + trailing-commentary). Pattern-match the error
    and tell it specifically what to do.
    """
    err = error_message.lower()
    if "extra data" in err or "jsondecodeerror" in err:
        return (
            "Your last response had text AFTER the closing brace `}`. Return "
            "ONLY a single JSON object, then stop — no commentary, no "
            "scenario narration, no second code block, no closing remarks. "
            "First character must be `{`, last character must be `}`."
        )
    if "what_would_make_me_wrong" in err and "too_long" in err:
        return (
            "Trim `what_would_make_me_wrong` to at most 8 items, keeping "
            "the strongest. Return ONLY the JSON object."
        )
    if "conviction" in err and "missing" in err:
        return (
            "Include the `conviction` field on every proposal (float 0.0-1.0). "
            "Return ONLY the JSON object."
        )
    if "cited_news_ids" in err:
        return (
            "Use only `n_xxxxxxxx` short identifiers from the news block I "
            "provided. Drop any citation whose id isn't in that list. "
            "Return ONLY the JSON object."
        )
    # Fallback — covers Pydantic constraint violations not yet pattern-matched.
    return (
        "Fix the validation problem above and return ONLY the JSON object "
        "(no commentary, no extra text)."
    )


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
        # Tailor the corrective instruction to what actually broke.
        # Generic "Fix JSON only" was insufficient when the model added
        # commentary after the closing brace — it kept doing it.
        guidance = _retry_guidance_for(feedback)
        user_content = (
            f"{user_content}\n\n---\nYour previous output was rejected:\n"
            f"{feedback}\n\n{guidance}"
        )

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
    # Anthropic SDK content blocks are a wide union (text, thinking, tool
    # results, etc.) — we only request text, so block 0 always has `.text`.
    raw = getattr(resp.content[0], "text", "") if resp.content else ""
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
    cost_namespace: str | None = None,
) -> AnalystReport:
    """Assemble prompt, call Claude, validate, optionally save to analyst_reports."""
    settings = get_settings()
    if not settings.feature_real_llm:
        raise LlmDisabledError(
            "FEATURE_REAL_LLM=false — set FEATURE_REAL_LLM=true in "
            "apps/worker/.env to call Anthropic"
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
                        cost_namespace=cost_namespace,
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
                    cost_namespace=cost_namespace,
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
                    cost_namespace=cost_namespace,
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
    # Force-set, NOT setdefault: these fields are server-authoritative.
    # With setdefault, an `as_of` the LLM volunteered in its JSON won the
    # tie — and Ray's Sonnet output reliably includes one, copied from
    # prompt context/training rather than today. Every Ray row written
    # 2026-06-10 landed with as_of_date=2025-01-24 that way; the paper
    # engine then logged "book 2025-01-24" on its first run (fills were
    # still correct — freshest row by ts — but date-scoped readers like
    # /api/proposals' MAX(as_of_date) only worked by luck because ALL
    # Ray rows carried the same wrong date).
    parsed["persona_id"] = "ray"
    parsed["as_of"] = as_of.isoformat()
    parsed["inputs_hash"] = inputs_hash
    parsed["model"] = model
    parsed["tokens_in"] = tokens_in
    parsed["tokens_out"] = tokens_out
    parsed["cost_usd"] = cost_usd
    return RegimeReport.model_validate(parsed)


def persist_regime_report(
    session: Any,
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
    return UUID(str(row[0]))


def run_regime_thesis(
    *,
    as_of: date | None = None,
    persist: bool = True,
    cost_namespace: str | None = None,
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
                # Risk gateway (2026-06-12): same final stop the stock-
                # pickers get. ValueError → this retry loop feeds the
                # reasons back to the model on attempt 0.
                from tessera_worker.risk.gateway import gate_regime
                from tessera_worker.risk.var import load_market_context

                market = load_market_context(
                    session, [a.instrument for a in report.allocations], "ray",
                )
                gate_result = gate_regime(report, market=market)
                if not gate_result.ok:
                    raise ValueError(
                        "risk gateway rejected the regime book: "
                        + "; ".join(gate_result.reasons)
                    )
                log_llm_call(
                    session, persona_id="ray", stage="regime", model=model,
                    tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost,
                    latency_ms=latency_ms, success=True, cached_tokens=cached,
                    cost_namespace=cost_namespace,
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
                    cost_namespace=cost_namespace,
                )
                if attempt == 1:
                    session.commit()
                    raise

        raise RuntimeError("unreachable")


def run_research(
    persona: PersonaId,
    ticker: str,
    *,
    as_of: date | None = None,
    cost_namespace: str | None = None,
) -> dict[str, Any] | None:
    """Pass-1 research call for the 2-pass architecture.

    V1 implementation: reuses `run_thesis()` (so we get all the prompt
    plumbing for free) but DOES NOT PERSIST, and reshapes the output to
    a TickerResearch-style dict suitable for `construct_portfolio`. The
    sizing fields the thesis call produces (target_weight, cash_target,
    side) are dropped — Pass 2 is the only place sizing happens.

    A lighter dedicated research prompt (with explicit bull/bear sections
    and no sizing instructions) is a v2 follow-up; the immediate goal is
    to land the 2-pass FLOW so the construction call has notes to act on.
    Returns None on failure (don't take down the rest of the batch).
    """
    try:
        report = run_thesis(
            persona, ticker, as_of=as_of, persist=False,
            cost_namespace=cost_namespace,
        )
    except Exception as e:
        log.warning("run_research.failed", persona=persona, ticker=ticker, err=str(e))
        return None
    if not report.proposals:
        return None
    p = report.proposals[0]
    # Derive bull/bear from thesis_md + what_would_make_me_wrong when the
    # research prompt doesn't yet split them. The construction prompt
    # consumes either pattern equally.
    thesis_paras = [s.strip() for s in p.thesis_md.split("\n\n") if s.strip()]
    bull = thesis_paras[0] if thesis_paras else p.thesis_md[:500]
    bear = (
        "; ".join(p.what_would_make_me_wrong)
        if p.what_would_make_me_wrong
        else "(no explicit bear case stated)"
    )
    return {
        "ticker": p.ticker,
        "conviction": p.conviction,
        "thesis_md": p.thesis_md,
        "bull_case": bull[:1000],
        "bear_case": bear[:1000],
        "what_would_make_me_wrong": p.what_would_make_me_wrong,
        "cost_usd": report.cost_usd,
        "tokens_in": report.tokens_in,
        "tokens_out": report.tokens_out,
    }


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
        regime_report = run_regime_thesis()
        print(regime_report.model_dump_json(indent=2))
        return 0
    if len(sys.argv) < 3:
        print(f"Persona '{persona}' requires a ticker arg.")
        return 1
    ticker = sys.argv[2].upper()
    analyst_report = run_thesis(persona, ticker)  # type: ignore[arg-type]
    print(analyst_report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
