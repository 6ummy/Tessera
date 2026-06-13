"""FastAPI server entry point for HTTP-triggered jobs.

Cloud Run can invoke endpoints here via Cloud Scheduler or Vercel Cron webhooks.
For long-running batch (>60s), prefer Cloud Run Jobs invoked directly:
    python -m tessera_worker.jobs.<name>

Auth model:
  - /health is public (Cloud Run liveness probe + uptime checks)
  - /jobs/*  requires `Authorization: Bearer ${WORKER_WEBHOOK_SECRET}`
    which Vercel's cron route forwards (see apps/web/app/api/cron/daily/route.ts).
    Cloud Run is deployed --allow-unauthenticated, so this bearer is the only
    thing between the public internet and our jobs.
"""

from __future__ import annotations

import contextlib
import hmac
from collections.abc import AsyncGenerator
from datetime import date
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from tessera_worker.config import get_settings
from tessera_worker.logging import configure_logging, get_logger
from tessera_worker.observability import init_sentry

configure_logging()
log = get_logger(__name__)

_settings = get_settings()
init_sentry()

app = FastAPI(title="Tessera Worker", version="0.1.0")


def _require_webhook_auth(authorization: str | None) -> None:
    """Reject /jobs/* + /api/* requests that aren't authorized.

    Three modes, in priority order:

    1. **RELY_ON_IAM=true**: Cloud Run was deployed with
       `--no-allow-unauthenticated`, so the IAM layer validated a Google-
       signed identity token before the request reached this app. We
       trust IAM and skip the app-level bearer check. The Authorization
       header still arrives (Cloud Run forwards it) but we don't re-
       verify the JWT — re-validating Google's signature in-app would
       just duplicate what Cloud Run already did.

    2. **bearer secret set + present**: shared `WORKER_WEBHOOK_SECRET`
       between Vercel proxies and this worker. Used during the rollout
       window before --no-allow-unauthenticated flips, and as the
       permanent guard if we ever revert to --allow-unauthenticated.

    3. **bearer secret blank**: dev mode, no auth. Cloud Run prod always
       has the secret set unless RELY_ON_IAM is on.
    """
    if _settings.rely_on_iam:
        return
    expected = _settings.worker_webhook_secret
    if not expected:
        # No secret configured -> open mode for local dev. Cloud Run always has one.
        return
    # Constant-time compare — a plain != short-circuits on the first
    # differing byte, which leaks prefix-match timing to an attacker
    # probing the public Cloud Run URL.
    if not hmac.compare_digest(authorization or "", f"Bearer {expected}"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="bad or missing bearer",
        )


@app.get("/health")
async def health() -> dict[str, str]:
    """Public liveness probe."""
    return {"status": "ok", "env": _settings.env}


