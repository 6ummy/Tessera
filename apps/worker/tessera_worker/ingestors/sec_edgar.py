"""SEC EDGAR filings ingestor.

Pulls recent 10-K + 10-Q filings for the equity universe. Two-stage:
  1) ticker -> CIK via SEC's company_tickers.json (small, cached on disk
     in module-level dict per process)
  2) per ticker, GET submissions JSON, walk recent filings, download
     the primary doc, extract a body-text excerpt, upload raw HTML to
     GCS, upsert headers + excerpt into the filings table.

SEC requirements:
  - User-Agent header MUST include contact info; non-conformant requests
    get 403. Set SEC_USER_AGENT in env (e.g. "Tessera Pilot jshin0407@gmail.com").
  - 10 req/sec rate cap. We sleep 0.12s between requests = ~8 req/sec.
  - No API key, free, unmetered.

We skip 8-K (too noisy for fundamentals-driven personas; revisit if Ray's
macro lens ever wants event-study). XBRL extraction is Phase C+.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable

import httpx
from bs4 import BeautifulSoup
from google.cloud import storage
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential

from tessera_worker.config import get_settings
from tessera_worker.db import session_scope
from tessera_worker.logging import get_logger

log = get_logger(__name__)

# ── SEC endpoints ─────────────────────────────────────────────────────
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVES_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{primary}"
)

# ── Defaults ──────────────────────────────────────────────────────────
DEFAULT_FORMS: frozenset[str] = frozenset({"10-K", "10-Q"})
# Per ticker, keep up to this many of each form. Tuned for ~1.5 yrs context.
DEFAULT_PER_FORM_LIMIT = {"10-K": 2, "10-Q": 4}
# Body text excerpt size (chars) stored inline in text_summary.
EXCERPT_CHARS = 8000
# Conservative throttle: 10 req/sec is SEC's cap; we leave headroom.
THROTTLE_S = 0.12

# Module-level CIK cache (one fetch per process).
_CIK_CACHE: dict[str, int] = {}


@dataclass(frozen=True, slots=True)
class IngestResult:
    source: str
    tickers_processed: int
    filings_upserted: int
    bytes_uploaded: int
    duration_ms: int
    tickers_missing_cik: list[str] = field(default_factory=list)


def _client() -> httpx.Client:
    """Build an httpx client with the SEC-required User-Agent."""
    ua = get_settings().sec_user_agent
    if not ua:
        raise RuntimeError(
            "SEC_USER_AGENT is required (e.g. 'Tessera Pilot you@example.com'). "
            "SEC rejects requests without contact info in User-Agent."
        )
    return httpx.Client(
        headers={
            "User-Agent": ua,
            "Accept-Encoding": "gzip, deflate",
            "Host": "www.sec.gov",  # overridden per request when needed
        },
        timeout=30,
        follow_redirects=True,
    )


def _gcs_bucket() -> storage.Bucket:
    """Lazy GCS client — auth via ADC on Cloud Run, gcloud creds locally."""
    s = get_settings()
    client = storage.Client()
    return client.bucket(s.gcs_bucket_raw)


@retry(stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=1, min=2, max=8),
       reraise=True)
def _get(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    # Switch Host header based on which subdomain we hit.
    host = "data.sec.gov" if "data.sec.gov" in url else "www.sec.gov"
    r = client.get(url, headers={"Host": host}, **kwargs)
    r.raise_for_status()
    return r


def _load_cik_map(client: httpx.Client) -> dict[str, int]:
    """Fetch ticker→CIK once per process. Returns UPPER ticker → int CIK.

    Adds dash↔dot aliases for dual-class names: SEC stores BRK-B but our
    universe uses BRK.B. Mapping both keys to the same CIK means the
    EDGAR ingestor finds our universe ticker without per-call patching.
    """
    if _CIK_CACHE:
        return _CIK_CACHE
    r = _get(client, TICKERS_URL)
    data = r.json()
    # SEC returns {"0":{"cik_str":..., "ticker":..., "title":...}, "1":{...}}
    for row in data.values():
        ticker = str(row["ticker"]).upper()
        cik = int(row["cik_str"])
        _CIK_CACHE[ticker] = cik
        # Dual-class alias: SEC's BRK-B = universe BRK.B; same CIK
        # works for either form. Same pattern for BF-B, RDS-A, etc.
        if "-" in ticker:
            _CIK_CACHE[ticker.replace("-", ".")] = cik
    log.info("sec.cik_loaded", n=len(_CIK_CACHE))
    return _CIK_CACHE


def _list_recent_filings(client: httpx.Client, cik: int) -> list[dict]:
    """Return SEC 'recent filings' rows for one CIK (oldest first)."""
    url = SUBMISSIONS_URL.format(cik=cik)
    r = _get(client, url)
    recent = r.json().get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    period_ends = recent.get("reportDate", [])
    accessions = recent.get("accessionNumber", [])
    primaries = recent.get("primaryDocument", [])
    return [
        {
            "form": forms[i],
            "filing_date": dates[i],
            "period_end": period_ends[i] or None,
            "accession": accessions[i],
            "primary": primaries[i],
        }
        for i in range(len(forms))
    ]


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _extract_text(html: bytes) -> str:
    """Strip HTML to plain text, collapse whitespace."""
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    # Drop script/style/header noise that has zero signal for the LLM.
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text_ = soup.get_text(" ")
    text_ = _WS_RE.sub(" ", text_).strip()
    return text_


def _upload_to_gcs(bucket: storage.Bucket, accession: str, html: bytes) -> str:
    """Upload raw HTML, return gs:// URI."""
    blob_name = f"edgar/{accession}.html"
    blob = bucket.blob(blob_name)
    blob.upload_from_string(html, content_type="text/html; charset=utf-8")
    return f"gs://{bucket.name}/{blob_name}"


