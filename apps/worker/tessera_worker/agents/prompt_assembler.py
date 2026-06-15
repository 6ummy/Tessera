"""Assemble persona thesis prompts from Neon data + personalities.md spec.

Production version of demo_warren_aapl.py: fetch inputs, render XML-ish blocks,
merge with optional memory recall, return system (persona spec) + user message.
"""

from __future__ import annotations

import hashlib
from contextlib import suppress
from dataclasses import dataclass
from datetime import date, timedelta
from textwrap import shorten
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from tessera_worker.agents.persona_loader import PersonaId, get_persona_spec
from tessera_worker.db import session_scope
from tessera_worker.logging import get_logger

log = get_logger(__name__)

# Per-persona macro base + ticker overlay (see demo_macro_sensitivity.py).
MACRO_BY_PERSONA: dict[str, list[str] | str] = {
    "warren": ["DGS10", "T10YIE", "BAMLH0A0HYM2", "VIXCLS"],
    "cathie": ["DGS10", "VIXCLS", "BAMLC0A0CM"],
    "ray": "ALL",
    "peter": ["DGS10", "T10YIE", "BAMLH0A0HYM2", "UNRATE"],
}

TICKER_MACRO_OVERLAY: dict[str, list[str]] = {
    "AAPL": ["VIXCLS", "BAMLH0A0HYM2", "DEXCHUS"],
    "AMZN": ["VIXCLS", "BAMLH0A0HYM2", "BAMLC0A0CM"],
    "ASML": ["VIXCLS", "DEXMXUS", "BAMLH0A0HYM2"],
    "GOOGL": ["VIXCLS", "BAMLH0A0HYM2", "DEXKOUS"],
    "META": ["BAMLH0A0HYM2", "VIXCLS", "BAMLC0A0CM"],
    "MSFT": ["BAMLH0A0HYM2", "BAMLC0A0CM", "VIXCLS"],
    "NVDA": ["VIXCLS", "BAMLH0A0HYM2", "BAMLC0A0CM"],
    "TSLA": ["VIXCLS", "BAMLH0A0HYM2", "BAMLC0A0CM"],
    "TSM": ["VIXCLS", "BAMLH0A0HYM2", "DEXJPUS"],
    "XOM": ["DCOILWTICO", "DCOILBRENTEU", "DJFUELUSGULF"],
    "JPM": ["VIXCLS", "BAMLH0A0HYM2", "T10Y2Y"],
    "NEE": ["DHHNGSP", "DGS10", "UNRATE"],
    "HD": ["DCOILWTICO", "DGS10", "DJFUELUSGULF"],
    "JNJ": ["DGS10", "T10YIE", "DGS30"],
    "PG": ["T10YIE", "DGS10", "DGS2"],
    "WMT": ["DEXMXUS", "DGS10", "VIXCLS"],
}

RENDER_RULES: dict[PersonaId, dict[str, Any]] = {
    "warren": {
        "news_limit": 10,
        "news_lookback_days": 7,
        "include_filing": True,
        "include_price_history": True,
        "include_financials_trend": True,
    },
    "cathie": {
        "news_limit": 12,
        "news_lookback_days": 7,
        "include_filing": False,
        "include_price_history": True,
        "include_financials_trend": True,
    },
    "ray": {
        "news_limit": 0,
        "news_lookback_days": 7,
        "include_filing": False,
        "include_price_history": False,
        "include_financials_trend": False,
    },
    "peter": {
        "news_limit": 8,
        "news_lookback_days": 7,
        "include_filing": True,
        "include_price_history": True,
        "include_financials_trend": True,
    },
}

