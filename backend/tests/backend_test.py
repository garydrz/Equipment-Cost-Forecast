"""
Backend tests - EPC parametric cost estimator v2 (weighted_similarity_v2)
Covers: meta, admin config (material/pressure/similarity), estimate math, rows, projects, indices.

SUPERSEDED (iteration 4): backend is now weighted_similarity_v3 with a rigid
category+subtype filter and a different range model, so this v2 suite is skipped.
Use tests/test_v3.py instead.
"""
import pytest

pytest.skip("v2 suite superseded by tests/test_v3.py (weighted_similarity_v3)",
            allow_module_level=True)

import math
import pytest


# ---------------------------------------------------------------
# META
# ---------------------------------------------------------------
class TestMeta:
    def test_root(self, api, base_url):
        r = api.get(f"{base_url}/", timeout=30)
        assert r.status_code == 200
        assert r.json()["model_version"] == "weighted_similarity_v2"

    def test_categories(self, api, base_url):
        r = api.get(f"{base_url}/meta/categories", timeout=30)
        assert r.status_code == 200
        d = r.json()
        cats = d["categories"]
        assert len(cats) == 10, f"expected 10 categories, got {len(cats)}: {cats}"
        assert "vessel" in cats
        expected_primary = {
            "column": "weight_kg", "reactor": "weight_kg", "vessel": "weight_kg",
            "storage_tank": "weight_kg", "heat_exchanger": "weight_kg",
            "pump": "power_kw", "compressor": "power_kw",
            "valve": "size", "instrumentation": "size", "other": "size",
        }
        for cat, pv in expected_primary.items():
            m = d["meta"][cat]
            assert m["primary_variable"] == pv, f"{cat} primary_variable={m['primary_variable']}"
            assert "fallback_variable" in m
        assert d["meta"]["valve"]["size_unit"] == "mm"
        assert d["meta"]["pump"]["show_power"] is True
        assert d["meta"]["column"]["show_power"] is False
        assert len(d["materials"]) == 6


