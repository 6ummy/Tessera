"""Show V's most recent income rows + which fields each carries.

Helps diagnose whether yf_history values actually landed in DB, and
whether they're being picked up by the _annual_income_rows filter.
"""
from sqlalchemy import text
from tessera_worker.db import session_scope

with session_scope() as s:
    rows = s.execute(text("""
        SELECT period_end,
               payload->>'source'          AS src,
               payload->>'period'          AS period,
               payload->>'form'            AS form,
               payload->>'fp'              AS fp,
               payload->>'epsDiluted'      AS eps_d,
               payload->>'epsBasic'        AS eps_b,
               payload->>'revenue'         AS revenue,
               payload->>'grossProfit'     AS gp
        FROM fundamentals
        WHERE ticker = 'V' AND filing_type = 'income'
        ORDER BY period_end DESC
        LIMIT 12
    """)).all()
    for r in rows:
        print(r)