SERIES_FORMATTERS: dict[str, tuple[str, str]] = {
    "DGS2": ("2Y yield", "{:.2f}%"),
    "DGS10": ("10Y yield", "{:.2f}%"),
    "DGS30": ("30Y yield", "{:.2f}%"),
    "T10Y2Y": ("2s10s spread", "{:.2f}%"),
    "T10YIE": ("10Y breakeven", "{:.2f}%"),
    "T5YIFR": ("5y5y fwd infl", "{:.2f}%"),
    "CPIAUCSL": ("CPI level", "{:.1f}"),
    "PCEPILFE": ("Core PCE level", "{:.2f}"),
    "UNRATE": ("Unemployment", "{:.2f}%"),
    "PAYEMS": ("Nonfarm payrolls", "{:.0f}K"),
    "ICSA": ("Init claims", "{:.0f}K"),
    "INDPRO": ("Industrial prod", "{:.1f}"),
    "M2SL": ("M2", "${:.0f}B"),
    "WALCL": ("Fed BS", "${:.0f}M"),
    "DTWEXBGS": ("USD broad", "{:.2f}"),
    "VIXCLS": ("VIX", "{:.1f}"),
    "BAMLH0A0HYM2": ("HY OAS", "{:.2f}%"),
    "BAMLC0A0CM": ("IG OAS", "{:.2f}%"),
    "DEXUSEU": ("USD/EUR", "{:.4f}"),
    "DEXJPUS": ("JPY/USD", "{:.2f}"),
    "DEXKOUS": ("KRW/USD", "{:.2f}"),
    "DEXCAUS": ("CAD/USD", "{:.4f}"),
    "DEXSZUS": ("CHF/USD", "{:.4f}"),
    "DEXCHUS": ("USD/CNY", "{:.2f}"),
    "DEXUSUK": ("USD/GBP", "{:.4f}"),
    "DEXMXUS": ("MXN/USD", "{:.2f}"),
    "DEXINUS": ("INR/USD", "{:.2f}"),
    "DCOILWTICO": ("WTI", "${:.1f}/bbl"),
    "DCOILBRENTEU": ("Brent", "${:.1f}/bbl"),
    "DHHNGSP": ("NatGas (HH)", "${:.2f}/MMBtu"),
    "DJFUELUSGULF": ("Jet fuel", "${:.3f}/gal"),
    "PCOPPUSDM": ("Copper", "${:.0f}/MT"),
    "PWHEAMTUSDM": ("Wheat", "${:.0f}/MT"),
}

SPARKLINE_CHARS = "▁▂▃▄▅▆▇█"


@dataclass(frozen=True)
class AssembledPrompt:
    persona_id: PersonaId
    ticker: str
    as_of: date
    system_prompt: str
    user_message: str
    news_ids: frozenset[str]
    inputs_hash: str


