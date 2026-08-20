import json, os
import requests
from dotenv import dotenv_values

API = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"
s = requests.Session()

# 1. save vessel refs, delete them, estimate, inspect shape, restore
refs = s.get(f"{API}/equipment", params={"category": "vessel"}, timeout=30).json()
print("vessel refs:", [(r["subtype"], r["id"]) for r in refs])
for r in refs:
    print("delete", s.delete(f"{API}/equipment/{r['id']}", timeout=30).status_code)

d = s.post(f"{API}/estimate", json={"category": "vessel", "weight_kg": 20000, "size": 30,
                                    "material": "carbon_steel", "design_pressure_bar": 15,
                                    "target_year": 2026, "output_currency": "EUR"}, timeout=60).json()
print("FAILURE SHAPE keys:", sorted(d.keys()))
print(json.dumps({k: d[k] for k in d if k not in ("references_detail",)}, indent=1)[:2500])

# restore
for r in refs:
    payload = {k: v for k, v in r.items() if k not in ("id", "created_at")}
    rr = s.post(f"{API}/equipment", json=payload, timeout=30)
    print("restore", rr.status_code, rr.text[:200])

print("vessel refs after restore:",
      [(x["subtype"], x["weight_kg"]) for x in s.get(f"{API}/equipment", params={"category": "vessel"}, timeout=30).json()])
v = s.post(f"{API}/estimate", json={"category": "vessel", "weight_kg": 20000, "size": 30,
                                    "material": "carbon_steel", "design_pressure_bar": 15,
                                    "target_year": 2026, "output_currency": "EUR"}, timeout=60).json()
print("vessel estimate after restore:", v["estimate_available"], v["references_used"], v["expected"])