@app.post("/jobs/ingest-daily")
async def trigger_ingest_daily(
    background: BackgroundTasks,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    """Trigger the daily ingestion pipeline. Vercel Cron calls this at 16:30 ET.

    Runs in the background so we can return 202 immediately (Vercel cron has
    a short fetch timeout, and the real ingest takes ~7 minutes).
    """
    _require_webhook_auth(authorization)
    # Lazy import: the jobs module pulls in pandas/sqlalchemy/etc., and we don't
    # want that cost on every cold start of /health.
    from tessera_worker.jobs.ingest_daily import run as run_ingest

    def _job() -> None:
        try:
            results = run_ingest()
            log.info("ingest_daily.bg_done",
                     passed=sum(r.ok for r in results),
                     failed=sum(not r.ok for r in results))
        except Exception:
            log.exception("ingest_daily.bg_failed")
            raise  # let Sentry capture

    background.add_task(_job)
    log.info("ingest_daily.queued")
    return {"status": "queued", "job": "ingest_daily"}


@app.post("/jobs/persona-batch")
async def trigger_persona_batch(
    background: BackgroundTasks,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    """Trigger the weekly persona thesis batch.

    Vercel Cron hits this Fri close (see apps/web/vercel.json `cron/weekly`).
    Runs in the background — a full 4-persona batch takes 5–10 min.

    Sequence: persona_batch → hallucination_canary on the freshly-written
    rows. A canary violation pages on-call via Sentry but doesn't roll
    back the batch (rejected rows are already isolated via Pydantic +
    citation_validator at write time).
    """
    _require_webhook_auth(authorization)
    from datetime import date as _date

    from tessera_worker.db import session_scope
    from tessera_worker.jobs.hallucination_canary import run_canary
    from tessera_worker.jobs.persona_batch import run_batch_v2

    def _job() -> None:
        try:
            # v2: research → construct → persist-one-row per persona.
            # Deterministic Python normalize guarantees sum=1.0.
            result = run_batch_v2()  # all 4 personas, defaults
            log.info("persona_batch.bg_done",
                     attempted=result.attempted, persisted=result.persisted,
                     errors=result.errors, cost_usd=round(result.total_cost_usd, 3),
                     aborted=bool(result.aborted_reason))
            # Canary runs against today's analyst_reports rows — i.e. what
            # this batch just wrote. analyst_reports has no run_id, so
            # `--since today` is the cleanest scoping proxy.
            with session_scope() as session:
                canary = run_canary(session, table="analyst_reports",
                                    since=_date.today())
            log.info("persona_batch.canary_done",
                     rows=canary.rows_checked,
                     violations=len(canary.violations),
                     passed=canary.passed)
            if not canary.passed:
                try:
                    import sentry_sdk
                    sentry_sdk.capture_message(
                        f"persona_batch canary FAILED — "
                        f"{len(canary.violations)} violations across "
                        f"{canary.rows_checked} fresh reports",
                        level="error",
                    )
                except Exception:
                    pass
        except Exception:
            log.exception("persona_batch.bg_failed")
            raise  # Sentry captures

    background.add_task(_job)
    log.info("persona_batch.queued")
    return {"status": "queued", "job": "persona_batch"}


# ── Chat input caps ──────────────────────────────────────────────────────
# The chat endpoint is reachable from the public internet (Vercel proxy,
# no user auth until Phase D) and `message` + `history` are entirely
# client-controlled. Without caps a single request can carry an arbitrary
# token bill — the daily budget pools bound the damage per day, these
# bound it per request. Values are generous for real usage: the UI sends
# short questions plus its own accumulated history.
MAX_CHAT_MESSAGE_CHARS = 4_000
MAX_CHAT_HISTORY_TURNS = 20
MAX_CHAT_HISTORY_ITEM_CHARS = 4_000


def _sanitize_chat_history(raw: object) -> list[dict[str, str]]:
    """Clamp client-supplied chat history to a safe shape.

    Keeps only well-formed {role, content} dicts with role in
    user/assistant, truncates each content, and keeps the most recent
    MAX_CHAT_HISTORY_TURNS items. Malformed entries are dropped silently —
    history is a courtesy for conversational continuity, not critical
    state worth a 400."""
    if not isinstance(raw, list):
        return []
    clean: list[dict[str, str]] = []
    for item in raw[-MAX_CHAT_HISTORY_TURNS:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str) or not content:
            continue
        clean.append({"role": role, "content": content[:MAX_CHAT_HISTORY_ITEM_CHARS]})
    return clean


@app.post("/api/chat/{persona_id}")
async def chat_stream(
    persona_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    """SSE-stream a Sonnet 4.6 response in the persona's chat voice.

    Body JSON:
      { "message": "...user input...",
        "history": [{"role": "user"|"assistant", "content": "..."}, ...] }

    Response: `text/event-stream`. Each token arrives as
      data: <text-delta>\\n\\n
    The stream ends with
      data: [DONE]\\n\\n

    Cost / safety: shares `check_daily_budget()` with the thesis path, so
    chat cannot blow the daily LLM cap. Also gated by `FEATURE_REAL_LLM`.
    """
    _require_webhook_auth(authorization)
    if persona_id not in ("warren", "cathie", "ray", "peter"):
        raise HTTPException(status_code=400, detail=f"unknown persona: {persona_id}")

    body = await request.json()
    message = body.get("message")
    if not message or not isinstance(message, str):
        raise HTTPException(status_code=400, detail="missing 'message'")
    if len(message) > MAX_CHAT_MESSAGE_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"message too long ({len(message)} > {MAX_CHAT_MESSAGE_CHARS} chars)",
        )
    history = _sanitize_chat_history(body.get("history"))

    from tessera_worker.agents.chat import (
        ChatBudgetExceeded,
        ChatDisabledError,
        run_chat_stream,
    )

    async def _event_stream() -> AsyncGenerator[str, None]:
        # SSE: 'data: <text>\\n\\n' chunks then 'data: [DONE]\\n\\n'.
        try:
            async for delta in run_chat_stream(persona_id, message, history):  # type: ignore[arg-type]
                # Replace newlines so SSE event boundaries don't split mid-message
                safe = delta.replace("\n", "\\n")
                yield f"data: {safe}\n\n"
            yield "data: [DONE]\n\n"
        except ChatDisabledError as e:
            yield f"event: error\ndata: chat_disabled: {e}\n\n"
        except ChatBudgetExceeded as e:
            yield f"event: error\ndata: budget_exceeded: {e}\n\n"
        except Exception as e:
            log.exception("chat.endpoint_failed", persona=persona_id)
            yield f"event: error\ndata: {type(e).__name__}: {e}\n\n"

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disables proxy buffering (nginx, etc.)
        },
    )