def macros_for(persona: PersonaId, ticker: str) -> list[str]:
    base = MACRO_BY_PERSONA.get(persona, [])
    if base == "ALL":
        return ["__ALL__"]
    overlay = TICKER_MACRO_OVERLAY.get(ticker, [])
    seen: set[str] = set()
    out: list[str] = []
    for s in list(base) + list(overlay):
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def fetch_inputs(
    session: Session,
    persona: PersonaId,
    ticker: str,
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Pull DB blocks for one (persona, ticker) pair as of `as_of` (default
    today). Backtest replay relies on this — every query is upper-bounded
    by `as_of` so no future data leaks into the prompt.
    """
    rules = RENDER_RULES[persona]
    cutoff = as_of or date.today()
    since = cutoff - timedelta(days=rules["news_lookback_days"])
    out: dict[str, Any] = {}

    feat = session.execute(
        text("""
            SELECT ts, ret_1d, ret_5d, ret_30d, ret_90d, ret_1y,
                   vol_30d, rsi_14, sma_20, sma_50, volume_z,
                   fcf_yield, peg, market_cap_usd, operating_margin,
                   eps_cagr_3y, debt_to_equity, gross_margin, gross_margin_trend,
                   gross_margin_qtr_yoy_chg
            FROM ticker_features WHERE ticker = :t AND ts <= :cutoff
            ORDER BY ts DESC LIMIT 1
        """),
        {"t": ticker, "cutoff": cutoff},
    ).mappings().first()
    out["features"] = dict(feat) if feat else None

    all_prices = session.execute(
        text("""
            SELECT DISTINCT ON (ts::date) ts::date AS d, close, source
            FROM ohlcv_1d
            WHERE ticker = :t AND ts::date <= :cutoff
            ORDER BY ts::date,
                     CASE source WHEN 'yahoo' THEN 1
                                 WHEN 'alpaca' THEN 2
                                 WHEN 'coinbase' THEN 3
                                 ELSE 9 END
        """),
        {"t": ticker, "cutoff": cutoff},
    ).all()
    out["prices_full"] = [(p.d, float(p.close)) for p in all_prices]

    funds: dict[str, list[dict[str, Any]]] = {}
    for ft in ("income", "balance", "cash_flow"):
        annual_rows = session.execute(
            text("""
                SELECT period_end, payload FROM fundamentals
                WHERE ticker = :t AND filing_type = :ft
                  AND period_end <= :cutoff
                  AND (payload ->> 'form' = '10-K' OR payload ->> 'fp' = 'FY')
                ORDER BY period_end DESC LIMIT 5
            """),
            {"t": ticker, "ft": ft, "cutoff": cutoff},
        ).mappings().all()
        funds[ft] = [dict(r) for r in annual_rows]
    out["fundamentals_annual"] = funds

    funds_latest: dict[str, dict[str, Any] | None] = {}
    for ft in ("income", "balance", "cash_flow"):
        row = session.execute(
            text("""
                SELECT period_end, payload FROM fundamentals
                WHERE ticker = :t AND filing_type = :ft AND period_end <= :cutoff
                ORDER BY period_end DESC LIMIT 1
            """),
            {"t": ticker, "ft": ft, "cutoff": cutoff},
        ).mappings().first()
        funds_latest[ft] = dict(row) if row else None
    out["fundamentals"] = funds_latest

    wanted = macros_for(persona, ticker)
    if wanted == ["__ALL__"]:
        macros = session.execute(
            text("""
                SELECT DISTINCT ON (series_id) series_id, value, ts
                FROM macro_series WHERE ts <= :cutoff
                ORDER BY series_id, ts DESC
            """),
            {"cutoff": cutoff},
        ).all()
    else:
        macros = session.execute(
            text("""
                SELECT DISTINCT ON (series_id) series_id, value, ts
                FROM macro_series
                WHERE series_id = ANY(:ids) AND ts <= :cutoff
                ORDER BY series_id, ts DESC
            """),
            {"ids": wanted, "cutoff": cutoff},
        ).all()
    out["macros"] = {r.series_id: float(r.value) for r in macros}

    news_limit = rules["news_limit"]
    if news_limit > 0:
        news = session.execute(
            text("""
                SELECT id, ts, source, title FROM news
                WHERE :t = ANY(tickers) AND ts >= :since AND ts <= :cutoff
                ORDER BY ts DESC LIMIT :lim
            """),
            {"t": ticker, "since": since, "cutoff": cutoff, "lim": news_limit},
        ).all()
        out["news"] = [
            {"id": str(n.id), "ts": n.ts, "source": n.source, "title": n.title}
            for n in news
        ]
    else:
        out["news"] = []

    if rules["include_filing"]:
        filing = session.execute(
            text("""
                SELECT filing_type, filing_date, period_end, text_summary, raw_gcs_uri
                FROM filings
                WHERE ticker = :t AND filing_type = '10-K' AND filing_date <= :cutoff
                ORDER BY filing_date DESC LIMIT 1
            """),
            {"t": ticker, "cutoff": cutoff},
        ).mappings().first()
        out["filing"] = dict(filing) if filing else None
    else:
        out["filing"] = None

    # Build a similarity query from the freshest signals — news headlines
    # + a short feature line — so the embedding picks up the current
    # narrative (earnings event, regulatory issue, etc.) and surfaces
    # analogous past theses. Falls back to recency-only when Voyage is
    # unconfigured or the embedding call fails.
    query_seeds: list[str] = []
    for n in (out.get("news") or [])[:3]:
        title = n.get("title") if isinstance(n, dict) else None
        if title:
            query_seeds.append(str(title))
    if out.get("features"):
        # A few highest-signal numbers, formatted compactly. The valuation
        # and quality features are what persona memory most often turns on.
        feat = out["features"]
        for k in (
            "fcf_yield",
            "peg",
            "eps_cagr_3y",
            "debt_to_equity",
            "gross_margin",
            "rsi_14",
            "vol_30d",
        ):
            v = feat.get(k) if isinstance(feat, dict) else None
            if v is not None:
                query_seeds.append(f"{k}={v}")
    query_text = " | ".join(query_seeds) if query_seeds else f"{persona} {ticker}"

    out["memory"] = fetch_memory_recall(
        session, persona, ticker, query_text=query_text, as_of=as_of,
    )
    return out


def fetch_memory_recall(
    session: Session,
    persona: PersonaId,
    ticker: str,
    limit: int = 3,
    *,
    query_text: str | None = None,
    as_of: date | None = None,
) -> str:
    """Recall up to `limit` prior thesis snippets for this (persona, ticker).

    Two strategies, picked at runtime:

      1. **Embedding similarity** — preferred. If a Voyage embedding can
         be produced for `query_text` (the current feature snapshot or
         seed prompt), rows are ordered by cosine distance to that vector
         against rows that have embeddings populated. This surfaces
         analogues from history rather than just the most recent reports.

      2. **Recency** — fallback. Triggers when:
           - no `query_text` provided,
           - Voyage key blank / library missing / embedding call failed,
           - no rows have embeddings yet (clean DB).

    Cross-ticker note: similarity restricted to same (persona, ticker)
    for now. Cross-ticker analogy retrieval is a Phase C task — it
    requires careful citation discipline so the LLM doesn't quote a
    different stock's thesis.
    """
    rows = _fetch_by_similarity(session, persona, ticker, limit, query_text, as_of) \
        or _fetch_by_recency(session, persona, ticker, limit, as_of)
    if not rows:
        return ""
    tags = [getattr(r, "_recall_tag", "recency") for r in rows]
    # The strategy is ALSO logged (2026-06-12): the sim= tag used to live
    # only inside the prompt text, which made "check the logs for sim="
    # unverifiable — and even the prompt tag was silently broken (see
    # _fetch_by_similarity). This line is now the observable signal.
    log.info("memory_recall.strategy", persona=persona, ticker=ticker,
             n=len(rows),
             strategy="similarity" if tags[0].startswith("sim=") else "recency",
             tags=tags)
    lines = [f'<memory count="{len(rows)}">']
    for r, tag in zip(rows, tags, strict=True):
        snippet = shorten(r.thesis_md or "", width=400, placeholder="...")
        lines.append(f"  [{r.ts.date()} · {tag}] {snippet}")
    lines.append("</memory>")
    return "\n".join(lines)


def _fetch_by_similarity(
    session: Session, persona: PersonaId, ticker: str, limit: int,
    query_text: str | None, as_of: date | None,
) -> list[Any]:
    """Try Voyage embedding + pgvector cosine search. Empty list on any miss.

    `as_of` upper-bounds ts — backtest replay must not see theses from
    after the replay date.
    """
    if not query_text:
        return []
    from tessera_worker.agents.embeddings import embed_query, to_pgvector_literal
    vec = embed_query(query_text)
    if vec is None:
        return []
    cutoff_clause = "AND ts::date <= :cutoff" if as_of else ""
    params: dict[str, Any] = {
        "p": persona, "t": ticker, "n": limit,
        "q": to_pgvector_literal(vec),
    }
    if as_of:
        params["cutoff"] = as_of
    rows = session.execute(
        text(f"""
            SELECT thesis_md, ts,
                   (embedding <=> CAST(:q AS vector)) AS distance
            FROM persona_memory
            WHERE persona_id = :p AND ticker = :t
              AND embedding IS NOT NULL
              {cutoff_clause}
            ORDER BY embedding <=> CAST(:q AS vector)
            LIMIT :n
        """),
        params,
    ).all()
    # SQLAlchemy 2.0 Rows are IMMUTABLE — the old code set `_recall_tag`
    # on them under suppress(AttributeError), which silently no-op'd, so
    # every recall rendered as "recency" even when this similarity path
    # produced it (found 2026-06-12; distances were a healthy 0.37–0.60
    # the whole time). Return lightweight objects that can carry the tag.
    from types import SimpleNamespace
    return [
        SimpleNamespace(
            thesis_md=r.thesis_md,
            ts=r.ts,
            _recall_tag=f"sim={float(r.distance):.3f}",
        )
        for r in rows
    ]


def _fetch_by_recency(
    session: Session, persona: PersonaId, ticker: str, limit: int,
    as_of: date | None,
) -> list[Any]:
    cutoff_clause = "AND ts::date <= :cutoff" if as_of else ""
    params: dict[str, Any] = {"p": persona, "t": ticker, "n": limit}
    if as_of:
        params["cutoff"] = as_of
    rows = session.execute(
        text(f"""
            SELECT thesis_md, ts FROM persona_memory
            WHERE persona_id = :p AND ticker = :t
              {cutoff_clause}
            ORDER BY ts DESC LIMIT :n
        """),
        params,
    ).all()
    for r in rows:
        with suppress(AttributeError, TypeError):
            r._recall_tag = "recency"
    return list(rows)


def _fmt_money(v: Any) -> str:
    if v is None or v == "":
        return "n/a"
    try:
        return f"${float(v) / 1e9:.1f}B"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_pct(v: Any, *, signed: bool = False) -> str:
    if v is None or v == "":
        return "n/a"
    try:
        return f"{float(v):+.2%}" if signed else f"{float(v):.2%}"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_num(v: Any, digits: int = 2, *, signed: bool = False) -> str:
    if v is None or v == "":
        return "n/a"
    try:
        return f"{float(v):+.{digits}f}" if signed else f"{float(v):.{digits}f}"
    except (TypeError, ValueError):
        return "n/a"


def render_features(f: dict[str, Any] | None) -> str:
    if not f:
        return "<features>(no data)</features>"
    return (
        "<features>\n"
        f"  asof={f['ts']}\n"
        f"  returns:  1d={_fmt_pct(f.get('ret_1d'), signed=True)}  "
        f"5d={_fmt_pct(f.get('ret_5d'), signed=True)}  "
        f"30d={_fmt_pct(f.get('ret_30d'), signed=True)}  "
        f"90d={_fmt_pct(f.get('ret_90d'), signed=True)}  "
        f"1y={_fmt_pct(f.get('ret_1y'), signed=True)}\n"
        f"  vol_30d={_fmt_pct(f.get('vol_30d'))}  RSI14={_fmt_num(f.get('rsi_14'), 0)}  "
        f"SMA20=${_fmt_num(f.get('sma_20'))}  SMA50=${_fmt_num(f.get('sma_50'))}\n"
        f"  volume_z={_fmt_num(f.get('volume_z'), signed=True)}\n"
        f"  valuation: fcf_yield={_fmt_pct(f.get('fcf_yield'))}  PEG={_fmt_num(f.get('peg'))}  "
        f"mcap={_fmt_money(f.get('market_cap_usd'))}\n"
        f"  quality: eps_cagr_3y={_fmt_pct(f.get('eps_cagr_3y'))}  "
        f"debt_to_equity={_fmt_num(f.get('debt_to_equity'))}  "
        f"gross_margin={_fmt_pct(f.get('gross_margin'))}  "
        f"gross_margin_trend={_fmt_pct(f.get('gross_margin_trend'), signed=True)}  "
        f"gross_margin_qtr_yoy={_fmt_pct(f.get('gross_margin_qtr_yoy_chg'), signed=True)}  "
        f"operating_margin={_fmt_pct(f.get('operating_margin'))}\n"
        "</features>"
    )


def _sparkline(values: list[float], width: int = 40) -> str:
    if not values:
        return "(empty)"
    if len(values) > width:
        bucket = len(values) / width
        sampled: list[float] = []
        for i in range(width):
            chunk = values[int(i * bucket) : int((i + 1) * bucket)]
            if chunk:
                sampled.append(sum(chunk) / len(chunk))
        values = sampled
    vmin, vmax = min(values), max(values)
    if vmax == vmin:
        return SPARKLINE_CHARS[0] * len(values)
    step = (vmax - vmin) / (len(SPARKLINE_CHARS) - 1)
    return "".join(
        SPARKLINE_CHARS[min(int((v - vmin) / step), 7)] for v in values
    )


def render_price_history(prices_full: list[tuple[Any, ...]]) -> str:
    if not prices_full:
        return "<price_history>(no data)</price_history>"
    closes = [p[1] for p in prices_full]
    first_dt, last_dt = prices_full[0][0], prices_full[-1][0]
    spark = _sparkline(closes, width=50)
    years = (last_dt - first_dt).days / 365.25
    total_ret = (closes[-1] / closes[0] - 1) * 100
    peak = max(closes)
    pct_off_ath = (closes[-1] / peak - 1) * 100 if peak > 0 else 0
    worst_dd = 0.0
    running_peak = closes[0]
    for c in closes:
        if c > running_peak:
            running_peak = c
        dd = (c / running_peak - 1) * 100
        if dd < worst_dd:
            worst_dd = dd
    return (
        f'<price_history span="{first_dt} to {last_dt}" years="{years:.1f}">\n'
        f"  {spark}\n"
        f"  start=${closes[0]:.2f}  end=${closes[-1]:.2f}  total_return={total_ret:+.0f}%\n"
        f"  all-time-high=${peak:.2f}  current_vs_ATH={pct_off_ath:+.0f}%\n"
        f"  worst_drawdown_in_window={worst_dd:+.0f}%\n"
        "</price_history>"
    )


def render_fundamentals(funds: dict[str, Any]) -> str:
    if not funds or not any(funds.values()):
        return "<financials>(no data)</financials>"
    inc = (funds.get("income") or {}).get("payload") or {}
    bs = (funds.get("balance") or {}).get("payload") or {}
    cf = (funds.get("cash_flow") or {}).get("payload") or {}
    period = (funds.get("income") or funds.get("cash_flow") or {}).get("period_end")
    return (
        f'<financials period="{period}">\n'
        f"  Revenue:    {_fmt_money(inc.get('revenue'))}\n"
        f"  Op income:  {_fmt_money(inc.get('operatingIncome'))}\n"
        f"  Net income: {_fmt_money(inc.get('netIncome'))}\n"
        f"  Free CF:    {_fmt_money(cf.get('freeCashFlow'))}\n"
        f"  Op cash flow:{_fmt_money(cf.get('operatingCashFlow'))}\n"
        f"  Long-term debt: {_fmt_money(bs.get('longTermDebt'))}\n"
        f"  Cash + ST inv: {_fmt_money(bs.get('cashAndShortTermInvestments'))}\n"
        f"  Shares (weighted): {inc.get('weightedAverageShsOut', 'n/a')}\n"
        "</financials>"
    )


def render_fundamentals_trend(funds_annual: dict[str, Any]) -> str:
    if not funds_annual:
        return "<financials_trend>(no annual data)</financials_trend>"
    inc_rows = funds_annual.get("income", [])
    cf_rows = funds_annual.get("cash_flow", [])
    bs_rows = funds_annual.get("balance", [])
    if not inc_rows and not cf_rows:
        return "<financials_trend>(no annual data)</financials_trend>"

    by_period: dict[Any, dict[str, Any]] = {}
    for row in inc_rows:
        p = row["period_end"]
        by_period.setdefault(p, {})["inc"] = row["payload"]
    for row in cf_rows:
        p = row["period_end"]
        by_period.setdefault(p, {})["cf"] = row["payload"]
    for row in bs_rows:
        p = row["period_end"]
        by_period.setdefault(p, {})["bs"] = row["payload"]
    periods = sorted(by_period.keys(), reverse=True)[:5]

    def fmt(payload_block: dict[str, Any] | None, key: str) -> str:
        if not payload_block:
            return "n/a"
        v = payload_block.get(key)
        if v is None:
            return "n/a"
        try:
            return f"${float(v) / 1e9:.1f}B"
        except (TypeError, ValueError):
            return "n/a"

    lines = ['<financials_trend rows="5 most recent annual filings">']
    lines.append(
        f"  {'period':<12}  {'revenue':>10}  {'op_inc':>10}  "
        f"{'net_inc':>10}  {'FCF':>10}  {'lt_debt':>10}"
    )
    for p in periods:
        b = by_period[p]
        lines.append(
            f"  {str(p):<12}  "
            f"{fmt(b.get('inc'), 'revenue'):>10}  "
            f"{fmt(b.get('inc'), 'operatingIncome'):>10}  "
            f"{fmt(b.get('inc'), 'netIncome'):>10}  "
            f"{fmt(b.get('cf'), 'freeCashFlow'):>10}  "
            f"{fmt(b.get('bs'), 'longTermDebt'):>10}"
        )
    try:
        first_rev = float(by_period[periods[-1]]["inc"]["revenue"])
        last_rev = float(by_period[periods[0]]["inc"]["revenue"])
        years = (periods[0] - periods[-1]).days / 365.25
        if years > 0 and first_rev > 0:
            cagr = (last_rev / first_rev) ** (1 / years) - 1
            lines.append(f"  -> revenue CAGR over {years:.1f}yr: {cagr * 100:+.1f}%/yr")
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        pass
    lines.append("</financials_trend>")
    return "\n".join(lines)


def render_macros(m: dict[str, Any]) -> str:
    if not m:
        return "<context>(no macro data)</context>"
    lines = []
    for series_id, value in m.items():
        label, fmt = SERIES_FORMATTERS.get(series_id, (series_id, "{:.4f}"))
        try:
            v_str = fmt.format(float(value))
        except (TypeError, ValueError):
            v_str = str(value)
        lines.append(f"{label}: {v_str}")
    return f"<context count={len(lines)}>\n  " + "\n  ".join(lines) + "\n</context>"


def render_news(items: list[dict[str, Any]]) -> str:
    if not items:
        return "<news count=0>(none in window)</news>"
    lines = [f"<news count={len(items)}>"]
    for n in items:
        title = shorten(n["title"], width=90, placeholder="...")
        short_id = n["id"].replace("-", "")[:8]
        lines.append(f"  [n_{short_id}] {n['ts'].date()} [{n['source']}] {title}")
    lines.append("</news>")
    return "\n".join(lines)


def news_ids_from_items(items: list[dict[str, Any]]) -> frozenset[str]:
    return frozenset(n["id"] for n in items)


def render_filing(f: dict[str, Any] | None) -> str:
    if not f:
        return "<filing>(no 10-K available)</filing>"
    excerpt = shorten(f["text_summary"] or "", width=800, placeholder="...")
    return (
        f'<filing form="{f["filing_type"]}" filed="{f["filing_date"]}" '
        f'period_end="{f["period_end"]}" gcs="{f["raw_gcs_uri"]}">\n'
        f"  (first 800 chars; full text in GCS)\n"
        f"  {excerpt}\n"
        "</filing>"
    )


def build_user_message(
    persona: PersonaId,
    ticker: str,
    blocks: dict[str, Any],
) -> str:
    rules = RENDER_RULES[persona]
    parts = [
        f"Today's analysis target: {ticker}",
        render_features(blocks["features"]),
    ]
    if rules["include_price_history"]:
        parts.append(render_price_history(blocks["prices_full"]))
    parts.append(render_fundamentals(blocks["fundamentals"]))
    if rules["include_financials_trend"]:
        parts.append(render_fundamentals_trend(blocks["fundamentals_annual"]))
    parts.append(render_macros(blocks["macros"]))
    if blocks.get("memory"):
        parts.append(blocks["memory"])
    if rules["news_limit"] > 0:
        parts.append(render_news(blocks["news"]))
    if rules["include_filing"]:
        parts.append(render_filing(blocks["filing"]))
    if persona == "ray":
        # Ray is an allocator, not a stock picker. Output RegimeReport
        # (regime probabilities + asset-class ETF allocations), not
        # AnalystReport. Ticker passed in is ignored — Ray always writes
        # the same portfolio-level read.
        parts.append(
            "You are evaluating the macro regime today, not a single ticker.\n"
            "Output JSON matching the RegimeReport schema:\n"
            "  persona_id: \"ray\"\n"
            "  as_of: \"YYYY-MM-DD\"\n"
            "  regime: {goldilocks_prob, reflation_prob, stagflation_prob, "
            "deflation_prob, delta_from_last_week_md}  ← four probs must sum to 1.0\n"
            "  allocations: [{asset_class, instrument, target_weight, thesis_md}, ...]\n"
            "    - allocate to asset-class ETFs only: VTI (US equities), "
            "VXUS (intl equities), IEF (7-10y treasuries), TLT (long treasuries), "
            "TIP (TIPS), GLD (gold), DBC (broad commodities), QQQ (US tech)\n"
            "    - target_weight 0.0 to 0.40 per slice; allocations + cash_target ≤ 1.0\n"
            "    - 5-8 allocations typical; do NOT pick individual stocks\n"
            "  cash_target: 0.0 to 1.0\n"
            "  notes_to_manager: one sentence on the dominant regime call"
        )
    else:
        parts.append(
            "Write today's thesis on the target ticker. Output JSON matching the "
            "AnalystReport schema (persona_id, as_of, proposals, cash_target, "
            "notes_to_manager). Cite news using the short identifier shown in the "
            "news block (e.g. \"n_b7a434db\") — the runner resolves these to full "
            "UUIDs automatically."
        )
    return "\n\n".join(parts)


def compute_inputs_hash(user_message: str) -> str:
    return hashlib.sha256(user_message.encode("utf-8")).hexdigest()


def assemble_prompt(
    persona: PersonaId,
    ticker: str,
    *,
    as_of: date | None = None,
    session: Session | None = None,
) -> AssembledPrompt:
    """Build system (persona spec) + user (data blocks) for one thesis call."""
    as_of = as_of or date.today()
    system_prompt = get_persona_spec(persona)

    def _build(sess: Session) -> AssembledPrompt:
        blocks = fetch_inputs(sess, persona, ticker, as_of=as_of)
        user_message = build_user_message(persona, ticker, blocks)
        news_ids = news_ids_from_items(blocks["news"])
        return AssembledPrompt(
            persona_id=persona,
            ticker=ticker,
            as_of=as_of,
            system_prompt=system_prompt,
            user_message=user_message,
            news_ids=news_ids,
            inputs_hash=compute_inputs_hash(user_message),
        )

    if session is not None:
        return _build(session)
    with session_scope() as sess:
        return _build(sess)