def _upsert_filing(row: dict) -> bool:
    """Insert/replace one filing header + excerpt. Returns True if newly written."""
    sql = text("""
        INSERT INTO filings (
            ticker, filing_type, filing_date, period_end,
            accession, raw_gcs_uri, text_summary
        ) VALUES (
            :ticker, :filing_type, :filing_date, :period_end,
            :accession, :raw_gcs_uri, :text_summary
        )
        ON CONFLICT (accession) DO UPDATE SET
            raw_gcs_uri = EXCLUDED.raw_gcs_uri,
            text_summary = EXCLUDED.text_summary,
            fetched_at = NOW()
    """)
    with session_scope() as session:
        session.execute(sql, row)
    return True


def _already_have(accession: str) -> bool:
    """Cheap pre-check: skip if we already have non-empty summary for this accession."""
    sql = text("""
        SELECT 1 FROM filings
        WHERE accession = :a AND text_summary IS NOT NULL AND length(text_summary) > 0
        LIMIT 1
    """)
    with session_scope() as session:
        return session.execute(sql, {"a": accession}).first() is not None


def ingest(
    tickers: Iterable[str],
    forms: Iterable[str] = DEFAULT_FORMS,
    per_form_limit: dict[str, int] | None = None,
) -> IngestResult:
    """Pull recent filings for each ticker."""
    forms_set = frozenset(forms)
    limits = per_form_limit or DEFAULT_PER_FORM_LIMIT
    tickers_list = sorted({t.upper() for t in tickers})

    started = datetime.now()
    log.info("sec.start", n_tickers=len(tickers_list), forms=sorted(forms_set))

    client = _client()
    cik_map = _load_cik_map(client)
    bucket = _gcs_bucket()

    upserted = 0
    bytes_up = 0
    missing: list[str] = []

    try:
        for tk in tickers_list:
            cik = cik_map.get(tk)
            if cik is None:
                missing.append(tk)
                log.warning("sec.cik_missing", ticker=tk)
                continue

            time.sleep(THROTTLE_S)
            try:
                all_filings = _list_recent_filings(client, cik)
            except httpx.HTTPError as e:
                log.warning("sec.submissions_failed", ticker=tk, err=str(e))
                continue

            # Filter to forms of interest, then keep most recent N per form.
            kept_by_form: dict[str, list[dict]] = {f: [] for f in forms_set}
            for f in all_filings:
                form = f["form"]
                if form not in forms_set:
                    continue
                cap = limits.get(form, 0)
                if cap and len(kept_by_form[form]) < cap:
                    kept_by_form[form].append(f)

            for form, items in kept_by_form.items():
                for f in items:
                    accession = f["accession"]
                    if _already_have(accession):
                        continue
                    accession_nodash = accession.replace("-", "")
                    doc_url = ARCHIVES_URL.format(
                        cik=cik,
                        accession_nodash=accession_nodash,
                        primary=f["primary"],
                    )
                    time.sleep(THROTTLE_S)
                    try:
                        r = _get(client, doc_url)
                    except httpx.HTTPError as e:
                        log.warning("sec.doc_failed", ticker=tk,
                                    accession=accession, err=str(e))
                        continue
                    html = r.content
                    bytes_up += len(html)
                    try:
                        gcs_uri = _upload_to_gcs(bucket, accession, html)
                    except Exception as e:
                        log.warning("sec.gcs_failed", ticker=tk,
                                    accession=accession, err=str(e))
                        continue
                    excerpt = _extract_text(html)[:EXCERPT_CHARS]
                    _upsert_filing({
                        "ticker": tk,
                        "filing_type": form,
                        "filing_date": date.fromisoformat(f["filing_date"]),
                        "period_end": (
                            date.fromisoformat(f["period_end"])
                            if f["period_end"] else None
                        ),
                        "accession": accession,
                        "raw_gcs_uri": gcs_uri,
                        "text_summary": excerpt,
                    })
                    upserted += 1
                    log.info("sec.filing_stored", ticker=tk, form=form,
                             accession=accession, excerpt_len=len(excerpt))
    finally:
        client.close()

    duration_ms = int((datetime.now() - started).total_seconds() * 1000)
    result = IngestResult(
        source="sec_edgar",
        tickers_processed=len(tickers_list),
        filings_upserted=upserted,
        bytes_uploaded=bytes_up,
        duration_ms=duration_ms,
        tickers_missing_cik=missing,
    )
    log.info("sec.done", upserted=upserted, bytes_uploaded=bytes_up,
             missing=len(missing), ms=duration_ms)
    return result
