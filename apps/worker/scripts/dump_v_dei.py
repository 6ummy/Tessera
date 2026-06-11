"""Dump V's dei namespace to see if EntityCommonStockSharesOutstanding
exists and what its observations' end dates look like."""
from tessera_worker.ingestors.sec_edgar import _client, _load_cik_map
from tessera_worker.ingestors.sec_edgar_facts import _fetch_companyfacts

client = _client()
cik = _load_cik_map(client)["V"]
cf = _fetch_companyfacts(client, cik)
client.close()

dei = cf.get("facts", {}).get("dei", {})
print(f"dei concepts on V: {len(dei)}")
print("\nAll dei concept names:")
for k in sorted(dei.keys()):
    print(f"  {k}")

target = "EntityCommonStockSharesOutstanding"
fact = dei.get(target)
if not fact:
    print(f"\n!! {target} NOT in dei facts")
else:
    units = fact.get("units", {})
    print(f"\n{target} units: {list(units.keys())}")
    obs_list = units.get("shares", [])
    print(f"  {len(obs_list)} observations. Showing newest 8:")
    for obs in sorted(obs_list, key=lambda o: o.get("end", ""), reverse=True)[:8]:
        print(f"    end={obs.get('end')} form={obs.get('form')} "
              f"fy={obs.get('fy')} fp={obs.get('fp')} val={obs.get('val')}")
