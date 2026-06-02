"""SEC EDGAR XBRL companyfacts ingestor.

Pulls structured fundamentals data straight from SEC's pre-parsed XBRL
facts JSON, bypassing FMP's per-symbol free-tier gating. Maps US-GAAP
concept names to the same field names FMP uses, so downstream feature
code reads the `fundamentals` table without caring which source filled it.

Source: https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json
- Free, unmetered, no API key (User-Agent required, same as sec_edgar.py).
- SEC has already done the XBRL XML → JSON normalization for us, so we
  avoid the `arelle` / `python-xbrl` parsing complexity entirely.

Coverage: every SEC filer (so the ~29 tickers FMP free tier blocks are
now reachable). Caveat: works only for US-listed companies that file with
SEC. Foreign filers (ASML, TSM, BABA) submit 20-F, not 10-K/10-Q —
companyfacts JSON may have less coverage; we tolerate missing fields.

Storage: writes to the existing `fundamentals` table (ticker, period_end,
filing_type, payload). Payload uses FMP-compatible field names so the
LLM demo + Quant FCF yield demo work without changes.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable

import httpx
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential

from tessera_worker.db import session_scope
from tessera_worker.logging import get_logger
from tessera_worker.ingestors.sec_edgar import _client, _load_cik_map

log = get_logger(__name__)

COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
THROTTLE_S = 0.12  # ~8 req/s, well under SEC's 10/s cap

# ── GAAP concept → our field name ────────────────────────────────────
# Each value is a list of XBRL concept names, tried in priority order.
# The first one with data wins (e.g. Apple stopped reporting Revenues
# after 2018 and switched to RevenueFromContractWithCustomerExcludingAssessedTax
# when ASC 606 took effect).
#
# Our field names mirror FMP's so the existing demos / LLM prompts read
# the same payload shape regardless of source.

CONCEPTS_INCOME: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "costOfRevenue":     ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
    "grossProfit":       ["GrossProfit"],
    "operatingIncome":   ["OperatingIncomeLoss"],
    "incomeTaxExpense":  ["IncomeTaxExpenseBenefit"],
    "netIncome":         ["NetIncomeLoss"],
    "researchAndDevelopmentExpense": ["ResearchAndDevelopmentExpense"],
    "epsDiluted":        ["EarningsPerShareDiluted"],
    "epsBasic":          ["EarningsPerShareBasic"],
    "weightedAverageShsOut":     ["WeightedAverageNumberOfSharesOutstandingBasic"],
    "weightedAverageShsOutDil":  ["WeightedAverageNumberOfDilutedSharesOutstanding"],
}

CONCEPTS_BALANCE: dict[str, list[str]] = {
    "totalAssets":              ["Assets"],
    "totalCurrentAssets":       ["AssetsCurrent"],
    "totalLiabilities":         ["Liabilities"],
    "totalCurrentLiabilities":  ["LiabilitiesCurrent"],
    "totalStockholdersEquity":  ["StockholdersEquity"],
    "longTermDebt":             ["LongTermDebt", "LongTermDebtNoncurrent"],
    "shortTermDebt":            ["DebtCurrent", "ShortTermBorrowings"],
    "cashAndCashEquivalents":   ["CashAndCashEquivalentsAtCarryingValue"],
    "cashAndShortTermInvestments": ["CashCashEquivalentsAndShortTermInvestments"],
    "netReceivables":           ["AccountsReceivableNetCurrent"],
    "inventory":                ["InventoryNet"],
    "propertyPlantAndEquipmentNet": ["PropertyPlantAndEquipmentNet"],
    "goodwill":                 ["Goodwill"],
}

CONCEPTS_CASHFLOW: dict[str, list[str]] = {
    "operatingCashFlow":           ["NetCashProvidedByUsedInOperatingActivities"],
    "netCashProvidedByInvestingActivities": ["NetCashProvidedByUsedInInvestingActivities"],
    "netCashProvidedByFinancingActivities": ["NetCashProvidedByUsedInFinancingActivities"],
    "capitalExpenditure":          ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "commonStockRepurchased":      ["PaymentsForRepurchaseOfCommonStock"],
    "commonDividendsPaid":         ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
    "depreciationAndAmortization": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization"],
}

CONCEPT_MAP_BY_TYPE: dict[str, dict[str, list[str]]] = {
    "income":    CONCEPTS_INCOME,
    "balance":   CONCEPTS_BALANCE,
    "cash_flow": CONCEPTS_CASHFLOW,
}


@dataclass(frozen=True, slots=True)
class IngestResult:
    source: str
    tickers_processed: int
    rows_upserted: int
    tickers_missing_cik: list[str] = field(default_factory=list)
    tickers_no_data: list[str] = field(default_factory=list)
    duration_ms: int = 0


@retry(stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=1, min=2, max=8),
       reraise=True)
def _fetch_companyfacts(client: httpx.Client, cik: int) -> dict | None:
    """Return the SEC companyfacts JSON for one CIK, or None if 404."""
    url = COMPANYFACTS_URL.format(cik=cik)
    r = client.get(url, headers={"Host": "data.sec.gov"})
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def _extract_rows(ticker: str, companyfacts: dict) -> list[dict]:
    """Walk us-gaap facts, group by (period_end, filing_type), return upsert rows."""
    us_gaap = companyfacts.get("facts", {}).get("us-gaap", {})
    if not us_gaap:
        return []

    # key = (period_end_str, filing_type, form, fy, fp) → field dict
    payloads: dict[tuple, dict] = {}

    for filing_type, concept_map in CONCEPT_MAP_BY_TYPE.items():
        for our_name, xbrl_names in concept_map.items():
            for xbrl_name in xbrl_names:
                if xbrl_name not in us_gaap:
                    continue
                fact = us_gaap[xbrl_name]
                # Pick the right unit. USD for $ amounts, shares for counts,
                # USD/shares for EPS. Skip other unit types (pure, EUR, etc).
                unit_priority = ["USD", "USD/shares", "shares"]
                unit = next((u for u in unit_priority if u in fact["units"]), None)
                if unit is None:
                    continue
                for obs in fact["units"][unit]:
                    form = obs.get("form")
                    if form not in ("10-K", "10-Q"):
                        continue
                    period_end = obs.get("end")
                    if not period_end:
                        continue
                    key = (period_end, filing_type, form, obs.get("fy"), obs.get("fp"))
                    payload = payloads.setdefault(key, {
                        "source": "edgar",
                        "form": form,
                        "fy": obs.get("fy"),
                        "fp": obs.get("fp"),
                        "accn": obs.get("accn"),
                    })
                    # If two observations cover the same key from different
                    # filings (one corrects the other), the LATER one wins —
                    # iteration order is filed-date ascending in SEC's response.
                    payload[our_name] = obs["val"]
                # First matching xbrl_name wins for this our_name
                break

    # Derived field: freeCashFlow = operatingCashFlow - abs(capex)
    # Only when both components present and we're in the cash_flow row for
    # that period (FCF lives there in our schema convention).
    for (pe, ft, form, fy, fp), payload in payloads.items():
        if ft == "cash_flow":
            ocf = payload.get("operatingCashFlow")
            capex = payload.get("capitalExpenditure")
            if ocf is not None and capex is not None:
                payload["freeCashFlow"] = ocf - abs(capex)

    # Collapse to the table's UNIQUE shape (ticker, period_end, filing_type) —
    # if there are multiple form/fy/fp combos for the same period_end+filing_type
    # (rare but possible when a company restates), prefer the 10-K over 10-Q
    # for that period_end.
    out: dict[tuple, dict] = {}
    for (pe, ft, form, fy, fp), payload in payloads.items():
        key = (pe, ft)
        existing = out.get(key)
        if existing is None or (form == "10-K" and existing.get("form") == "10-Q"):
            out[key] = payload

    rows = [
        {"ticker": ticker, "period_end": pe, "filing_type": ft, "payload": json.dumps(payload)}
        for (pe, ft), payload in out.items()
    ]
    return rows


def _upsert(rows: list[dict]) -> int:
    if not rows:
        return 0
    # JSONB merge (||) preserves any field present in the existing FMP row
    # but EDGAR's values take precedence on overlapping keys (EDGAR is the
    # canonical source — FMP/Tiingo/Yahoo all derive from SEC filings).
    sql = text("""
        INSERT INTO fundamentals (ticker, period_end, filing_type, payload)
        VALUES (:ticker, :period_end, :filing_type, CAST(:payload AS JSONB))
        ON CONFLICT (ticker, period_end, filing_type)
        DO UPDATE SET
            payload = fundamentals.payload || EXCLUDED.payload,
            fetched_at = NOW()
    """)
    chunk = 500
    written = 0
    with session_scope() as session:
        for i in range(0, len(rows), chunk):
            session.execute(sql, rows[i : i + chunk])
            written += len(rows[i : i + chunk])
    return written


def ingest(tickers: Iterable[str]) -> IngestResult:
    """Pull XBRL companyfacts for each ticker → upsert fundamentals."""
    tickers_list = sorted({t.upper() for t in tickers})
    started = datetime.now()
    log.info("sec_facts.start", n_tickers=len(tickers_list))

    client = _client()
    cik_map = _load_cik_map(client)

    missing_cik: list[str] = []
    no_data: list[str] = []
    total_rows = 0

    try:
        for tk in tickers_list:
            cik = cik_map.get(tk)
            if cik is None:
                missing_cik.append(tk)
                log.warning("sec_facts.cik_missing", ticker=tk)
                continue

            time.sleep(THROTTLE_S)
            try:
                cf = _fetch_companyfacts(client, cik)
            except httpx.HTTPError as e:
                log.warning("sec_facts.fetch_failed", ticker=tk, err=str(e))
                continue

            if cf is None:
                no_data.append(tk)
                log.info("sec_facts.no_data", ticker=tk)
                continue

            rows = _extract_rows(tk, cf)
            if not rows:
                no_data.append(tk)
                log.info("sec_facts.no_rows", ticker=tk)
                continue

            n = _upsert(rows)
            total_rows += n
            log.info("sec_facts.ticker_done", ticker=tk, rows=n)

    finally:
        client.close()

    duration_ms = int((datetime.now() - started).total_seconds() * 1000)
    result = IngestResult(
        source="sec_edgar_facts",
        tickers_processed=len(tickers_list),
        rows_upserted=total_rows,
        tickers_missing_cik=missing_cik,
        tickers_no_data=no_data,
        duration_ms=duration_ms,
    )
    log.info("sec_facts.done",
             tickers=len(tickers_list),
             rows=total_rows,
             missing=len(missing_cik),
             no_data=len(no_data),
             ms=duration_ms)
    return result
