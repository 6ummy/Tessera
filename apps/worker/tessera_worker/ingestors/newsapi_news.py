"""NewsAPI news ingestor — ticker-tagged headlines + bodies.

For each ticker, pulls articles published since `since` (default: last 24h).
Free tier: 100 requests/day, 24h delay on most sources, /everything endpoint
caps at ~5,000 articles per query. Fine for our daily-batch cadence.

Embeddings: left NULL for Phase A. Phase B will backfill via Anthropic-
embedded text or an OSS model (bge-small) — see Risk Register, vector recall.
Storing news without embeddings still enables ticker-based lookup (GIN
index on `tickers` array) for chat-with-analyst context.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import httpx
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential

from tessera_worker.config import get_settings
from tessera_worker.db import session_scope
from tessera_worker.logging import get_logger
from tessera_worker.universe import META_BY_TICKER, by_asset_class

log = get_logger(__name__)

API = "https://newsapi.org/v2/everything"


@dataclass(frozen=True, slots=True)
class IngestResult:
    source: str
    tickers_queried: int
    rows_upserted: int
    requests_made: int
    duration_ms: int


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _fetch(query: str, since_iso: str, page_size: int = 25) -> list[dict]:
    s = get_settings()
    r = httpx.get(
        API,
        params={
            "q": query,
            "from": since_iso,
            "pageSize": page_size,
            "sortBy": "publishedAt",
            "language": "en",
            "apiKey": s.newsapi_api_key,
        },
        timeout=15,
    )
    r.raise_for_status()
    body = r.json()
    if body.get("status") != "ok":
        # NewsAPI returns status=error with message in body — surface it
        raise RuntimeError(f"NewsAPI error: {body.get('code')} {body.get('message')}")
    return body.get("articles", [])


def _build_query(ticker: str) -> str:
    """Combine ticker symbol with company name for better recall.
    NewsAPI plain-text query, double quotes for exact-match company name."""
    meta = META_BY_TICKER.get(ticker)
    if meta and meta.name:
        # Strip parenthetical disambiguators like "Alphabet (A)"
        clean = meta.name.split(" (")[0]
        return f'"{ticker}" OR "{clean}"'
    return ticker


def _row_for(article: dict, ticker: str) -> dict | None:
    ts_raw = article.get("publishedAt")
    if not ts_raw:
        return None
    try:
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    title = (article.get("title") or "").strip()
    if not title:
        return None
    return {
        "id": uuid4(),
        "ts": ts,
        "source": (article.get("source") or {}).get("name", "newsapi"),
        "url": article.get("url"),
        "title": title[:1000],
        "body": (article.get("description") or article.get("content") or "")[:5000],
        "tickers": [ticker],
        "sentiment": None,            # filled later by Phase B
        "raw_gcs_uri": None,          # filled when we wire GCS backups
    }


def _upsert(rows: list[dict]) -> int:
    if not rows:
        return 0
    # No natural unique key on NewsAPI articles, but (title, ticker, ts day) is
    # effectively unique. We dedupe in-process before insert, then rely on the
    # GIN index for query. For simple INSERT we don't UPSERT — accept some
    # duplicates across days and clean up later if needed.
    sql = text("""
        INSERT INTO news (id, ts, source, url, title, body, tickers,
                          sentiment, raw_gcs_uri, fetched_at)
        VALUES (:id, :ts, :source, :url, :title, :body, :tickers, :sentiment, :raw_gcs_uri, NOW())
    """)
    chunk = 200
    written = 0
    with session_scope() as session:
        for i in range(0, len(rows), chunk):
            session.execute(sql, rows[i : i + chunk])
            written += len(rows[i : i + chunk])
    return written


def ingest(
    tickers: Iterable[str] | None = None,
    since: date | None = None,
    page_size: int = 25,
) -> IngestResult:
    """Pull news for each ticker. Default universe: equities. Default since: 24h ago."""
    if tickers is None:
        tickers = [t.ticker for t in by_asset_class("equity")]
    tickers = sorted(set(tickers))
    if since is None:
        since = (datetime.now(UTC) - timedelta(hours=24)).date()
    since_iso = since.isoformat()
    started = datetime.now()

    log.info("newsapi.start", n_tickers=len(tickers), since=since_iso)

    requests_made = 0
    rows: list[dict] = []
    seen_titles: set[tuple[str, str]] = set()   # (ticker, normalized title)
    for ticker in tickers:
        try:
            articles = _fetch(_build_query(ticker), since_iso, page_size=page_size)
            requests_made += 1
        except Exception as e:
            log.warning("newsapi.fetch_skip", ticker=ticker, err=str(e)[:200])
            continue
        for a in articles:
            row = _row_for(a, ticker)
            if not row:
                continue
            key = (ticker, row["title"].lower().strip())
            if key in seen_titles:
                continue
            seen_titles.add(key)
            rows.append(row)

    inserted = _upsert(rows)
    duration_ms = int((datetime.now() - started).total_seconds() * 1000)
    result = IngestResult(
        source="newsapi_news",
        tickers_queried=len(tickers),
        rows_upserted=inserted,
        requests_made=requests_made,
        duration_ms=duration_ms,
    )
    log.info("newsapi.done", rows=inserted, requests=requests_made, ms=duration_ms)
    return result