# ---------------------------------------------------------------
# ADMIN: material factors
# ---------------------------------------------------------------
class TestMaterialFactors:
    def test_get(self, api, base_url):
        r = api.get(f"{base_url}/admin/material-factors", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 6
        by_mat = {d["material"]: d for d in data}
        assert by_mat["carbon_steel"]["factor"] == 1.0
        assert by_mat["stainless_steel_316"]["factor"] == 2.1
        for d in data:
            for k in ("factor", "source", "notes", "default_factor", "reference_material"):
                assert k in d, f"missing {k} in {d['material']}"

    def test_put_update_and_restore(self, api, base_url):
        r = api.put(f"{base_url}/admin/material-factors",
                    json=[{"material": "duplex", "factor": 3.33, "source": "TEST", "notes": "TEST"}],
                    timeout=30)
        assert r.status_code == 200, r.text
        got = {d["material"]: d for d in api.get(f"{base_url}/admin/material-factors", timeout=30).json()}
        assert got["duplex"]["factor"] == 3.33
        assert got["duplex"]["source"] == "TEST"
        # restore default
        r2 = api.put(f"{base_url}/admin/material-factors",
                     json=[{"material": "duplex", "factor": 3.00,
                            "source": "preliminary configurable", "notes": "To be calibrated"}],
                     timeout=30)
        assert r2.status_code == 200
        got2 = {d["material"]: d for d in api.get(f"{base_url}/admin/material-factors", timeout=30).json()}
        assert got2["duplex"]["factor"] == 3.00

    def test_put_invalid_factor(self, api, base_url):
        r = api.put(f"{base_url}/admin/material-factors",
                    json=[{"material": "duplex", "factor": 0}], timeout=30)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"

    def test_put_unknown_material(self, api, base_url):
        r = api.put(f"{base_url}/admin/material-factors",
                    json=[{"material": "unobtanium", "factor": 2.0}], timeout=30)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"


# ---------------------------------------------------------------
# ADMIN: pressure factors
# ---------------------------------------------------------------
class TestPressureFactors:
    def test_get(self, api, base_url):
        r = api.get(f"{base_url}/admin/pressure-factors", timeout=30)
        assert r.status_code == 200
        data = {d["category"]: d for d in r.json()}
        assert len(data) == 10
        for cat in ("pump", "compressor", "instrumentation"):
            assert data[cat]["enabled"] is False, f"{cat} should be disabled by default"
        for cat in ("column", "reactor", "vessel", "storage_tank", "heat_exchanger", "valve"):
            assert data[cat]["enabled"] is True, f"{cat} should be enabled by default"
        for d in data.values():
            for k in ("pressure_exponent", "enabled", "minimum_factor", "maximum_factor",
                      "default_exponent", "default_enabled"):
                assert k in d
        assert data["column"]["pressure_exponent"] == 0.60
        assert data["valve"]["pressure_exponent"] == 0.30

    def test_put_update_and_restore(self, api, base_url):
        r = api.put(f"{base_url}/admin/pressure-factors",
                    json=[{"category": "vessel", "pressure_exponent": 0.44, "enabled": True,
                           "minimum_factor": None, "maximum_factor": None}], timeout=30)
        assert r.status_code == 200, r.text
        data = {d["category"]: d for d in api.get(f"{base_url}/admin/pressure-factors", timeout=30).json()}
        assert data["vessel"]["pressure_exponent"] == 0.44
        # restore
        api.put(f"{base_url}/admin/pressure-factors",
                json=[{"category": "vessel", "pressure_exponent": 0.55, "enabled": True,
                       "minimum_factor": None, "maximum_factor": None}], timeout=30)
        data = {d["category"]: d for d in api.get(f"{base_url}/admin/pressure-factors", timeout=30).json()}
        assert data["vessel"]["pressure_exponent"] == 0.55

    def test_put_negative_exponent(self, api, base_url):
        r = api.put(f"{base_url}/admin/pressure-factors",
                    json=[{"category": "vessel", "pressure_exponent": -0.1, "enabled": True}], timeout=30)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"


# ---------------------------------------------------------------
# ADMIN: similarity settings
# ---------------------------------------------------------------
class TestSimilaritySettings:
    def test_get(self, api, base_url):
        r = api.get(f"{base_url}/admin/similarity-settings", timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ("alpha", "beta", "gamma", "w_size", "w_subtype", "w_material", "w_pressure",
                  "min_similarity", "max_references", "min_references", "max_extrapolation_ratio",
                  "atmospheric_pressure_bar", "defaults"):
            assert k in d, f"missing {k}"
        assert abs(d["w_size"] + d["w_subtype"] + d["w_material"] + d["w_pressure"] - 1.0) < 0.01
        assert d["defaults"]["alpha"] == 1.0

    def test_put_weights_not_summing(self, api, base_url, sim_defaults):
        bad = dict(sim_defaults); bad["w_size"] = 0.9
        r = api.put(f"{base_url}/admin/similarity-settings", json=bad, timeout=30)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"

    def test_put_alpha_non_positive(self, api, base_url, sim_defaults):
        bad = dict(sim_defaults); bad["alpha"] = 0
        r = api.put(f"{base_url}/admin/similarity-settings", json=bad, timeout=30)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"

    def test_put_min_similarity_out_of_range(self, api, base_url, sim_defaults):
        bad = dict(sim_defaults); bad["min_similarity"] = 1.5
        r = api.put(f"{base_url}/admin/similarity-settings", json=bad, timeout=30)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"

    def test_put_valid_roundtrip(self, api, base_url, sim_defaults):
        good = dict(sim_defaults); good["beta"] = 0.55
        r = api.put(f"{base_url}/admin/similarity-settings", json=good, timeout=30)
        assert r.status_code == 200, r.text
        assert api.get(f"{base_url}/admin/similarity-settings", timeout=30).json()["beta"] == 0.55
        api.put(f"{base_url}/admin/similarity-settings", json=sim_defaults, timeout=30)
        assert api.get(f"{base_url}/admin/similarity-settings", timeout=30).json()["beta"] == sim_defaults["beta"]

    # kept in this class so all global similarity-config mutations run in a single xdist worker
    def test_insufficient_similarity_exclusion(self, api, base_url, sim_defaults):
        strict = dict(sim_defaults); strict["min_similarity"] = 0.99
        assert api.put(f"{base_url}/admin/similarity-settings", json=strict, timeout=30).status_code == 200
        try:
            r = api.post(f"{base_url}/estimate", json={
                "category": "column", "size": 50, "weight_kg": 1000000,
                "material": "stainless_steel_316", "design_pressure_bar": 10,
                "target_year": 2026, "output_currency": "EUR",
            }, timeout=60)
            assert r.status_code == 200, r.text
            d = r.json()
            assert "excluded_references" not in d, "legacy key name must be gone"
            excl = d.get("references_excluded") or []
            assert any("insufficient similarity" in (e.get("exclusion_reason") or "") for e in excl), \
                f"no similarity exclusion found: {excl}"
            # all refs excluded -> estimate not available, nulls not zeros
            assert d["estimate_available"] is False, d
            assert d["expected"] is None and d["low"] is None and d["high"] is None
            assert d.get("errors")
        finally:
            restored = api.put(f"{base_url}/admin/similarity-settings", json=sim_defaults, timeout=30)
            assert restored.status_code == 200
            assert api.get(f"{base_url}/admin/similarity-settings", timeout=30).json()["min_similarity"] \
                == sim_defaults["min_similarity"]


# ---------------------------------------------------------------
# ESTIMATE: scaling variables
# ---------------------------------------------------------------
class TestEstimateScaling:
    def test_column_primary_weight(self, api, base_url):
        r = api.post(f"{base_url}/estimate", json={
            "category": "column", "subtype": "Distillation packed", "size": 50,
            "weight_kg": 36000, "material": "stainless_steel_316",
            "design_pressure_bar": 10, "target_year": 2026, "output_currency": "EUR", "quantity": 1,
        }, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["estimate_available"] is True, d
        assert d["scaling_variable"] == "weight_kg"
        assert d["scaling_variable_is_fallback"] is False
        assert d["scaling_variable_value"] == 36000
        assert d["scaling_variable_unit"] == "kg"
        assert d["model_version"] == "weighted_similarity_v2"
        assert d["expected"] > 0 and d["low"] <= d["expected"] <= d["high"]
        assert len(d["references_detail"]) >= 1
        for ref in d["references_detail"]:
            for k in ("applied_material_factor", "applied_pressure_factor", "size_similarity",
                      "total_similarity", "normalized_weight", "weighted_contribution",
                      "cost_after_size_scaling", "cost_after_material_correction",
                      "cost_after_pressure_correction", "cost_after_escalation",
                      "cost_after_currency_conversion"):
                assert k in ref, f"references_detail missing {k}"
        assert "references_excluded" in d
        assert d["estimation_breakdown"]["primary_scaling_variable"] == "weight_kg"

    def test_column_fallback_no_weight(self, api, base_url):
        r = api.post(f"{base_url}/estimate", json={
            "category": "column", "size": 50, "material": "stainless_steel_316",
            "design_pressure_bar": 10, "target_year": 2026, "output_currency": "EUR",
        }, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        # iteration-3 fix: references are re-evaluated on the fallback variable
        excl = d.get("references_excluded") or []
        assert not any("incompatible scaling variable" in (e.get("exclusion_reason") or "") for e in excl), \
            f"references should no longer be excluded for fallback, got {excl}"
        warn_text = " ".join(d.get("warnings") or [])
        assert "Fallback variable used for target" in warn_text, f"warnings={d.get('warnings')}"
        assert d["estimate_available"] is True, d
        assert d["scaling_variable"] == "size"
        assert d["scaling_variable_is_fallback"] is True
        assert d["references_used"] > 0
        assert d["expected"] > 0

    def test_pump_power(self, api, base_url):
        r = api.post(f"{base_url}/estimate", json={
            "category": "pump", "subtype": "Centrifugal", "size": 100, "power_kw": 75,
            "material": "stainless_steel_316", "design_pressure_bar": 12,
            "target_year": 2026, "output_currency": "EUR",
        }, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["estimate_available"] is True, d
        assert d["scaling_variable"] == "power_kw"
        assert d["scaling_variable_is_fallback"] is False
        assert d["expected"] > 0
        # pressure disabled for pump
        assert d["pressure_factor_summary"]["enabled"] is False
        assert all(x == 1.0 for x in d["pressure_factor_summary"]["applied_pressure_factors"])

    def test_valve_size_mm(self, api, base_url):
        r = api.post(f"{base_url}/estimate", json={
            "category": "valve", "subtype": "Control", "size": 100,
            "material": "stainless_steel_316", "design_pressure_bar": 20,
            "target_year": 2026, "output_currency": "EUR",
        }, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["estimate_available"] is True, d
        assert d["scaling_variable"] == "size"
        assert d["scaling_variable_unit"] == "mm"
        assert d["expected"] > 0

    def test_unknown_category(self, api, base_url):
        r = api.post(f"{base_url}/estimate", json={
            "category": "spaceship", "size": 1, "material": "carbon_steel", "target_year": 2026,
        }, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["estimate_available"] is False
        assert d["errors"]


# ---------------------------------------------------------------
# ESTIMATE: mathematics
# ---------------------------------------------------------------
@pytest.fixture(scope="class")
def column_refs(api, base_url):
    docs = api.get(f"{base_url}/equipment", params={"category": "column"}, timeout=30).json()
    return {d.get("subtype"): d for d in docs}


class TestEstimateMath:
    def test_pressure_factor_formula(self, api, base_url, column_refs):
        ref = column_refs.get("Distillation packed")
        assert ref is not None, f"seed reference missing: {list(column_refs)}"
        assert ref["design_pressure_bar"] == 8
        r = api.post(f"{base_url}/estimate", json={
            "category": "column", "size": 60, "weight_kg": 38000,
            "material": "stainless_steel_316", "design_pressure_bar": 25,
            "target_year": 2026, "output_currency": "EUR",
            "reference_ids": [ref["id"]],
        }, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["estimate_available"] is True, d
        det = d["references_detail"][0]
        atm = 1.01325
        expected_f = ((25 + atm) / (8 + atm)) ** 0.60
        assert abs(det["applied_pressure_factor"] - expected_f) / expected_f < 0.01, \
            f"applied={det['applied_pressure_factor']} expected={expected_f}"
        assert abs(det["reference_absolute_pressure_bara"] - (8 + atm)) < 1e-6
        assert abs(det["target_absolute_pressure_bara"] - (25 + atm)) < 1e-6
        assert det["pressure_exponent"] == 0.60

    def test_material_factor_formula(self, api, base_url, column_refs):
        ref = column_refs.get("Distillation tray")  # carbon_steel MF 1.0
        assert ref is not None
        assert ref["material"] == "carbon_steel"
        r = api.post(f"{base_url}/estimate", json={
            "category": "column", "size": 45, "weight_kg": 32000,
            "material": "stainless_steel_316", "design_pressure_bar": 12,
            "target_year": 2026, "output_currency": "EUR",
            "reference_ids": [ref["id"]],
        }, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        det = d["references_detail"][0]
        assert abs(det["applied_material_factor"] - 2.1) < 1e-6, det["applied_material_factor"]
        assert det["reference_material_coefficient"] == 1.0
        assert det["target_material_coefficient"] == 2.1
        # chain check: cost_after_material == cost_after_size * f_material
        assert abs(det["cost_after_material_correction"] -
                   det["cost_after_size_scaling"] * det["applied_material_factor"]) < 1e-3
        # size factor check (ratio 1 -> 1)
        assert abs(det["size_scaling_factor"] - 1.0) < 1e-9

    def test_weighted_average_and_neff(self, api, base_url):
        r = api.post(f"{base_url}/estimate", json={
            "category": "column", "size": 52, "weight_kg": 35000,
            "material": "stainless_steel_316", "design_pressure_bar": 10,
            "target_year": 2026, "output_currency": "EUR",
        }, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        refs = d["references_detail"]
        assert len(refs) == 2, f"expected 2 column refs used, got {len(refs)}"
        wsum = sum(x["normalized_weight"] for x in refs)
        assert abs(wsum - 1.0) < 0.01, wsum
        contrib = sum(x["weighted_contribution"] for x in refs)
        assert abs(contrib - d["expected"]) < 0.05 * max(1.0, abs(d["expected"])), \
            f"sum contrib={contrib} expected={d['expected']}"
        neff_calc = 1.0 / sum(x["normalized_weight"] ** 2 for x in refs)
        assert abs(d["effective_sample_size"] - neff_calc) < 0.01
        assert 1.5 <= d["effective_sample_size"] <= 2.0, d["effective_sample_size"]
        # sigma / range consistency
        assert abs((d["high"] - d["low"]) - 2 * 1.645 * d["sigma"]) < 1.0 or d["low"] == 0.0

    def test_quantity_scaling(self, api, base_url):
        payload = {
            "category": "column", "size": 52, "weight_kg": 35000,
            "material": "stainless_steel_316", "design_pressure_bar": 10,
            "target_year": 2026, "output_currency": "EUR", "quantity": 3,
        }
        d = api.post(f"{base_url}/estimate", json=payload, timeout=60).json()
        assert abs(d["total_expected"] - round(d["expected"] * 3, 2)) < 0.05


# ---------------------------------------------------------------
# ESTIMATE: exclusions
# ---------------------------------------------------------------
class TestExclusions:
    def test_vessel_category_has_references(self, api, base_url):
        r = api.post(f"{base_url}/estimate", json={
            "category": "vessel", "size": 20, "weight_kg": 15000,
            "material": "carbon_steel", "design_pressure_bar": 10,
            "target_year": 2026, "output_currency": "EUR",
        }, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["estimate_available"] is True, d
        assert d["references_used"] >= 1
        assert d["expected"] > 0


# ---------------------------------------------------------------
# ROWS
# ---------------------------------------------------------------
class TestRows:
    created = []

    def test_valve_power_sanitized(self, api, base_url, project):
        r = api.post(f"{base_url}/projects/{project['id']}/rows", json={
            "tag": "TEST_V1", "category": "valve", "subtype": "Control", "size": 100,
            "material": "stainless_steel_316", "design_pressure_bar": 20,
            "power_kw": 100, "quantity": 2,
        }, timeout=60)
        assert r.status_code == 200, r.text
        row = r.json()
        TestRows.created.append(row["id"])
        assert row["power_kw"] is None, f"power_kw should be sanitized, got {row['power_kw']}"
        assert row["size_unit"] == "mm"
        assert row["scaling_variable"] == "size"
        assert row["unit_expected_cost"] > 0
        assert row["model_version"] == "weighted_similarity_v2"

    def test_column_with_weight(self, api, base_url, project):
        r = api.post(f"{base_url}/projects/{project['id']}/rows", json={
            "tag": "TEST_C1", "category": "column", "subtype": "Distillation packed",
            "size": 50, "weight_kg": 36000, "material": "stainless_steel_316",
            "design_pressure_bar": 10, "design_temperature_c": 170, "quantity": 1,
        }, timeout=60)
        assert r.status_code == 200, r.text
        row = r.json()
        TestRows.created.append(row["id"])
        assert row["weight_kg"] == 36000
        assert row["scaling_variable"] == "weight_kg"
        assert row["scaling_variable_is_fallback"] is False
        assert row["unit_expected_cost"] > 0
        assert row["estimate_available"] is True
        assert row["references_detail"] and len(row["references_detail"]) >= 1
        assert row["total_expected_cost"] == pytest.approx(row["unit_expected_cost"], rel=1e-6)
        for k in ("scaling_variable_value", "scaling_variable_unit", "references_excluded",
                  "similarity_summary", "material_factor_summary", "pressure_factor_summary",
                  "estimation_breakdown"):
            assert k in row

    def test_column_fallback_row(self, api, base_url, project):
        r = api.post(f"{base_url}/projects/{project['id']}/rows", json={
            "tag": "TEST_C2", "category": "column", "size": 50,
            "material": "stainless_steel_316", "design_pressure_bar": 10, "quantity": 1,
        }, timeout=60)
        assert r.status_code == 200, r.text
        row = r.json()
        TestRows.created.append(row["id"])
        assert row["warnings"], "expected warnings for fallback row"
        warn = " ".join(row["warnings"])
        assert "Fallback" in warn or "fallback" in warn, warn
        if row["estimate_available"]:
            assert row["scaling_variable"] == "size"
            assert row["scaling_variable_is_fallback"] is True
        else:
            assert row["unit_expected_cost"] == 0.0
            assert row["scaling_variable"] is None

    def test_update_and_delete_row(self, api, base_url, project):
        r = api.post(f"{base_url}/projects/{project['id']}/rows", json={
            "tag": "TEST_P1", "category": "pump", "subtype": "Centrifugal", "size": 100,
            "power_kw": 75, "material": "stainless_steel_316", "quantity": 1,
        }, timeout=60)
        assert r.status_code == 200, r.text
        row = r.json()
        assert row["scaling_variable"] == "power_kw"
        first = row["unit_expected_cost"]
        assert first > 0
        u = api.put(f"{base_url}/projects/{project['id']}/rows/{row['id']}", json={
            "tag": "TEST_P1", "category": "pump", "subtype": "Centrifugal", "size": 100,
            "power_kw": 150, "material": "stainless_steel_316", "quantity": 2,
        }, timeout=60)
        assert u.status_code == 200, u.text
        upd = u.json()
        assert upd["power_kw"] == 150
        assert upd["unit_expected_cost"] > first, (first, upd["unit_expected_cost"])
        d = api.delete(f"{base_url}/projects/{project['id']}/rows/{row['id']}", timeout=30)
        assert d.status_code == 200
        assert api.delete(f"{base_url}/projects/{project['id']}/rows/{row['id']}", timeout=30).status_code == 404

    def test_project_rows_fields_and_totals(self, api, base_url, project):
        r = api.get(f"{base_url}/projects/{project['id']}", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["project"]["aace_class"] == "Class 3"
        assert d["totals"]["aace_class"] == "Class 3"
        assert d["rows"], "no rows in project"
        for row in d["rows"]:
            assert "_id" not in row
            for k in ("scaling_variable", "scaling_variable_value", "scaling_variable_unit",
                      "scaling_variable_is_fallback", "references_detail", "references_excluded",
                      "model_version"):
                assert k in row, f"row missing {k}"
            assert row["model_version"] == "weighted_similarity_v2"
        exp = round(sum(x["total_expected_cost"] for x in d["rows"]), 2)
        assert abs(d["totals"]["expected"] - exp) < 0.05

    def test_recompute(self, api, base_url, project):
        r = api.post(f"{base_url}/projects/{project['id']}/recompute", timeout=120)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True

    def test_row_on_missing_project(self, api, base_url):
        r = api.post(f"{base_url}/projects/does-not-exist/rows", json={
            "category": "valve", "size": 100, "material": "carbon_steel"}, timeout=30)
        assert r.status_code == 404


# ---------------------------------------------------------------
# PROJECTS / AACE
# ---------------------------------------------------------------
class TestProjects:
    def test_aace_explicit_lifecycle(self, api, base_url):
        c = api.post(f"{base_url}/projects", json={
            "name": "TEST_aace", "output_currency": "EUR", "target_year": 2026, "aace_class": "Class 3"},
            timeout=30)
        assert c.status_code == 200, c.text
        p = c.json()
        assert p["aace_class"] == "Class 3"
        try:
            u = api.put(f"{base_url}/projects/{p['id']}", json={"aace_class": "Class 2"}, timeout=30)
            assert u.status_code == 200, u.text
            assert u.json()["aace_class"] == "Class 2"
            g = api.get(f"{base_url}/projects/{p['id']}", timeout=30).json()
            assert g["project"]["aace_class"] == "Class 2"
            assert g["totals"]["aace_class"] == "Class 2"
            # new row inherits project aace_class
            row = api.post(f"{base_url}/projects/{p['id']}/rows", json={
                "category": "valve", "subtype": "Control", "size": 100,
                "material": "stainless_steel_316", "design_pressure_bar": 20, "quantity": 1}, timeout=60).json()
            assert row["aace_class"] == "Class 2", row["aace_class"]
        finally:
            api.delete(f"{base_url}/projects/{p['id']}", timeout=30)

    def test_invalid_aace_rejected(self, api, base_url):
        r = api.post(f"{base_url}/projects", json={"name": "TEST_bad", "aace_class": "Class 9"}, timeout=30)
        assert r.status_code == 422, r.status_code

    def test_get_missing_project(self, api, base_url):
        assert api.get(f"{base_url}/projects/nope-nope", timeout=30).status_code == 404

    def test_dummy_project_seeded(self, api, base_url):
        projects = api.get(f"{base_url}/projects", timeout=30).json()
        dummy = [p for p in projects if p["name"].startswith("DUMMY")]
        assert dummy, "DUMMY project not seeded"
        d = api.get(f"{base_url}/projects/{dummy[0]['id']}", timeout=30).json()
        assert len(d["rows"]) == 8, f"expected 8 seeded rows, got {len(d['rows'])}"
        cols = [r for r in d["rows"] if r["category"] == "column"]
        assert cols and cols[0]["weight_kg"] == 36000
        assert cols[0]["scaling_variable"] == "weight_kg"


# ---------------------------------------------------------------
# INDICES
# ---------------------------------------------------------------
class TestIndices:
    def test_indices_fred(self, api, base_url):
        r = api.get(f"{base_url}/indices", timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert d["source"] == "FRED", f"source={d['source']}"
        assert len(d["steel_by_year"]) > 10 and len(d["oil_by_year"]) > 10
