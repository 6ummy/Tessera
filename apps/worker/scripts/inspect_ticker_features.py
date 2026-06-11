"""Inspect one ticker's data lineage — fundamentals → features.

Use to debug "why is X showing blank in the UI?" — e.g. VISA on
/proposals where fcf_yield / PEG / market cap / EPS CAGR / D-E /
gross margin all render as "—".

Run:
    cd apps/worker
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe \
        scripts/inspect_ticker_features.py V

The script prints:
  1. Latest ticker_features row (what the UI actually reads).
  2. Whether `fundamentals` table has any rows for the ticker
     (per filing_type), and the newest period_end per type.
  3. Whether the latest income/balance/cash payloads carry the
     fields compute.py expects (epsDiluted, totalDebt, freeCashFlow…).
  4. A re-run of the in-memory fundamentals compute against the
     same DB, so you can see which feature compute.py *would*
     produce vs what's actually persisted.
"""

from __future__ import annotations

import sys

from sqlalchemy import text

from tessera_worker.db import session_scope
from tessera_worker.features.compute import (
    _annual_income_rows,
    _eps_value,
    _load_fundamentals_latest,
    _load_latest_closes,
    _to_float,
    compute_debt_to_equity,
    compute_eps_cagr_3y,
    compute_fcf_yield,
    compute_gross_margin,
    compute_gross_margin_trend,
    compute_peg,
    estimate_market_cap,
    sum_ttm_fcf,
)
from tessera_worker.logging import configure_logging

configure_logging()


