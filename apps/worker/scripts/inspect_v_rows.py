"""Quick one-off: dump V's recent fundamentals payload fields per filing_type.

Run:
    .venv\\Scripts\\python.exe scripts\\inspect_v_rows.py
"""
from sqlalchemy import text
from tessera_worker.db import session_scope

with session_scope() as s:
    print("\n=== Income / shares + grossProfit + marketCap (top 12) ===")
    rows = s.execute(text("""
        SELECT period_end,
               payload->>'source'                    AS src,
               payload->>'weightedAverageShsOut'     AS shs_b,
               payload->>'weightedAverageShsOutDil'  AS shs_d,
               payload->>'grossProfit'               AS gp,
               payload->>'marketCap'                 AS mcap
        FROM fundamentals
        WHERE ticker='V' AND filing_type='income'
        ORDER BY period_end DESC LIMIT 12
    """)).all()
    for r in rows:
        print(r)

    print("\n=== Cash flow / FCF + OCF + capex (top 12) ===")
    rows = s.execute(text("""
        SELECT period_end,
               payload->>'source'              AS src,
               payload->>'freeCashFlow'        AS fcf,
               payload->>'operatingCashFlow'   AS ocf,
               payload->>'capitalExpenditure'  AS capex,
               payload->>'reportedCurrency'    AS ccy,
               payload->>'period'              AS period
        FROM fundamentals
        WHERE ticker='V' AND filing_type='cash_flow'
        ORDER BY period_end DESC LIMIT 12
    """)).all()
    for r in rows:
        print(r)

    print("\n=== Source breakdown across all V rows ===")
    rows = s.execute(text("""
        SELECT filing_type,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE payload->>'source' = 'edgar') AS edgar,
               COUNT(*) FILTER (WHERE payload->>'source' IS NULL)   AS no_source
        FROM fundamentals
        WHERE ticker='V'
        GROUP BY filing_type
        ORDER BY filing_type
    """)).all()
    for r in rows:
        print(r)