@app.get("/api/reports/{persona_id}")
async def get_persona_reports(
    persona_id: str,
    limit: int = 5,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Latest N analyst_reports for a persona, reshaped for the Vercel UI.

    Each report's `parsed` JSONB (AnalystReport for stock-pickers,
    RegimeReport for Ray) is unpacked into UI-friendly shape: title,
    body paragraphs, tickers, numerics, what_would_make_me_wrong list.
    """
    _require_webhook_auth(authorization)
    if persona_id not in ("warren", "cathie", "ray", "peter"):
        raise HTTPException(400, f"unknown persona: {persona_id}")
    limit = max(1, min(limit, 20))

    from sqlalchemy import text as _sql

    from tessera_worker.db import session_scope

    rows = []
    with session_scope() as session:
        result = session.execute(
            _sql("""
                SELECT id::text AS id, as_of_date, parsed
                FROM analyst_reports
                WHERE persona_id = :p AND rejected = false
                ORDER BY as_of_date DESC, ts DESC
                LIMIT :n
            """),
            {"p": persona_id, "n": limit},
        ).all()
        for r in result:
            parsed = r.parsed if isinstance(r.parsed, dict) else {}
            rows.append(_reshape_report_row(
                r.id, persona_id, r.as_of_date.isoformat(), parsed,
            ))
    return {"reports": rows}


# Latest BATCH DAY only. v2 persona_batch (default since PR #87) persists
# ONE analyst_reports row per persona per batch carrying the whole book, so
# the current book is simply the freshest row. The MAX(as_of_date) subquery
# (instead of LIMIT 1) also keeps legacy v1 batch days correct — those wrote
# one row per (persona, ticker) cell, and all of that day's rows together
# form the book. What this must NEVER do is span multiple batch days: the
# pre-2026-06-11 LIMIT 20 version unioned up to 20 batches, resurrecting
# tickers that had been dropped from the current book ("ghost positions")
# and averaging cash_target across months.
_PROPOSALS_SQL = """
    SELECT as_of_date, ts, parsed
    FROM analyst_reports
    WHERE persona_id = :p AND rejected = false
      AND as_of_date = (
          SELECT MAX(as_of_date) FROM analyst_reports
          WHERE persona_id = :p AND rejected = false
      )
    ORDER BY ts DESC
"""


@app.get("/api/proposals/{persona_id}")
async def get_persona_proposal(
    persona_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Persona's CURRENT BOOK — the latest batch day's report(s) reshaped
    into a single Proposal-like view. See _PROPOSALS_SQL for why only the
    most recent as_of_date participates, and _aggregate_book for the
    aggregation rules."""
    _require_webhook_auth(authorization)
    if persona_id not in ("warren", "cathie", "ray", "peter"):
        raise HTTPException(400, f"unknown persona: {persona_id}")

    from sqlalchemy import text as _sql

    from tessera_worker.db import session_scope

    with session_scope() as session:
        rows = session.execute(_sql(_PROPOSALS_SQL), {"p": persona_id}).all()

    if not rows:
        return {"personaId": persona_id, "asOf": None, "positions": [],
                "cashWeight": None, "regime": None,
                "horizon": _persona_horizon(persona_id)}

    parsed_rows = [r.parsed if isinstance(r.parsed, dict) else {} for r in rows]
    return _aggregate_book(
        parsed_rows, persona_id, rows[0].as_of_date.isoformat(),
    )


