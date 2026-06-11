"""Dump every us-gaap concept Visa has reported, grouped by whether
their value is currently used by sec_edgar_facts mapping or not.

Helps decide which XBRL concept name to add as a fallback when V (or
any other ticker) leaves our mapped fields blank.
"""
from tessera_worker.ingestors.sec_edgar import _client, _load_cik_map
from tessera_worker.ingestors.sec_edgar_facts import (
    CONCEPT_MAP_BY_TYPE,
    _fetch_companyfacts,
)

KNOWN_CONCEPTS = {c for cmap in CONCEPT_MAP_BY_TYPE.values()
                    for names in cmap.values() for c in names}

# Concepts worth looking at by category, even if not currently mapped
SHARE_HINTS = ("Shares", "Stock")
CAPEX_HINTS = ("Property", "Capital", "ProductiveAssets")
MARGIN_HINTS = ("GrossProfit", "CostOfRevenue", "CostOfGoods", "OperatingExpenses")

client = _client()
cik_map = _load_cik_map(client)
cik = cik_map["V"]
cf = _fetch_companyfacts(client, cik)
client.close()

us_gaap = cf["facts"]["us-gaap"]
print(f"Total us-gaap concepts reported by V: {len(us_gaap)}\n")

def matches(name: str, hints: tuple[str, ...]) -> bool:
    return any(h.lower() in name.lower() for h in hints)

for label, hints in [("SHARES candidates", SHARE_HINTS),
                     ("CAPEX candidates", CAPEX_HINTS),
                     ("MARGIN/COST candidates", MARGIN_HINTS)]:
    print(f"=== {label} ===")
    for name in sorted(us_gaap.keys()):
        if matches(name, hints):
            units = list(us_gaap[name].get("units", {}).keys())
            mark = " (MAPPED)" if name in KNOWN_CONCEPTS else ""
            n_obs = sum(len(us_gaap[name]["units"][u]) for u in units)
            print(f"  {name}  units={units}  n_obs={n_obs}{mark}")
    print()
