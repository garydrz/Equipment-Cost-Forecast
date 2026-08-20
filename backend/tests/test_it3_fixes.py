"""Iteration-3 strict verification of the weighted_similarity_v2 fixes.

Covers: fallback path, missing target pressure (F=1 skip), vessel references,
Pydantic gt=0/ge=1 validation, unified failure shape (_unavailable),
DUMMY project row quality, material/pressure math, weighted normalization,
meta/indices, row sanitization.
"""
import math
import pytest

pytest.skip("v2 suite superseded by tests/test_v3.py (weighted_similarity_v3)",
            allow_module_level=True)

FAILURE_KEYS = [
    "estimate_available", "expected", "low", "high", "sigma",
    "references_used", "references_excluded", "scaling_variable",
    "scaling_variable_is_fallback", "model_version",
    "total_expected", "total_low", "total_high",
]


# --- fallback scaling variable path -------------------------------------
class TestFallbackPath:
    def test_column_size_only_estimate_available(self, api, base_url):
        r = api.post(f"{base_url}/estimate", json={
            "category": "column", "size": 50, "material": "carbon_steel",
            "design_pressure_bar": 10, "target_year": 2026, "output_currency": "EUR",
        }, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["estimate_available"] is True, d
        assert d["scaling_variable"] == "size"
        assert d["scaling_variable_is_fallback"] is True
        assert d["scaling_variable_value"] == 50
        assert d["references_used"] > 0
        assert d["expected"] > 0
        assert d["low"] <= d["expected"] <= d["high"]
        warns = " ".join(d.get("warnings") or [])
        assert "allback" in warns, f"expected fallback warning, got {d.get('warnings')}"
        # references must be evaluated on the fallback variable too
        for ref in d["references_detail"]:
            assert ref.get("scaling_variable") in (None, "size"), ref

    def test_no_duplicate_warnings(self, api, base_url):
        r = api.post(f"{base_url}/estimate", json={
            "category": "column", "size": 50, "material": "carbon_steel",
            "design_pressure_bar": 10, "target_year": 2026, "output_currency": "USD",
        }, timeout=60)
        w = r.json().get("warnings") or []
        assert len(w) == len(set(w)), f"duplicated warnings: {w}"


# --- missing target pressure -------------------------------------------
class TestMissingTargetPressure:
    @pytest.fixture(scope="class")
    def resp(self, api, base_url):
        r = api.post(f"{base_url}/estimate", json={
            "category": "column", "size": 50, "weight_kg": 36000,
            "material": "stainless_steel_316",
            "target_year": 2026, "output_currency": "EUR",
        }, timeout=60)
        assert r.status_code == 200, r.text
        return r.json()

    def test_estimate_available(self, resp):
        assert resp["estimate_available"] is True, resp
        assert resp["references_used"] > 0
        assert resp["expected"] > 0

    def test_no_pressure_exclusions(self, resp):
        for e in resp["references_excluded"]:
            assert "pressure" not in (e.get("exclusion_reason") or "").lower(), e

    def test_global_warning(self, resp):
        warns = resp.get("warnings") or []
        assert any("target design pressure missing" in w.lower() for w in warns), warns
        # single global warning, not per reference
        assert sum(1 for w in warns if "target design pressure missing" in w.lower()) == 1

    def test_reference_pressure_status_and_factor(self, resp):
        assert resp["references_detail"]
        for ref in resp["references_detail"]:
            assert ref["pressure_status"] == "skipped-target-pressure-missing", ref
            assert ref["applied_pressure_factor"] == 1.0, ref


# --- vessel category ---------------------------------------------------
class TestVessel:
    def test_vessel_estimate(self, api, base_url):
        r = api.post(f"{base_url}/estimate", json={
            "category": "vessel", "weight_kg": 20000, "size": 30,
            "material": "carbon_steel", "design_pressure_bar": 15,
            "target_year": 2026, "output_currency": "EUR",
        }, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["estimate_available"] is True, d
        assert d["references_used"] >= 1
        assert d["scaling_variable"] == "weight_kg"
        assert d["expected"] > 0

    def test_vessel_refs_exist(self, api, base_url):
        docs = api.get(f"{base_url}/equipment", params={"category": "vessel"}, timeout=30).json()
        assert len(docs) >= 2, docs
        subs = {d.get("subtype") for d in docs}
        assert "Horizontal separator" in subs and "Vertical KO drum" in subs, subs


# --- input validation (gt=0 / ge=1) ------------------------------------
class TestValidation:
    BASE = {"category": "column", "size": 50, "material": "carbon_steel",
            "design_pressure_bar": 10, "target_year": 2026, "output_currency": "EUR"}

    @pytest.mark.parametrize("field,value", [
        ("weight_kg", -5), ("weight_kg", 0),
        ("size", -1), ("size", 0),
        ("power_kw", -10), ("power_kw", 0),
        ("quantity", 0), ("quantity", -2),
    ])
    def test_estimate_rejects_non_positive(self, api, base_url, field, value):
        payload = dict(self.BASE)
        payload[field] = value
        r = api.post(f"{base_url}/estimate", json=payload, timeout=30)
        assert r.status_code == 422, f"{field}={value} -> {r.status_code} {r.text[:300]}"

    @pytest.mark.parametrize("field,value", [("weight_kg", -5), ("size", 0), ("quantity", 0)])
    def test_row_rejects_non_positive(self, api, base_url, it3_project, field, value):
        payload = {"tag": "TEST_bad", "category": "column", "size": 50,
                   "material": "carbon_steel", "design_pressure_bar": 10}
        payload[field] = value
        r = api.post(f"{base_url}/projects/{it3_project}/rows", json=payload, timeout=30)
        assert r.status_code == 422, f"{field}={value} -> {r.status_code} {r.text[:300]}"

    def test_historical_rejects_non_positive(self, api, base_url):
        r = api.post(f"{base_url}/equipment", json={
            "category": "column", "subtype": "TEST_bad", "size": -3, "size_unit": "m3",
            "material": "carbon_steel", "year": 2020, "cost_original": 1000,
            "currency_original": "EUR",
        }, timeout=30)
        assert r.status_code == 422, r.text[:300]


# --- unified failure shape --------------------------------------------
class TestFailureShape:
    def _assert_shape(self, d):
        for k in FAILURE_KEYS:
            assert k in d, f"missing key {k} in failure response: {sorted(d)}"
        assert "excluded_references" not in d
        assert d["estimate_available"] is False
        for k in ("expected", "low", "high", "sigma", "total_expected", "total_low", "total_high"):
            assert d[k] is None, f"{k} should be None, got {d[k]}"
        assert d["references_used"] == 0
        assert isinstance(d["references_excluded"], list)
        assert d["model_version"] == "weighted_similarity_v2"

    def test_unknown_category_shape(self, api, base_url):
        r = api.post(f"{base_url}/estimate", json={
            "category": "unicorn", "size": 5, "material": "carbon_steel",
            "target_year": 2026, "output_currency": "EUR",
        }, timeout=30)
        assert r.status_code == 200, r.text
        self._assert_shape(r.json())

    def test_no_scaling_variable_shape(self, api, base_url):
        # compressor primary=power_kw, fallback=size -> omit both is impossible (size required),
        # use 'other' category which has no references
        r = api.post(f"{base_url}/estimate", json={
            "category": "other", "size": 5, "material": "carbon_steel",
            "target_year": 2026, "output_currency": "EUR",
        }, timeout=30)
        assert r.status_code == 200, r.text
        self._assert_shape(r.json())

    def test_all_refs_excluded_shape(self, api, base_url):
        # unknown material for target? use extreme size mismatch with strict subtype filter
        r = api.post(f"{base_url}/estimate", json={
            "category": "instrumentation", "size": 1, "material": "carbon_steel",
            "subtype": "NO_SUCH_SUBTYPE_XYZ",
            "target_year": 2026, "output_currency": "EUR",
        }, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        if d["estimate_available"] is False:
            self._assert_shape(d)


# --- DUMMY project quality --------------------------------------------
class TestDummyProject:
    def test_recompute_and_row_quality(self, api, base_url):
        projects = api.get(f"{base_url}/projects", timeout=30).json()
        dummy = next((p for p in projects if "DUMMY" in (p.get("name") or "").upper()), None)
        if dummy is None:
            pytest.skip("no DUMMY project present")
        rc = api.post(f"{base_url}/projects/{dummy['id']}/recompute", timeout=120)
        assert rc.status_code == 200, rc.text
        detail = api.get(f"{base_url}/projects/{dummy['id']}", timeout=60).json()
        rows = detail["rows"]
        assert rows
        bad = []
        for row in rows:
            if not row.get("estimate_available") or (row.get("references_used") or 0) <= 0:
                bad.append({"tag": row.get("tag"), "cat": row.get("category"),
                            "avail": row.get("estimate_available"),
                            "refs": row.get("references_used"),
                            "warn": row.get("warnings"), "err": row.get("errors")})
        assert not bad, f"rows without a usable estimate: {bad}"
        assert detail["totals"]["expected"] > 0


# --- math ---------------------------------------------------------------
class TestMath:
    def test_material_factor_ss316_vs_cs(self, api, base_url):
        refs = api.get(f"{base_url}/equipment", params={"category": "column"}, timeout=30).json()
        cs = next(x for x in refs if x["material"] == "carbon_steel")
        r = api.post(f"{base_url}/estimate", json={
            "category": "column", "size": 45, "weight_kg": 32000,
            "material": "stainless_steel_316", "design_pressure_bar": 12,
            "target_year": 2026, "output_currency": "EUR", "reference_ids": [cs["id"]],
        }, timeout=60)
        d = r.json()
        assert d["estimate_available"] is True, d
        assert abs(d["references_detail"][0]["applied_material_factor"] - 2.1) < 1e-9, d["references_detail"][0]

    def test_pressure_factor_formula(self, api, base_url):
        refs = api.get(f"{base_url}/equipment", params={"category": "column"}, timeout=30).json()
        ref = next(x for x in refs if x["subtype"] == "Distillation packed")
        cfg = api.get(f"{base_url}/admin/pressure-factors", timeout=30).json()
        items = cfg if isinstance(cfg, list) else cfg.get("categories", [])
        col = next((c for c in items if c.get("category") == "column"), None)
        assert col, cfg
        p_exp = col["pressure_exponent"]
        atm = api.get(f"{base_url}/admin/similarity-settings", timeout=30).json()["atmospheric_pressure_bar"]
        r = api.post(f"{base_url}/estimate", json={
            "category": "column", "size": 60, "weight_kg": 38000,
            "material": "stainless_steel_316", "design_pressure_bar": 25,
            "target_year": 2026, "output_currency": "EUR", "reference_ids": [ref["id"]],
        }, timeout=60)
        d = r.json()
        assert d["estimate_available"] is True, d
        expected = ((25 + atm) / (ref["design_pressure_bar"] + atm)) ** p_exp
        got = d["references_detail"][0]["applied_pressure_factor"]
        assert abs(got - expected) / expected < 0.01, (got, expected)

    def test_weight_normalization(self, api, base_url):
        r = api.post(f"{base_url}/estimate", json={
            "category": "column", "size": 50, "weight_kg": 35000,
            "material": "stainless_steel_316", "design_pressure_bar": 10,
            "target_year": 2026, "output_currency": "EUR",
        }, timeout=60)
        d = r.json()
        assert d["estimate_available"] is True, d
        wsum = sum(x["normalized_weight"] for x in d["references_detail"])
        assert abs(wsum - 1.0) < 0.01, wsum
        contrib = sum(x["weighted_contribution"] for x in d["references_detail"])
        assert abs(contrib - d["expected"]) / d["expected"] < 0.001, (contrib, d["expected"])


# --- meta / config ------------------------------------------------------
class TestMetaAndAdmin:
    def test_categories_vessel_meta(self, api, base_url):
        d = api.get(f"{base_url}/meta/categories", timeout=30).json()
        cats = d if isinstance(d, list) else d.get("categories")
        meta = d.get("category_meta") if isinstance(d, dict) else None
        names = [c if isinstance(c, str) else c.get("value") or c.get("key") for c in (cats or [])]
        assert "vessel" in names, names
        if meta:
            assert meta["vessel"]["primary_variable"] == "weight_kg"
            assert meta["vessel"]["fallback_variable"] == "size"

    def test_indices_source_fred(self, api, base_url):
        d = api.get(f"{base_url}/indices", timeout=60).json()
        assert d["source"] == "FRED", d.get("source")
        assert d["steel_by_year"] and d["oil_by_year"]

    def test_similarity_weights_must_sum_to_one(self, api, base_url):
        cur = api.get(f"{base_url}/admin/similarity-settings", timeout=30).json()
        bad = {k: v for k, v in cur.items() if k not in ("defaults", "updated_at")}
        bad["w_size"] = 0.9
        bad["w_material"] = 0.9
        r = api.put(f"{base_url}/admin/similarity-settings", json=bad, timeout=30)
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"
        after = api.get(f"{base_url}/admin/similarity-settings", timeout=30).json()
        assert after["w_size"] == cur["w_size"], "rejected update must not persist"


# --- row sanitization ---------------------------------------------------
class TestRowSanitization:
    def test_valve_power_kw_sanitized(self, api, base_url, it3_project):
        r = api.post(f"{base_url}/projects/{it3_project}/rows", json={
            "tag": "TEST_it3_valve", "category": "valve", "subtype": "Control",
            "size": 100, "material": "stainless_steel_316",
            "design_pressure_bar": 20, "power_kw": 100, "quantity": 3,
        }, timeout=60)
        assert r.status_code == 200, r.text
        row = r.json()
        assert row["power_kw"] is None, row
        assert row["quantity"] == 3


@pytest.fixture(scope="module")
def it3_project(api, base_url):
    r = api.post(f"{base_url}/projects", json={
        "name": "TEST_it3_project", "description": "TEST iteration3",
        "output_currency": "EUR", "target_year": 2026, "aace_class": "Class 3",
    }, timeout=30)
    r.raise_for_status()
    pid = r.json()["id"]
    yield pid
    api.delete(f"{base_url}/projects/{pid}", timeout=30)