def main(ticker: str) -> int:
    t = ticker.upper()
    print(f"\n=== Inspecting {t} ===\n")

    with session_scope() as session:
        # 1) Latest ticker_features row.
        feat = session.execute(text("""
            SELECT ts::date AS asof,
                   fcf_yield, peg, market_cap_usd,
                   eps_cagr_3y, debt_to_equity,
                   gross_margin, gross_margin_trend, operating_margin,
                   pe_trailing, pe_forward,
                   ret_30d, ret_1y, vol_30d, rsi_14
            FROM ticker_features
            WHERE ticker = :t
            ORDER BY ts DESC
            LIMIT 1
        """), {"t": t}).mappings().first()

    print("[1] ticker_features (latest row UI reads)")
    if not feat:
        print("    (none) — no row at all. Either ingest didn't run or ticker isn't in universe.")
    else:
        for k, v in feat.items():
            print(f"    {k:20} = {v}")
    print()

    # 2) Fundamentals coverage
    with session_scope() as session:
        cov = session.execute(text("""
            SELECT filing_type, COUNT(*) AS n,
                   MIN(period_end) AS oldest, MAX(period_end) AS newest
            FROM fundamentals
            WHERE ticker = :t
            GROUP BY filing_type
            ORDER BY filing_type
        """), {"t": t}).all()
    print("[2] fundamentals coverage")
    if not cov:
        print("    (empty) — fmp_fundamentals ingestor never wrote anything for this ticker.")
        print("    Fix path: run `python -m tessera_worker.ingestors.fmp_fundamentals` or")
        print("    invoke the daily ingest cron with this ticker included.")
    else:
        for filing_type, n, oldest, newest in cov:
            print(f"    {filing_type:10}  rows={n:3}   {oldest} → {newest}")
    print()

    # 3) Field presence in latest payloads
    print("[3] field presence in latest payload per filing_type")
    with session_scope() as session:
        for filing_type, want_keys in [
            ("income", ["epsDiluted", "epsBasic", "revenue", "grossProfit",
                        "operatingIncome", "weightedAverageShsOutDil", "marketCap"]),
            ("balance", ["totalDebt", "longTermDebt", "shortTermDebt",
                         "totalStockholdersEquity"]),
            ("cash_flow", ["freeCashFlow", "reportedCurrency", "period",
                           "marketCap"]),
        ]:
            row = session.execute(text("""
                SELECT period_end, payload
                FROM fundamentals
                WHERE ticker = :t AND filing_type = :ft
                ORDER BY period_end DESC
                LIMIT 1
            """), {"t": t, "ft": filing_type}).first()
            if not row:
                print(f"    {filing_type:10}  (no rows)")
                continue
            pe, payload = row
            print(f"    {filing_type:10}  period_end={pe}")
            for k in want_keys:
                v = payload.get(k) if isinstance(payload, dict) else None
                marker = "✓" if v not in (None, "", 0) else "·"
                print(f"        {marker} {k:30} = {v!r}"[:120])
    print()

    # 4) Re-run compute against current DB.
    fund = _load_fundamentals_latest([t]).get(t)
    closes = _load_latest_closes([t]).get(t)
    print("[4] dry-run compute (what compute.py would produce right now)")
    if not fund or not closes:
        print(f"    skipped — fundamentals_present={bool(fund)} close_present={bool(closes)}")
        return 0
    ts, close = closes
    print(f"    latest close (USD per ADR/share): {close}  asof={ts.date()}")
    print(f"    reported_currency: {fund.get('reported_currency')!r}")
    print(f"    shares_basic={fund.get('shares_basic')}  "
          f"shares_diluted={fund.get('shares_diluted')}  "
          f"payload_mcap_cash={fund.get('payload_mcap_cash')}  "
          f"payload_mcap_income={fund.get('payload_mcap_income')}")
    ttm_fcf = sum_ttm_fcf(fund["cash_rows"])
    mcap = estimate_market_cap(
        close=close,
        shares_basic=fund.get("shares_basic"),
        shares_diluted=fund.get("shares_diluted"),
        payload_mcap_cash=fund.get("payload_mcap_cash"),
        payload_mcap_income=fund.get("payload_mcap_income"),
        ticker=t,
    )
    yld = compute_fcf_yield(
        close=close,
        fcf_local=ttm_fcf,
        shares_basic=fund.get("shares_basic"),
        shares_diluted=fund.get("shares_diluted"),
        reported_currency=fund.get("reported_currency"),
        payload_mcap_cash=fund.get("payload_mcap_cash"),
        payload_mcap_income=fund.get("payload_mcap_income"),
        ticker=t,
    )
    income_rows = fund.get("income_rows", [])
    annual_income = _annual_income_rows(income_rows)
    latest_income = annual_income[0] if annual_income else (income_rows[0] if income_rows else {})
    eps_cagr = compute_eps_cagr_3y(income_rows)
    peg = compute_peg(close, _eps_value(latest_income), eps_cagr)
    revenue = _to_float(latest_income.get("revenue"))
    gm = compute_gross_margin(revenue, _to_float(latest_income.get("grossProfit")))
    om = compute_gross_margin(revenue, _to_float(latest_income.get("operatingIncome")))
    gm_trend = compute_gross_margin_trend(income_rows)
    bal = fund.get("balance", {})
    de = compute_debt_to_equity(
        total_debt=bal.get("total_debt"),
        long_term_debt=bal.get("long_term_debt"),
        short_term_debt=bal.get("short_term_debt"),
        equity=bal.get("equity"),
    )
    for label, val in [
        ("ttm_fcf (local ccy)", ttm_fcf),
        ("market_cap (USD)",    mcap),
        ("fcf_yield",           yld),
        ("eps_cagr_3y",         eps_cagr),
        ("peg",                 peg),
        ("gross_margin",        gm),
        ("operating_margin",    om),
        ("gross_margin_trend",  gm_trend),
        ("debt_to_equity",      de),
    ]:
        print(f"    {label:24} = {val}")
    print()
    print("Diff hint: any compute value above that is non-None but missing in [1]")
    print("means the fundamentals pass never ran for this ticker since the last")
    print("schema/ingest change — run `build_features([ticker])` to backfill.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: inspect_ticker_features.py <TICKER>")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