def _aggregate_book(
    parsed_rows: list[dict[str, Any]], persona_id: str, latest_as_of: str,
) -> dict[str, Any]:
    """Collapse one batch day's parsed reports into the UI book shape.

    `parsed_rows` must be ordered newest-first and contain ONLY rows from a
    single batch day (the handler's SQL guarantees this). For v2 that's one
    row; for legacy v1 days it's one row per ticker cell — first occurrence
    of a ticker wins, which under newest-first ordering is the freshest
    write."""
    from tessera_worker.universe import META_BY_TICKER

    positions_by_ticker: dict[str, dict[str, Any]] = {}
    cash_targets: list[float] = []
    regime: dict[str, Any] | None = None

    for parsed in parsed_rows:
        cash = parsed.get("cash_target")
        if cash is not None:
            with contextlib.suppress(TypeError, ValueError):
                cash_targets.append(float(cash))
        if regime is None and parsed.get("regime"):
            regime = parsed["regime"]

        # Stock-picker shape (Warren / Cathie / Peter)
        for p in (parsed.get("proposals") or []):
            ticker = p.get("ticker")
            if not ticker or ticker in positions_by_ticker:
                continue
            meta = META_BY_TICKER.get(ticker)
            positions_by_ticker[ticker] = {
                "ticker": ticker,
                "name": meta.name if meta else ticker,
                "sector": meta.sector if meta else "Unknown",
                "weight": float(p.get("target_weight", 0)),
                "side": p.get("side", "hold"),
                "conviction": float(p.get("conviction", 0)),
                "thesis": (p.get("thesis_md") or "")[:240].strip(),
            }
        # Ray shape (parsed.allocations) — single-row but iterate anyway
        for a in (parsed.get("allocations") or []):
            inst = a.get("instrument")
            if not inst or inst in positions_by_ticker:
                continue
            meta = META_BY_TICKER.get(inst)
            positions_by_ticker[inst] = {
                "ticker": inst,
                "name": meta.name if meta else (a.get("asset_class") or inst),
                "sector": meta.sector if meta else (a.get("asset_class") or "Unknown"),
                "weight": float(a.get("target_weight", 0)),
                "side": "long",
                # RegimeAllocation has no per-slice conviction.
                "conviction": None,
                "thesis": (a.get("thesis_md") or "")[:240].strip(),
            }

    # Cash target — average across the batch's cells (each cell's view
    # of "what fraction of NAV should be cash" varies; averaging is the
    # least-bad summary).
    cash_weight = sum(cash_targets) / len(cash_targets) if cash_targets else 0.0

    positions = sorted(
        positions_by_ticker.values(),
        key=lambda p: -p["weight"],  # heaviest first
    )

    # ─────────────────────────────────────────────────────────────────
    # Conservation-of-NAV safeguard — belt-and-suspenders since v2.
    #
    # v2 persona_batch's construction pass enforces proposals +
    # cash_target = 1.0 via Pydantic before persisting, so for current
    # batches this block is a no-op that only logs if something slipped.
    # It still does real work when the latest batch day predates v2
    # (one row per ticker cell, independently-sized positions): the gap
    # to 1.0 is treated as cash, and over-allocation is scaled down
    # proportionally with cash zeroed. Logged loudly either way so an
    # operator can audit. Ray's RegimeReport allocations are coordinated
    # by construction — always a no-op there.
    # ─────────────────────────────────────────────────────────────────
    sum_positions = sum(p["weight"] for p in positions)
    total = sum_positions + cash_weight
    if abs(total - 1.0) > 0.01:
        if sum_positions > 1.0:
            log.warning("proposals.over_allocation",
                        persona=persona_id,
                        sum_positions=round(sum_positions, 4),
                        cash_reported=round(cash_weight, 4))
            scale = 1.0 / sum_positions
            for p in positions:
                p["weight"] *= scale
            cash_weight = 0.0
        else:
            inferred_cash = max(0.0, 1.0 - sum_positions)
            log.info("proposals.cash_inferred",
                     persona=persona_id,
                     sum_positions=round(sum_positions, 4),
                     cash_reported=round(cash_weight, 4),
                     cash_inferred=round(inferred_cash, 4),
                     gap=round(1.0 - total, 4))
            cash_weight = inferred_cash

    return {
        "personaId": persona_id,
        "asOf": latest_as_of,
        "horizon": _persona_horizon(persona_id),
        "cashWeight": cash_weight,
        "positions": positions,
        "regime": regime,
        # v2 writes one row per batch with a real construction-pass note;
        # take the newest. Legacy v1 days had per-cell notes too noisy to
        # aggregate — first-row-only keeps those harmless.
        "notesToManager": (parsed_rows[0].get("notes_to_manager") or "")
                          if parsed_rows else "",
    }


@app.get("/api/features/{ticker}")
async def get_ticker_features(
    ticker: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Latest ticker_features row, reshaped for the UI's expandable
    position card. Returns numeric values + a snapshot date; the
    frontend handles per-field formatting (% / x / $)."""
    _require_webhook_auth(authorization)
    # Normalize: UI may send lowercase or mixed; universe stores uppercase.
    # Crypto pairs stored as 'SOL/USD'; URL uses 'SOL-USD' (slashes break
    # the route). Equity tickers don't contain '-' so this is safe.
    ticker_u = ticker.upper().replace("-", "/")
    from sqlalchemy import text as _sql

    from tessera_worker.db import session_scope
    from tessera_worker.universe import META_BY_TICKER

    meta = META_BY_TICKER.get(ticker_u)
    if not meta:
        raise HTTPException(404, f"ticker not in universe: {ticker_u}")

    with session_scope() as session:
        row = session.execute(
            _sql("""
                SELECT ts::date AS asof,
                       ret_1d, ret_5d, ret_30d, ret_90d, ret_1y,
                       vol_30d, rsi_14, sma_20, sma_50, volume_z,
                       fcf_yield, peg, market_cap_usd, operating_margin,
                       eps_cagr_3y, debt_to_equity,
                       gross_margin, gross_margin_trend,
                       pe_trailing, pe_forward
                FROM ticker_features
                WHERE ticker = :t
                ORDER BY ts DESC
                LIMIT 1
            """),
            {"t": ticker_u},
        ).mappings().first()

    if not row:
        return {"ticker": ticker_u, "name": meta.name, "sector": meta.sector,
                "asof": None, "features": None}

    def _f(v: Any) -> float | None:
        return float(v) if v is not None else None
    def _i(v: Any) -> int | None:
        return int(v) if v is not None else None

    return {
        "ticker": ticker_u,
        "name": meta.name,
        "sector": meta.sector,
        "asof": row["asof"].isoformat() if row["asof"] else None,
        "features": {
            "ret_1d":             _f(row["ret_1d"]),
            "ret_5d":             _f(row["ret_5d"]),
            "ret_30d":            _f(row["ret_30d"]),
            "ret_90d":            _f(row["ret_90d"]),
            "ret_1y":             _f(row["ret_1y"]),
            "vol_30d":            _f(row["vol_30d"]),
            "rsi_14":             _f(row["rsi_14"]),
            "sma_20":             _f(row["sma_20"]),
            "sma_50":             _f(row["sma_50"]),
            "volume_z":           _f(row["volume_z"]),
            "fcf_yield":          _f(row["fcf_yield"]),
            "peg":                _f(row["peg"]),
            "market_cap_usd":     _i(row["market_cap_usd"]),
            "operating_margin":   _f(row["operating_margin"]),
            "eps_cagr_3y":        _f(row["eps_cagr_3y"]),
            "debt_to_equity":     _f(row["debt_to_equity"]),
            "gross_margin":       _f(row["gross_margin"]),
            "gross_margin_trend": _f(row["gross_margin_trend"]),
            "pe_trailing":        _f(row["pe_trailing"]),
            "pe_forward":         _f(row["pe_forward"]),
        },
    }


@app.get("/api/prices/{ticker}")
async def get_ticker_prices(
    ticker: str,
    range: str = "20y",
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Historical close prices for one ticker, downsampled for chart display.

    Used by the expandable position card on /proposals + the persona
    detail sheet to render a long-horizon price line. We pull from
    ohlcv_1d (TimescaleDB hypertable) and bucket so the wire payload is
    small (~250 points for 20y) regardless of how much history exists.

    Query params:
        range: one of "1y" | "5y" | "10y" | "20y" | "max" (default "20y").
               Drives the SQL window AND the bucket size.

    Response shape:
        {
          "ticker": "V",
          "name":   "Visa Inc.",
          "range":  "20y",
          "points": [{ "date": "2006-03-19", "close": 4.86 }, …],
        }
    """
    _require_webhook_auth(authorization)
    # Crypto pairs are stored as 'SOL/USD' but URLs use 'SOL-USD' (slashes
    # would break the route). Normalize so the universe lookup + SQL query
    # both find the canonical row. Equity tickers don't contain '-' so this
    # is safe: BRK.B uses '.', no ticker in our universe uses dash.
    ticker_u = ticker.upper().replace("-", "/")
    from sqlalchemy import text as _sql

    from tessera_worker.db import session_scope
    from tessera_worker.universe import META_BY_TICKER

    meta = META_BY_TICKER.get(ticker_u)
    if not meta:
        raise HTTPException(404, f"ticker not in universe: {ticker_u}")

    # Range → (lookback_days_or_None, bucket_days).
    # Bucket sizes are tuned to keep payload ~200–300 points: enough to
    # see structure, small enough to stream cheap.
    range_map = {
        "1y":  (365,    1),
        "5y":  (5 * 365,  7),
        "10y": (10 * 365, 14),
        "20y": (20 * 365, 30),
        "max": (None,     30),
    }
    rng = range.lower() if range else "20y"
    if rng not in range_map:
        rng = "20y"
    lookback, bucket = range_map[rng]

    # We bucket via plain `date_trunc` + simple arithmetic instead of
    # Timescale's `time_bucket` to keep the query portable and avoid the
    # `||` operator in a SQL string (clashes with psycopg parameter
    # binding in some paths and was the source of an earlier 500). The
    # bucket interval and lookback days are both server-trusted integers
    # (range_map above), so inlining them is safe.
    if lookback is None:
        where_clause = "ticker = :t"
        params = {"t": ticker_u}
    else:
        where_clause = (
            f"ticker = :t AND ts >= NOW() - INTERVAL '{int(lookback)} days'"
        )
        params = {"t": ticker_u}

    # Bucket every Nth day from the earliest available row. floor((ts -
    # epoch) / bucket_days) * bucket_days yields a deterministic bucket
    # key independent of the data window, so re-querying with a smaller
    # range still aligns to the same bucket boundaries.
    bucket_days = int(bucket)

    # Inner DISTINCT ON: one row per calendar day before bucketing. Mixed-
    # source history can store the same day twice (Alpaca 04:00Z vs Yahoo
    # backfill 00:00Z); migration 006 cleaned the table, this keeps the
    # endpoint correct even if duplicates ever reappear. Preference order
    # matches compute._load_ohlcv (daily-cron sources > backfill).
    with session_scope() as session:
        rows = session.execute(
            _sql(f"""
                SELECT to_timestamp(
                           floor(EXTRACT(EPOCH FROM ts) / ({bucket_days} * 86400))
                           * ({bucket_days} * 86400)
                       )::date                  AS bucket,
                       AVG(close)::float        AS close
                FROM (
                    SELECT DISTINCT ON (ts::date) ts, close
                    FROM ohlcv_1d
                    WHERE {where_clause}
                    ORDER BY ts::date,
                             CASE source
                                 WHEN 'alpaca'   THEN 1
                                 WHEN 'coinbase' THEN 1
                                 WHEN 'yahoo'    THEN 2
                                 ELSE 3
                             END,
                             ts DESC
                ) canonical_day
                GROUP BY bucket
                ORDER BY bucket
            """),
            params,
        ).all()

    points = [
        {"date": r.bucket.isoformat(), "close": float(r.close)}
        for r in rows
        if r.close is not None
    ]

    return {
        "ticker": ticker_u,
        "name":   meta.name,
        "range":  rng,
        "points": points,
    }


def _build_performance_payload(
    persona_id: str,
    points: list[tuple[date, float, bool]],  # (date, total_value, hypothetical) ASC
    sharpe30d: float | None,
    mdd30d: float | None,
) -> dict[str, Any]:
    """Reshape persona_portfolios rows into the UI's equity-curve payload.

    Values are normalized so the FIRST point of the window = 1.0 — the
    chart plots (value − 1) as cumulative %. Each point carries its
    `hypothetical` flag so the frontend can split the line into a dashed
    backfilled segment and a solid live segment (the honesty-labelling
    requirement from migration 007 / the frozen-book decision)."""
    if not points:
        return {"personaId": persona_id, "asOf": None, "series": [],
                "metrics": None}
    base = float(points[0][1])
    series = [
        {"date": d.isoformat(), "value": round(float(v) / base, 6),
         "hypothetical": bool(h)}
        for d, v, h in points
    ]

    def _window_return(n: int) -> float | None:
        if len(points) < 2:
            return None
        window = points[-n:] if len(points) > n else points
        first, last = float(window[0][1]), float(window[-1][1])
        return round(last / first - 1.0, 4) if first > 0 else None

    track_start = next((d for d, _v, h in points if not h), None)
    return {
        "personaId": persona_id,
        "asOf": points[-1][0].isoformat(),
        "series": series,
        "metrics": {
            "totalValue": round(float(points[-1][1]), 2),
            # ~252 trading days ≈ 1y, ~63 ≈ 90d on the equity calendar
            "return1y": _window_return(252),
            "return90d": _window_return(63),
            "sharpe30d": sharpe30d,
            "mdd30d": mdd30d,
            "trackStart": track_start.isoformat() if track_start else None,
        },
    }


@app.get("/api/performance/{persona_id}")
async def get_persona_performance(
    persona_id: str,
    days: int = 400,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Equity curve + headline metrics for one persona's paper track.

    Series = daily persona_portfolios snapshots (hypothetical backfill +
    real track, flagged per point). Metrics: returns computed from the
    curve; sharpe/mdd from the latest persona_performance row (real row
    preferred, hypothetical fallback while the live track is young)."""
    _require_webhook_auth(authorization)
    if persona_id not in ("warren", "cathie", "ray", "peter"):
        raise HTTPException(400, f"unknown persona: {persona_id}")
    days = max(30, min(days, 800))

    from sqlalchemy import text as _sql

    from tessera_worker.db import session_scope

    with session_scope() as session:
        rows = session.execute(
            _sql("""
                SELECT * FROM (
                    SELECT ts::date AS d, total_value, hypothetical
                    FROM persona_portfolios
                    WHERE persona_id = :p
                    ORDER BY ts DESC
                    LIMIT :n
                ) recent ORDER BY d ASC
            """),
            {"p": persona_id, "n": days},
        ).all()
        # Latest row that actually HAS a sharpe: the live track's first
        # days carry NULL (sharpe needs ≥5 observations), so this
        # naturally serves the hypothetical track's trailing stats until
        # the live track matures, then live values win by date.
        perf = session.execute(
            _sql("""
                SELECT sharpe_30d, mdd_30d
                FROM persona_performance
                WHERE persona_id = :p AND sharpe_30d IS NOT NULL
                ORDER BY date DESC
                LIMIT 1
            """),
            {"p": persona_id},
        ).first()

    sharpe = float(perf.sharpe_30d) if perf and perf.sharpe_30d is not None else None
    mdd = float(perf.mdd_30d) if perf and perf.mdd_30d is not None else None
    return _build_performance_payload(
        persona_id,
        [(r.d, float(r.total_value), bool(r.hypothetical)) for r in rows],
        sharpe, mdd,
    )


@app.get("/api/portfolio/{persona_id}")
async def get_persona_portfolio(
    persona_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Latest REAL portfolio snapshot (positions with qty/close/value/
    weight + cash). Hypothetical snapshots are never served here — this
    endpoint answers "what does the persona actually hold on paper"."""
    _require_webhook_auth(authorization)
    if persona_id not in ("warren", "cathie", "ray", "peter"):
        raise HTTPException(400, f"unknown persona: {persona_id}")

    from sqlalchemy import text as _sql

    from tessera_worker.db import session_scope
    from tessera_worker.universe import META_BY_TICKER

    with session_scope() as session:
        row = session.execute(
            _sql("""
                SELECT ts::date AS d, cash, positions, total_value
                FROM persona_portfolios
                WHERE persona_id = :p AND NOT hypothetical
                ORDER BY ts DESC
                LIMIT 1
            """),
            {"p": persona_id},
        ).first()

    if not row:
        return {"personaId": persona_id, "asOf": None, "totalValue": None,
                "cash": None, "cashWeight": None, "positions": []}

    total = float(row.total_value)
    raw = row.positions if isinstance(row.positions, dict) else {}
    positions = []
    for ticker, v in raw.items():
        if not isinstance(v, dict):
            continue
        value = float(v.get("value") or 0.0)
        meta = META_BY_TICKER.get(ticker)
        positions.append({
            "ticker": ticker,
            "name": meta.name if meta else ticker,
            "sector": meta.sector if meta else "Unknown",
            "qty": float(v.get("qty") or 0.0),
            "close": float(v.get("close") or 0.0),
            "value": round(value, 2),
            "weight": round(value / total, 4) if total > 0 else 0.0,
        })
    positions.sort(key=lambda p: -p["weight"])
    cash = float(row.cash)
    return {
        "personaId": persona_id,
        "asOf": row.d.isoformat(),
        "totalValue": round(total, 2),
        "cash": round(cash, 2),
        "cashWeight": round(cash / total, 4) if total > 0 else None,
        "positions": positions,
    }


@app.get("/api/attribution/{persona_id}")
async def get_persona_attribution(
    persona_id: str,
    period: str = "mtd",
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Ticker-level P&L attribution over the paper track.

    period: 'mtd' (default, calendar month-to-date), '7d', '30d'.
    Contributions are fractions of period-start NAV and sum ≈ the
    period's total return. Spans hypothetical + live snapshots
    transparently (the frozen backfill is a constant-qty book)."""
    _require_webhook_auth(authorization)
    if persona_id not in ("warren", "cathie", "ray", "peter"):
        raise HTTPException(400, f"unknown persona: {persona_id}")
    from datetime import date as _date
    from datetime import timedelta as _timedelta

    today = _date.today()
    if period == "7d":
        start = today - _timedelta(days=7)
    elif period == "30d":
        start = today - _timedelta(days=30)
    else:
        period = "mtd"
        start = today.replace(day=1)

    from tessera_worker.db import session_scope
    from tessera_worker.risk.attribution import compute_attribution, load_snapshots
    from tessera_worker.universe import META_BY_TICKER

    with session_scope() as session:
        snapshots = load_snapshots(session, persona_id, start)
    rows = compute_attribution(snapshots)

    if not snapshots:
        return {"personaId": persona_id, "period": period, "start": None,
                "end": None, "totalReturn": None, "rows": []}
    start_nav = snapshots[0].total_value
    end_nav = snapshots[-1].total_value
    return {
        "personaId": persona_id,
        "period": period,
        "start": snapshots[0].day.isoformat(),
        "end": snapshots[-1].day.isoformat(),
        "totalReturn": round(end_nav / start_nav - 1.0, 6) if start_nav > 0 else None,
        "rows": [
            {
                "ticker": a.ticker,
                "name": (META_BY_TICKER[a.ticker].name
                         if a.ticker in META_BY_TICKER else a.ticker),
                "pnl": a.pnl,
                "contribution": a.contribution,
            }
            for a in rows
        ],
    }


def _reshape_report_row(
    row_id: str, persona_id: str, date_iso: str, parsed: dict[str, Any],
) -> dict[str, Any]:
    """Turn a raw analyst_reports row into the {title, body, tickers, …}
    shape the UI's report card expects."""
    # Pick the first proposal/allocation to title the report card.
    first_pos = (parsed.get("proposals") or [None])[0] \
        or (parsed.get("allocations") or [None])[0]
    if first_pos:
        ticker = first_pos.get("ticker") or first_pos.get("instrument") or "?"
        side = first_pos.get("side") or "allocate"
        conv = first_pos.get("conviction")
        # Readable conviction tier rather than the raw 0.55 number.
        # Bins line up with how PMs talk to one another: a "Strong buy"
        # is a top-of-book conviction (≥0.80), "Buy" is a real position
        # (0.65–0.80), "Hold" is keep-but-don't-add (0.50–0.65), and
        # "Watch" is research-only (<0.50). The risk gateway uses the
        # same thresholds when it decides whether to size the slot.
        conv_label = ""
        if isinstance(conv, (int, float)):
            if conv >= 0.80:
                conv_label = "Strong buy"
            elif conv >= 0.65:
                conv_label = "Buy"
            elif conv >= 0.50:
                conv_label = "Hold"
            else:
                conv_label = "Watch"
        # Drop the raw `side` token when we have a conviction label and
        # the side is buy-ish — "buy (Strong buy)" reads redundant since
        # the label already carries the direction. For non-buy sides
        # (trim / sell) the side is the more informative thing to show.
        if conv_label and side in ("buy", "hold", "add"):
            title = f"{persona_id.title()} · {ticker} · {conv_label}"
        else:
            title = f"{persona_id.title()} · {ticker} · {side}"
        thesis_md = first_pos.get("thesis_md") or ""
    else:
        title = f"{persona_id.title()} · {date_iso}"
        thesis_md = parsed.get("notes_to_manager") or ""

    body_paragraphs = [p.strip() for p in (thesis_md or "").split("\n\n") if p.strip()]
    summary = body_paragraphs[0][:240] if body_paragraphs else ""
    if len(summary) >= 240:
        summary = summary.rstrip() + "…"

    tickers: list[str] = []
    # Per-ticker proposal map so the frontend can render related-thesis
    # cards with the SPECIFIC ticker's conviction + sizing reasoning,
    # instead of using the report's global title (which is the first
    # proposal's). In v2 each report carries the whole persona book,
    # so the global title becomes misleading when shown under a sibling
    # ticker's "Related thesis" lookup.
    per_ticker: dict[str, dict[str, Any]] = {}
    for p in (parsed.get("proposals") or []):
        t = p.get("ticker")
        if not t:
            continue
        tickers.append(t)
        per_ticker[t] = {
            "side":          p.get("side") or "buy",
            "conviction":    float(p.get("conviction") or 0),
            "targetWeight":  float(p.get("target_weight") or 0),
            "thesisMd":      (p.get("thesis_md") or "").strip(),
        }
    for a in (parsed.get("allocations") or []):
        inst = a.get("instrument")
        if not inst:
            continue
        tickers.append(inst)
        per_ticker[inst] = {
            "side":          "long",
            "conviction":    0.0,
            "targetWeight":  float(a.get("target_weight") or 0),
            "thesisMd":      (a.get("thesis_md") or "").strip(),
        }

    return {
        "id": row_id,
        "personaId": persona_id,
        "date": date_iso,
        "title": title,
        "tickers": tickers,
        "type": "macro" if persona_id == "ray" else "thesis",
        "summary": summary,
        "body": body_paragraphs,
        "whatWouldMakeMeWrong": (
            (parsed.get("proposals") or [{}])[0].get("what_would_make_me_wrong") or []
            if parsed.get("proposals") else []
        ),
        "cashTarget": parsed.get("cash_target"),
        "notesToManager": parsed.get("notes_to_manager") or "",
        "proposalsByTicker": per_ticker,
    }


def _persona_horizon(persona_id: str) -> str:
    return {
        "warren": "5+ years",
        "cathie": "3–5 years",
        "ray": "Continuous",
        "peter": "2–4 years",
    }.get(persona_id, "—")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("tessera_worker.main:app", host="0.0.0.0", port=8080, reload=False)
