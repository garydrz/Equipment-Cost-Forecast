"""
Iteration 4 backend test suite for model_version = weighted_similarity_v3.

Covers: rigid category+subtype filter, controlled subtypes, burner category,
weighted sample sigma range, IQR outlier filter, pump multivariate scaling,
pump similarity, project sigma aggregation (rho_quantity / rho_between_rows),
configurable confidence level, pump admin configs, calculation_report.
"""
import math
import os

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
_base = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not _base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
API = _base.rstrip("/") + "/api"

MODEL_VERSION = "weighted_similarity_v3"
TIMEOUT = 60

# Isolated playground: category 'other' has zero seeded historical records
OTHER_CAT = "other"
OTHER_SUB = "User Defined"
BASE_YEAR = 2024
BASE_SIZE = 10.0
BASE_MAT = "carbon_steel"


# ------------------------------------------------------------------ helpers
def _session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def create_ref(api, cost, category=OTHER_CAT, subtype=OTHER_SUB, size=BASE_SIZE,
               material=BASE_MAT, year=BASE_YEAR, **extra):
    payload = {
        "category": category, "subtype": subtype, "size": size, "material": material,
        "year": year, "cost_original": cost, "currency": "EUR",
        "notes": "TEST_v3_temp_ref",
    }
    payload.update(extra)
    r = api.post(f"{API}/equipment", json=payload, timeout=TIMEOUT)
    assert r.status_code == 200, f"create ref failed {r.status_code} {r.text[:300]}"
    return r.json()["id"]


def estimate_other(api, size=BASE_SIZE, material=BASE_MAT, quantity=1):
    body = {"category": OTHER_CAT, "subtype": OTHER_SUB, "size": size, "material": material,
            "target_year": BASE_YEAR, "output_currency": "EUR", "quantity": quantity}
    r = api.post(f"{API}/estimate", json=body, timeout=TIMEOUT)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    return r.json()


LEGACY_KEYS = ("defaults", "confidence_z_map", "updated_at", "range_method",
               "w_subtype", "subtype_mismatch", "_id")


def put_sim(api, cfg, **overrides):
    body = dict(cfg)
    for k in LEGACY_KEYS:
        body.pop(k, None)
    body.update(overrides)
    return api.put(f"{API}/admin/similarity-settings", json=body, timeout=TIMEOUT)


# ------------------------------------------------------------------ fixtures
@pytest.fixture(scope="session")
def api():
    return _session()


@pytest.fixture(scope="session")
def sim_cfg(api):
    """Sanitized similarity settings (v3 shape) applied for the session and restored after.

    NOTE: the persisted config in Mongo is a stale v2 document (contains w_subtype /
    subtype_mismatch and w_size+w_material+w_pressure = 0.85), which the v3 PUT validator
    rejects. The fixture therefore normalises the weights so the remaining scenarios can be
    exercised; the defect itself is asserted in TestAdminSettingsIntegrity.
    """
    r = api.get(f"{API}/admin/similarity-settings", timeout=TIMEOUT)
    assert r.status_code == 200
    cfg = r.json()
    for k in LEGACY_KEYS:
        cfg.pop(k, None)
    if abs(cfg["w_size"] + cfg["w_material"] + cfg["w_pressure"] - 1.0) > 0.01:
        cfg["w_size"], cfg["w_material"], cfg["w_pressure"] = 0.70, 0.20, 0.10
    pr = put_sim(api, cfg)
    assert pr.status_code == 200, f"could not apply sanitized config: {pr.text[:300]}"
    yield cfg
    put_sim(api, cfg)


@pytest.fixture
def three_other_refs(api):
    """3 identical-geometry refs with costs 100k/200k/300k -> equal similarity weights."""
    ids = [create_ref(api, c) for c in (100000.0, 200000.0, 300000.0)]
    yield ids
    for i in ids:
        api.delete(f"{API}/equipment/{i}", timeout=TIMEOUT)


# ================================================================== META
class TestMeta:
    def test_root(self, api):
        r = api.get(f"{API}/", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["model_version"] == MODEL_VERSION

    def test_categories_subtypes_and_confidence(self, api):
        r = api.get(f"{API}/meta/categories", timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d["model_version"] == MODEL_VERSION
        assert "subtypes" in d
        st = d["subtypes"]
        assert len(st) == 11, f"expected 11 categories, got {len(st)}"
        assert "burner" in st and st["burner"] == ["Process Burner", "Boiler Burner", "Duct Burner", "Flare Burner"]
        assert st["column"] == ["Tray", "Packed"]
        assert st["pump"] == ["Centrifugal", "Positive Displacement"]
        assert sorted(d["confidence_levels"]) == sorted(["68.27", "80.00", "90.00", "95.00", "99.00"])
        assert d["confidence_z_map"]["90.00"] == 1.645
        assert d["confidence_z_map"]["95.00"] == 1.960
        assert d["confidence_z_map"]["99.00"] == 2.576
        # burner meta
        assert d["meta"]["burner"]["primary_variable"] == "thermal_duty_kw"


# ================================================================== ADMIN SETTINGS INTEGRITY
class TestAdminSettingsIntegrity:
    """Persisted similarity config must be valid for the v3 model."""

    def test_stored_weights_sum_to_one(self, api):
        cfg = api.get(f"{API}/admin/similarity-settings", timeout=TIMEOUT).json()
        s = cfg["w_size"] + cfg["w_material"] + cfg["w_pressure"]
        assert abs(s - 1.0) <= 0.01, (
            f"stored similarity weights sum to {s} (w_size={cfg['w_size']}, "
            f"w_material={cfg['w_material']}, w_pressure={cfg['w_pressure']}) - "
            "stale v2 config not migrated to v3")

    def test_removed_v2_keys_absent(self, api):
        cfg = api.get(f"{API}/admin/similarity-settings", timeout=TIMEOUT).json()
        stale = [k for k in ("w_subtype", "subtype_mismatch") if k in cfg]
        assert not stale, f"removed v2 keys still returned by GET: {stale}"

    def test_get_put_roundtrip(self, api):
        cfg = api.get(f"{API}/admin/similarity-settings", timeout=TIMEOUT).json()
        body = {k: v for k, v in cfg.items() if k not in ("defaults", "confidence_z_map", "updated_at")}
        r = api.put(f"{API}/admin/similarity-settings", json=body, timeout=TIMEOUT)
        assert r.status_code == 200, (
            f"GET->PUT round-trip of the admin settings fails: {r.status_code} {r.text[:200]}")


# ================================================================== SUBTYPE VALIDATION
class TestSubtypeValidation:
    def test_legacy_subtype_rejected(self, api):
        r = api.post(f"{API}/equipment", json={
            "category": "column", "subtype": "Distillation tray", "size": 40,
            "material": "carbon_steel", "year": 2020, "cost_original": 100000, "currency": "EUR"},
            timeout=TIMEOUT)
        if r.status_code == 200:
            api.delete(f"{API}/equipment/{r.json()['id']}", timeout=TIMEOUT)
        assert r.status_code == 400, (
            f"legacy subtype 'Distillation tray' should be rejected with 400, got {r.status_code} "
            f"body={r.text[:200]}")

    def test_missing_subtype_rejected(self, api):
        r = api.post(f"{API}/equipment", json={
            "category": "column", "size": 40, "material": "carbon_steel",
            "year": 2020, "cost_original": 100000, "currency": "EUR"}, timeout=TIMEOUT)
        assert r.status_code in (400, 422), r.text[:200]

    def test_canonical_subtype_accepted(self, api):
        r = api.post(f"{API}/equipment", json={
            "category": "column", "subtype": "Tray", "size": 40, "weight_kg": 30000,
            "material": "carbon_steel", "design_pressure_bar": 10, "year": 2020,
            "cost_original": 400000, "currency": "EUR", "notes": "TEST_v3_temp_ref"}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["subtype"] == "Tray"
        assert d["size_unit"] == "m3"
        got = api.get(f"{API}/equipment", params={"category": "column", "subtype": "Tray"}, timeout=TIMEOUT).json()
        assert any(x["id"] == d["id"] for x in got)
        api.delete(f"{API}/equipment/{d['id']}", timeout=TIMEOUT)

    def test_pump_ref_with_flow_and_head(self, api):
        r = api.post(f"{API}/equipment", json={
            "category": "pump", "subtype": "Centrifugal", "size": 80, "material": "carbon_steel",
            "flow_rate_m3_h": 80, "head_m": 40, "pump_efficiency": 0.7, "fluid_density_kg_m3": 990,
            "year": 2020, "cost_original": 40000, "currency": "EUR", "notes": "TEST_v3_temp_ref"},
            timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["flow_rate_m3_h"] == 80 and d["head_m"] == 40
        assert d["pump_efficiency"] == 0.7 and d["fluid_density_kg_m3"] == 990
        api.delete(f"{API}/equipment/{d['id']}", timeout=TIMEOUT)

    def test_pump_efficiency_bounds(self, api):
        r = api.post(f"{API}/equipment", json={
            "category": "pump", "subtype": "Centrifugal", "size": 80, "material": "carbon_steel",
            "flow_rate_m3_h": 80, "head_m": 40, "pump_efficiency": 1.4,
            "year": 2020, "cost_original": 40000, "currency": "EUR"}, timeout=TIMEOUT)
        assert r.status_code == 422, r.text[:200]

    def test_migrate_subtypes(self, api):
        r = api.post(f"{API}/equipment/migrate-subtypes", timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "updated" in d and "needs_review" in d
        assert isinstance(d["needs_review"], list)
        assert d["needs_review"] == [], f"records needing review: {d['needs_review']}"


# ================================================================== RIGID FILTER
class TestRigidFilter:
    def test_subtype_isolation(self, api):
        """column/Packed estimate must not pull in column/Tray references."""
        r = api.post(f"{API}/estimate", json={
            "category": "column", "subtype": "Packed", "size": 60, "weight_kg": 38000,
            "material": "stainless_steel_316", "design_pressure_bar": 8,
            "target_year": 2025, "output_currency": "EUR"}, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d["estimate_available"] is True, d.get("errors")
        assert d["candidate_references"] == 1, d["candidate_references"]
        for ref in d["references_detail"]:
            assert ref["subtype"] == "Packed"
        for ref in d["references_excluded"]:
            assert "subtype mismatch" not in str(ref.get("exclusion_reason"))

    def test_no_references_for_combo(self, api):
        r = api.post(f"{API}/estimate", json={
            "category": "valve", "subtype": "SDV", "size": 100, "material": "carbon_steel",
            "design_pressure_bar": 10, "target_year": 2025, "output_currency": "EUR"}, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d["estimate_available"] is False
        assert "No historical references available for the selected category and subtype" in d["errors"]

    def test_unavailable_payload_shape(self, api):
        d = api.post(f"{API}/estimate", json={
            "category": "valve", "subtype": "TRV", "size": 100, "material": "carbon_steel",
            "target_year": 2025, "output_currency": "EUR"}, timeout=TIMEOUT).json()
        assert d["estimate_available"] is False
        for k in ("expected", "low", "high", "sigma_population", "sigma_sample", "sigma_used_for_range"):
            assert d[k] is None, f"{k} should be None, got {d[k]}"
        assert d["references_used"] == 0
        assert "references_excluded" in d and "excluded_references" not in d
        assert d["model_version"] == MODEL_VERSION


# ================================================================== WEIGHTED STATS
class TestWeightedStats:
    def test_single_reference_no_range(self, api):
        rid = create_ref(api, 150000.0)
        try:
            d = estimate_other(api)
            assert d["estimate_available"] is True, d.get("errors")
            assert d["references_used"] == 1
            assert d["expected"] == pytest.approx(150000.0, rel=0.001)
            assert d["sigma_sample"] is None
            assert d["low"] is None and d["high"] is None
            assert "Insufficient independent historical references to calculate a reliability range" in d["warnings"]
            assert d["sigma_population"] == pytest.approx(0.0, abs=1e-6)
        finally:
            api.delete(f"{API}/equipment/{rid}", timeout=TIMEOUT)

    def test_two_references_unbiased_sigma(self, api, sim_cfg):
        assert str(sim_cfg["confidence_level"]) == "90.00"
        ids = [create_ref(api, 100000.0), create_ref(api, 200000.0)]
        try:
            d = estimate_other(api)
            assert d["references_used"] == 2
            assert d["expected"] == pytest.approx(150000.0, rel=0.001)
            # equal weights: var_pop = (d/2)^2 ; denom = 0.5 ; sigma = |d|/sqrt(2)
            expected_sigma = 100000.0 / math.sqrt(2)
            assert d["sigma_sample"] == pytest.approx(expected_sigma, rel=0.01), d["sigma_sample"]
            z = 1.645
            assert d["z_value"] == z
            assert d["low"] == pytest.approx(max(0.0, 150000.0 - z * expected_sigma), rel=0.01)
            assert d["high"] == pytest.approx(150000.0 + z * expected_sigma, rel=0.01)
            assert d["sigma_used_for_range"] == pytest.approx(d["sigma_sample"], rel=1e-6)
        finally:
            for i in ids:
                api.delete(f"{API}/equipment/{i}", timeout=TIMEOUT)

    def test_three_references_numeric(self, api, three_other_refs):
        d = estimate_other(api)
        assert d["references_used"] == 3
        assert d["expected"] == pytest.approx(200000.0, rel=0.001)
        assert d["sigma_sample"] == pytest.approx(100000.0, rel=0.05), d["sigma_sample"]
        assert d["effective_sample_size"] == pytest.approx(3.0, rel=0.01)
        assert d["low"] == pytest.approx(200000.0 - 1.645 * 100000.0, rel=0.02)
        assert d["high"] == pytest.approx(200000.0 + 1.645 * 100000.0, rel=0.02)
        # weights normalized + expected == sum(weighted contributions)
        wsum = sum(u["normalized_weight"] for u in d["references_detail"])
        assert wsum == pytest.approx(1.0, abs=0.01)
        contrib = sum(u["weighted_contribution"] for u in d["references_detail"])
        assert contrib == pytest.approx(d["expected"], rel=0.001)
        # n<4 -> IQR not applied
        assert "IQR outlier filtering not applied: fewer than four valid references" in d["warnings"]
        assert d["outlier_summary"]["applied"] is False
        assert d["outlier_summary"]["outliers_removed"] == 0

    def test_low_clamped_at_zero(self, api):
        """Wide spread must clamp low to 0, never negative."""
        ids = [create_ref(api, c) for c in (10000.0, 900000.0)]
        try:
            d = estimate_other(api)
            assert d["low"] == 0.0, d["low"]
        finally:
            for i in ids:
                api.delete(f"{API}/equipment/{i}", timeout=TIMEOUT)

    def test_calculation_report_shape(self, api, three_other_refs):
        d = estimate_other(api)
        rep = d["calculation_report"]
        assert rep is not None
        for k in ("equipment_description", "historical_basis", "estimation_method",
                  "equation_used", "most_influential_references", "reliability_assessment", "warnings"):
            assert k in rep, f"missing {k}"
        em = rep["estimation_method"]
        assert isinstance(em["cost_corrections_applied"], list) and len(em["cost_corrections_applied"]) >= 5
        assert em["reliability_range"]["confidence_level_percent"] == "90.00"
        assert em["reliability_range"]["z_value"] == 1.645
        assert len(rep["most_influential_references"]) <= 5
        assert all("weight_percent" in r for r in rep["most_influential_references"])
        assert rep["reliability_assessment"]["effective_sample_size"] == pytest.approx(3.0, rel=0.01)


# ================================================================== IQR
class TestIQR:
    def test_outlier_removed_and_weights_renormalized(self, api):
        costs = [100000.0, 105000.0, 110000.0, 115000.0, 500000.0]
        ids = [create_ref(api, c) for c in costs]
        try:
            d = estimate_other(api)
            os_ = d["outlier_summary"]
            assert os_["applied"] is True, os_
            assert os_["references_before_filter"] == 5
            assert os_["outliers_removed"] == 1, os_
            assert d["references_used"] == 4
            assert os_["q1"] == pytest.approx(105000.0, rel=0.001)
            assert os_["q3"] == pytest.approx(115000.0, rel=0.001)
            assert os_["iqr"] == pytest.approx(10000.0, rel=0.001)
            assert os_["upper_fence"] == pytest.approx(130000.0, rel=0.001)
            out = [e for e in d["references_excluded"]
                   if e.get("exclusion_reason") == "Adjusted cost outside IQR fences"]
            assert len(out) == 1, d["references_excluded"]
            for k in ("Q1", "Q3", "IQR", "lower_fence", "upper_fence", "IQR_multiplier"):
                assert k in out[0], f"missing {k} in outlier record"
            assert out[0]["adjusted_cost"] == pytest.approx(500000.0, rel=0.01)
            # weights re-normalized AFTER removal
            wsum = sum(u["normalized_weight"] for u in d["references_detail"])
            assert wsum == pytest.approx(1.0, abs=0.01)
            contrib = sum(u["weighted_contribution"] for u in d["references_detail"])
            assert contrib == pytest.approx(d["expected"], rel=0.001)
            assert d["expected"] == pytest.approx(107500.0, rel=0.01), d["expected"]
        finally:
            for i in ids:
                api.delete(f"{API}/equipment/{i}", timeout=TIMEOUT)

    def test_iqr_multiplier_configurable(self, api, sim_cfg):
        costs = [100000.0, 105000.0, 110000.0, 115000.0, 500000.0]
        ids = [create_ref(api, c) for c in costs]
        try:
            r = put_sim(api, sim_cfg, iqr_multiplier=50.0)
            assert r.status_code == 200, r.text[:300]
            d = estimate_other(api)
            assert d["outlier_summary"]["iqr_multiplier"] == 50.0
            assert d["outlier_summary"]["outliers_removed"] == 0, "huge multiplier must keep all refs"
            assert d["references_used"] == 5
        finally:
            put_sim(api, sim_cfg)
            for i in ids:
                api.delete(f"{API}/equipment/{i}", timeout=TIMEOUT)


    def test_iqr_minimum_references_configurable(self, api, sim_cfg):
        """minimum_references_for_iqr=3 must let the filter run with only 3 refs."""
        ids = [create_ref(api, c) for c in (100000.0, 105000.0, 500000.0)]
        try:
            r = put_sim(api, sim_cfg, minimum_references_for_iqr=3)
            assert r.status_code == 200, r.text[:300]
            d = estimate_other(api)
            assert d["outlier_summary"]["minimum_references_for_iqr"] == 3
            assert d["outlier_summary"]["applied"] is True
            assert not any("fewer than four valid references" in w for w in d["warnings"])
        finally:
            put_sim(api, sim_cfg)
            for i in ids:
                api.delete(f"{API}/equipment/{i}", timeout=TIMEOUT)


# ================================================================== MANUAL REFERENCES
class TestManualReferences:
    def test_manual_reference_wrong_subtype_excluded(self, api):
        """reference_ids must still respect the rigid category+subtype filter."""
        eq = api.get(f"{API}/equipment", params={"category": "column"}, timeout=TIMEOUT).json()
        tray = [e for e in eq if e["subtype"] == "Tray"][0]
        packed = [e for e in eq if e["subtype"] == "Packed"][0]
        d = api.post(f"{API}/estimate", json={
            "category": "column", "subtype": "Packed", "size": 60, "weight_kg": 38000,
            "material": "stainless_steel_316", "design_pressure_bar": 8, "target_year": 2025,
            "output_currency": "EUR", "reference_ids": [tray["id"], packed["id"]]}, timeout=TIMEOUT).json()
        assert d["estimate_available"] is True, d.get("errors")
        assert d["references_used"] == 1
        assert d["references_detail"][0]["historical_equipment_id"] == packed["id"]
        assert any(e.get("historical_equipment_id") == tray["id"] and
                   "subtype mismatch" in str(e.get("exclusion_reason"))
                   for e in d["references_excluded"]), d["references_excluded"]

    def test_manual_reference_only_wrong_subtype(self, api):
        eq = api.get(f"{API}/equipment", params={"category": "column"}, timeout=TIMEOUT).json()
        tray = [e for e in eq if e["subtype"] == "Tray"][0]
        d = api.post(f"{API}/estimate", json={
            "category": "column", "subtype": "Packed", "size": 60, "weight_kg": 38000,
            "material": "stainless_steel_316", "design_pressure_bar": 8, "target_year": 2025,
            "output_currency": "EUR", "reference_ids": [tray["id"]]}, timeout=TIMEOUT).json()
        assert d["estimate_available"] is False
        assert d["errors"], d
        assert d["expected"] is None and d["low"] is None and d["high"] is None


# ================================================================== CONFIDENCE LEVEL
class TestConfidenceLevel:
    def test_z_switching(self, api, sim_cfg, three_other_refs):
        try:
            for level, z in (("95.00", 1.960), ("99.00", 2.576), ("68.27", 1.000)):
                r = put_sim(api, sim_cfg, confidence_level=level)
                assert r.status_code == 200, r.text[:300]
                g = api.get(f"{API}/admin/similarity-settings", timeout=TIMEOUT).json()
                assert g["confidence_level"] == level
                assert g["z_value"] == z
                d = estimate_other(api)
                assert d["z_value"] == z
                assert d["confidence_level"] == level
                assert d["low"] == pytest.approx(max(0.0, d["expected"] - z * d["sigma_sample"]), rel=0.01)
                assert d["high"] == pytest.approx(d["expected"] + z * d["sigma_sample"], rel=0.01)
        finally:
            put_sim(api, sim_cfg)

    def test_arbitrary_z_ignored(self, api, sim_cfg):
        try:
            r = put_sim(api, sim_cfg, confidence_level="90.00", z_value=9.99)
            assert r.status_code == 200, r.text[:300]
            g = api.get(f"{API}/admin/similarity-settings", timeout=TIMEOUT).json()
            assert g["z_value"] == 1.645, g["z_value"]
        finally:
            put_sim(api, sim_cfg)

    def test_invalid_confidence_level_rejected(self, api, sim_cfg):
        r = put_sim(api, sim_cfg, confidence_level="97.50")
        assert r.status_code in (400, 422), f"got {r.status_code} {r.text[:200]}"


# ================================================================== PUMP
class TestPump:
    def test_missing_flow_rejected(self, api):
        d = api.post(f"{API}/estimate", json={
            "category": "pump", "subtype": "Centrifugal", "size": 100, "head_m": 45,
            "material": "stainless_steel_316", "target_year": 2025, "output_currency": "EUR"},
            timeout=TIMEOUT).json()
        assert d["estimate_available"] is False
        assert "pump target flow_rate_m3_h is required" in d["errors"], d["errors"]

    def test_missing_head_rejected(self, api):
        d = api.post(f"{API}/estimate", json={
            "category": "pump", "subtype": "Centrifugal", "flow_rate_m3_h": 100,
            "material": "stainless_steel_316", "target_year": 2025, "output_currency": "EUR"},
            timeout=TIMEOUT).json()
        assert d["estimate_available"] is False
        assert "pump target head_m is required" in d["errors"], d["errors"]

    def test_multivariate_breakdown(self, api):
        d = api.post(f"{API}/estimate", json={
            "category": "pump", "subtype": "Centrifugal", "flow_rate_m3_h": 100, "head_m": 45,
            "power_kw": 75, "material": "stainless_steel_316", "target_year": 2025,
            "output_currency": "EUR"}, timeout=TIMEOUT).json()
        assert d["estimate_available"] is True, d.get("errors")
        assert "(Q_target/Q_ref)^a × (H_target/H_ref)^b × (P_target/P_ref)^c" in d["calculation_formula"]
        assert d["pump_scaling_summary"] is not None
        ps = d["pump_scaling_summary"]
        assert ps["subtype"] == "Centrifugal"
        for k in ("flow_exponent_a", "head_exponent_b", "power_exponent_c", "power_missing_policy"):
            assert k in ps
        assert d["pressure_factor_summary"]["enabled"] is False, "pressure must be disabled for pump"
        for ref in d["references_detail"]:
            pb = ref["pump_breakdown"]
            assert pb is not None
            for k in ("flow_target", "flow_ref", "F_flow", "head_target", "head_ref", "F_head",
                      "power_target", "power_ref", "F_power", "F_pump", "power_used",
                      "power_policy", "renormalization_note"):
                assert k in pb, f"missing {k} in pump_breakdown"
            a, b, c = pb["flow_exponent_a"], pb["head_exponent_b"], pb["power_exponent_c"]
            exp_ff = (pb["flow_target"] / pb["flow_ref"]) ** a
            exp_fh = (pb["head_target"] / pb["head_ref"]) ** b
            assert pb["F_flow"] == pytest.approx(exp_ff, rel=1e-6)
            assert pb["F_head"] == pytest.approx(exp_fh, rel=1e-6)
            if pb["power_used"]:
                exp_fp = (pb["power_target"] / pb["power_ref"]) ** c
                assert pb["F_power"] == pytest.approx(exp_fp, rel=1e-6)
            else:
                assert pb["F_power"] == 1.0
            assert pb["F_pump"] == pytest.approx(pb["F_flow"] * pb["F_head"] * pb["F_power"], rel=1e-6)
            assert ref["size_scaling_factor"] == pytest.approx(pb["F_pump"], rel=1e-6)
            assert ref["pressure_similarity"] is None, "pressure similarity must be disabled for pump"
            assert ref["cost_after_size_scaling"] == pytest.approx(ref["original_cost"] * pb["F_pump"], rel=1e-6)

    def test_reference_without_power(self, api):
        """Target has power, one reference does not -> power dropped for that ref only."""
        rid = create_ref(api, 41000.0, category="pump", subtype="Centrifugal", size=85,
                         material="stainless_steel_316", flow_rate_m3_h=85, head_m=42)
        try:
            d = api.post(f"{API}/estimate", json={
                "category": "pump", "subtype": "Centrifugal", "flow_rate_m3_h": 100, "head_m": 45,
                "power_kw": 75, "material": "stainless_steel_316", "target_year": 2025,
                "output_currency": "EUR"}, timeout=TIMEOUT).json()
            assert d["estimate_available"] is True
            target = [r for r in d["references_detail"] if r["historical_equipment_id"] == rid]
            assert target, "temp ref not used"
            pb = target[0]["pump_breakdown"]
            assert pb["power_used"] is False
            assert pb["F_power"] == 1.0
            assert pb["power_ratio"] is None
            assert pb["power_policy"] == "optional_and_renormalize"
            assert pb["renormalization_note"] is None, "renormalization disabled by default"
            msg = "Power term excluded because comparable power data are unavailable"
            assert d["warnings"].count(msg) == 1, d["warnings"]
            # refs that do have power still use it
            assert any(r["pump_breakdown"]["power_used"] for r in d["references_detail"])
        finally:
            api.delete(f"{API}/equipment/{rid}", timeout=TIMEOUT)

    def test_no_power_anywhere(self, api):
        d = api.post(f"{API}/estimate", json={
            "category": "pump", "subtype": "Centrifugal", "flow_rate_m3_h": 100, "head_m": 45,
            "material": "stainless_steel_316", "target_year": 2025, "output_currency": "EUR"},
            timeout=TIMEOUT).json()
        assert d["estimate_available"] is True, d.get("errors")
        for ref in d["references_detail"]:
            assert ref["pump_breakdown"]["power_used"] is False
            assert ref["pump_breakdown"]["F_power"] == 1.0
        msg = "Power term excluded because comparable power data are unavailable"
        assert d["warnings"].count(msg) == 1, d["warnings"]

    def test_pump_similarity_composition(self, api, sim_cfg):
        d = api.post(f"{API}/estimate", json={
            "category": "pump", "subtype": "Centrifugal", "flow_rate_m3_h": 100, "head_m": 45,
            "power_kw": 75, "material": "stainless_steel_316", "target_year": 2025,
            "output_currency": "EUR"}, timeout=TIMEOUT).json()
        wq, wh, wp = sim_cfg["pump_w_Q"], sim_cfg["pump_w_H"], sim_cfg["pump_w_P"]
        dw, mw = sim_cfg["pump_duty_weight"], sim_cfg["pump_material_weight"]
        aq, ah, ap = sim_cfg["pump_alpha_Q"], sim_cfg["pump_alpha_H"], sim_cfg["pump_alpha_P"]
        beta = sim_cfg["beta"]
        for ref in d["references_detail"]:
            pb = ref["pump_breakdown"]
            s_q = math.exp(-aq * abs(math.log(pb["flow_target"] / pb["flow_ref"])))
            s_h = math.exp(-ah * abs(math.log(pb["head_target"] / pb["head_ref"])))
            comps = [(wq, s_q), (wh, s_h)]
            if pb["power_used"]:
                s_p = math.exp(-ap * abs(math.log(pb["power_target"] / pb["power_ref"])))
                comps.append((wp, s_p))
            tw = sum(w for w, _ in comps)
            s_duty = sum((w / tw) * s for w, s in comps)
            s_mat = math.exp(-beta * abs(math.log(
                ref["target_material_coefficient"] / ref["reference_material_coefficient"])))
            expected = (dw * s_duty + mw * s_mat) / (dw + mw)
            assert ref["total_similarity"] == pytest.approx(expected, rel=1e-4), (
                ref["total_similarity"], expected)
            assert ref["size_similarity"] == pytest.approx(s_duty, rel=1e-4)

    def test_pump_configs_admin(self, api):
        r = api.get(f"{API}/admin/pump-configs", timeout=TIMEOUT)
        assert r.status_code == 200
        cfgs = r.json()
        assert len(cfgs) == 2
        subs = {c["subtype"] for c in cfgs}
        assert subs == {"Centrifugal", "Positive Displacement"}
        for c in cfgs:
            for k in ("a", "b", "c", "default_a", "default_b", "default_c"):
                assert k in c
        original = [{"subtype": c["subtype"], "a": c["a"], "b": c["b"], "c": c["c"],
                     "source": c.get("source"), "notes": c.get("notes")} for c in cfgs]
        try:
            upd = [dict(o) for o in original]
            upd[0].update({"a": 0.55, "b": 0.25, "c": 0.15})
            r = api.put(f"{API}/admin/pump-configs", json=upd, timeout=TIMEOUT)
            assert r.status_code == 200, r.text[:300]
            got = api.get(f"{API}/admin/pump-configs", timeout=TIMEOUT).json()
            hit = [c for c in got if c["subtype"] == upd[0]["subtype"]][0]
            assert hit["a"] == 0.55 and hit["b"] == 0.25 and hit["c"] == 0.15
            # estimate must use the new exponents
            d = api.post(f"{API}/estimate", json={
                "category": "pump", "subtype": "Centrifugal", "flow_rate_m3_h": 100, "head_m": 45,
                "power_kw": 75, "material": "stainless_steel_316", "target_year": 2025,
                "output_currency": "EUR"}, timeout=TIMEOUT).json()
            if upd[0]["subtype"] == "Centrifugal":
                assert d["pump_scaling_summary"]["flow_exponent_a"] == 0.55
        finally:
            api.put(f"{API}/admin/pump-configs", json=original, timeout=TIMEOUT)

    def test_invalid_pump_subtype_config(self, api):
        r = api.put(f"{API}/admin/pump-configs", json=[{"subtype": "Nope", "a": 0.3, "b": 0.2, "c": 0.3}],
                    timeout=TIMEOUT)
        assert r.status_code == 400, r.text[:200]


# ================================================================== BURNER
class TestBurner:
    def test_burner_estimate(self, api):
        d = api.post(f"{API}/estimate", json={
            "category": "burner", "subtype": "Process Burner", "thermal_duty_kw": 6000,
            "material": "carbon_steel", "target_year": 2025, "output_currency": "EUR"},
            timeout=TIMEOUT).json()
        assert d["estimate_available"] is True, d.get("errors")
        assert d["references_used"] == 2, d["references_used"]
        assert d["scaling_variable"] == "thermal_duty_kw"
        assert d["scaling_variable_value"] == 6000
        assert "Duty_target/Duty_ref" in d["calculation_formula"]
        assert d["expected"] > 0
        for ref in d["references_detail"]:
            assert ref["scaling_variable_name"] == "thermal_duty_kw"
            assert ref["size_scaling_factor"] > 0

    def test_burner_invalid_subtype(self, api):
        d = api.post(f"{API}/estimate", json={
            "category": "burner", "subtype": "Mega Burner", "thermal_duty_kw": 6000,
            "material": "carbon_steel", "target_year": 2025, "output_currency": "EUR"},
            timeout=TIMEOUT).json()
        assert d["estimate_available"] is False
        assert any("not allowed" in e for e in d["errors"]), d["errors"]


# ================================================================== ROWS / PROJECT
class TestRows:
    @pytest.fixture(scope="class")
    def proj(self, api):
        r = api.post(f"{API}/projects", json={"name": "TEST_v3_rows", "output_currency": "EUR",
                                              "target_year": BASE_YEAR, "aace_class": "Class 5"},
                     timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        p = r.json()
        yield p
        api.delete(f"{API}/projects/{p['id']}", timeout=TIMEOUT)

    def test_add_pump_row(self, api, proj):
        r = api.post(f"{API}/projects/{proj['id']}/rows", json={
            "tag": "TEST_P-1", "category": "pump", "subtype": "Centrifugal",
            "flow_rate_m3_h": 100, "head_m": 45, "power_kw": 75,
            "material": "stainless_steel_316", "quantity": 2}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:400]
        row = r.json()
        assert row["subtype"] == "Centrifugal"
        assert row["flow_rate_m3_h"] == 100 and row["head_m"] == 45
        assert row["unit_expected_cost"] > 0
        assert row["pump_scaling_summary"] is not None
        assert row["estimate_available"] is True
        assert row["model_version"] == MODEL_VERSION
        assert row["total_expected_cost"] == pytest.approx(row["unit_expected_cost"] * 2, rel=0.001)
        assert row["calculation_report"] is not None
        api.delete(f"{API}/projects/{proj['id']}/rows/{row['id']}", timeout=TIMEOUT)

    def test_invalid_row_subtype(self, api, proj):
        r = api.post(f"{API}/projects/{proj['id']}/rows", json={
            "tag": "TEST_BAD", "category": "pump", "subtype": "NotValid",
            "flow_rate_m3_h": 100, "head_m": 45, "material": "carbon_steel"}, timeout=TIMEOUT)
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"

    def test_burner_row(self, api, proj):
        r = api.post(f"{API}/projects/{proj['id']}/rows", json={
            "tag": "TEST_B-1", "category": "burner", "subtype": "Process Burner",
            "thermal_duty_kw": 6000, "material": "carbon_steel", "quantity": 1}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:400]
        row = r.json()
        assert row["thermal_duty_kw"] == 6000
        assert row["scaling_variable"] == "thermal_duty_kw"
        assert row["unit_expected_cost"] > 0
        api.delete(f"{API}/projects/{proj['id']}/rows/{row['id']}", timeout=TIMEOUT)

    def test_row_update_and_delete(self, api, proj):
        r = api.post(f"{API}/projects/{proj['id']}/rows", json={
            "tag": "TEST_C-1", "category": "column", "subtype": "Packed", "size": 60,
            "weight_kg": 38000, "material": "stainless_steel_316", "design_pressure_bar": 8,
            "quantity": 1}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:400]
        row = r.json()
        u = api.put(f"{API}/projects/{proj['id']}/rows/{row['id']}", json={
            "tag": "TEST_C-1", "category": "column", "subtype": "Packed", "size": 80,
            "weight_kg": 50000, "material": "stainless_steel_316", "design_pressure_bar": 8,
            "quantity": 3}, timeout=TIMEOUT)
        assert u.status_code == 200, u.text[:300]
        upd = u.json()
        assert upd["weight_kg"] == 50000 and upd["quantity"] == 3
        g = api.get(f"{API}/projects/{proj['id']}", timeout=TIMEOUT).json()
        stored = [x for x in g["rows"] if x["id"] == row["id"]][0]
        assert stored["weight_kg"] == 50000 and stored["quantity"] == 3
        d = api.delete(f"{API}/projects/{proj['id']}/rows/{row['id']}", timeout=TIMEOUT)
        assert d.status_code == 200
        g2 = api.get(f"{API}/projects/{proj['id']}", timeout=TIMEOUT).json()
        assert all(x["id"] != row["id"] for x in g2["rows"])

    def test_project_totals_keys(self, api):
        pid = api.get(f"{API}/projects", timeout=TIMEOUT).json()[-1]["id"]
        g = api.get(f"{API}/projects/{pid}", timeout=TIMEOUT).json()
        t = g["totals"]
        for k in ("expected", "sigma_project", "sigma", "low", "high", "confidence_level",
                  "z_value", "range_method", "rho_quantity", "rho_between_rows",
                  "rows_with_valid_sigma", "rows_without_valid_sigma", "warnings"):
            assert k in t, f"missing totals key {k}"
        assert t["range_method"] == "weighted_mean_plus_minus_z_sigma"
        assert t["sigma"] == t["sigma_project"]

    def test_recompute(self, api):
        pid = api.get(f"{API}/projects", timeout=TIMEOUT).json()[-1]["id"]
        r = api.post(f"{API}/projects/{pid}/recompute", timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["ok"] is True


# ================================================================== AGGREGATION
class TestProjectAggregation:
    @pytest.fixture(scope="class")
    def proj(self, api):
        r = api.post(f"{API}/projects", json={"name": "TEST_v3_agg", "output_currency": "EUR",
                                              "target_year": BASE_YEAR, "aace_class": "Class 5"},
                     timeout=TIMEOUT)
        p = r.json()
        yield p
        api.delete(f"{API}/projects/{p['id']}", timeout=TIMEOUT)

    def _add_other_row(self, api, pid, tag, qty):
        r = api.post(f"{API}/projects/{pid}/rows", json={
            "tag": tag, "category": OTHER_CAT, "subtype": OTHER_SUB, "size": BASE_SIZE,
            "material": BASE_MAT, "quantity": qty}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:400]
        return r.json()

    def test_rho_quantity_one(self, api, sim_cfg, three_other_refs, proj):
        row = self._add_other_row(api, proj["id"], "TEST_AGG_Q3", 3)
        try:
            put_sim(api, sim_cfg, rho_quantity=1.0, rho_between_rows=0.0)
            g = api.get(f"{API}/projects/{proj['id']}", timeout=TIMEOUT).json()
            t = g["totals"]
            s = row["unit_sigma"]
            assert s and s > 0, row["unit_sigma"]
            assert t["rho_quantity"] == 1.0
            assert t["sigma_project"] == pytest.approx(3 * s, rel=0.01), (t["sigma_project"], s)
            assert t["expected"] == pytest.approx(row["unit_expected_cost"] * 3, rel=0.01)
            assert t["low"] == pytest.approx(max(0.0, t["expected"] - t["z_value"] * t["sigma_project"]), rel=0.01)
            assert t["high"] == pytest.approx(t["expected"] + t["z_value"] * t["sigma_project"], rel=0.01)
        finally:
            put_sim(api, sim_cfg)
            api.delete(f"{API}/projects/{proj['id']}/rows/{row['id']}", timeout=TIMEOUT)

    def test_rho_quantity_zero(self, api, sim_cfg, three_other_refs, proj):
        row = self._add_other_row(api, proj["id"], "TEST_AGG_Q4", 4)
        try:
            put_sim(api, sim_cfg, rho_quantity=0.0, rho_between_rows=0.0)
            t = api.get(f"{API}/projects/{proj['id']}", timeout=TIMEOUT).json()["totals"]
            s = row["unit_sigma"]
            assert t["sigma_project"] == pytest.approx(2 * s, rel=0.01), (t["sigma_project"], s)
        finally:
            put_sim(api, sim_cfg)
            api.delete(f"{API}/projects/{proj['id']}/rows/{row['id']}", timeout=TIMEOUT)

    def test_rho_between_rows(self, api, sim_cfg, three_other_refs, proj):
        r1 = self._add_other_row(api, proj["id"], "TEST_AGG_R1", 1)
        r2 = self._add_other_row(api, proj["id"], "TEST_AGG_R2", 1)
        try:
            s1, s2 = r1["unit_sigma"], r2["unit_sigma"]
            put_sim(api, sim_cfg, rho_quantity=1.0, rho_between_rows=0.0)
            t0 = api.get(f"{API}/projects/{proj['id']}", timeout=TIMEOUT).json()["totals"]
            assert t0["sigma_project"] == pytest.approx(math.sqrt(s1 ** 2 + s2 ** 2), rel=0.01)
            put_sim(api, sim_cfg, rho_quantity=1.0, rho_between_rows=0.5)
            t5 = api.get(f"{API}/projects/{proj['id']}", timeout=TIMEOUT).json()["totals"]
            exp = math.sqrt(s1 ** 2 + s2 ** 2 + 2 * 0.5 * s1 * s2)
            assert t5["rho_between_rows"] == 0.5
            assert t5["sigma_project"] == pytest.approx(exp, rel=0.01), (t5["sigma_project"], exp)
        finally:
            put_sim(api, sim_cfg)
            for rr in (r1, r2):
                api.delete(f"{API}/projects/{proj['id']}/rows/{rr['id']}", timeout=TIMEOUT)

    def test_row_without_sigma_warning(self, api, proj):
        """Single reference row -> unit_sigma None -> project warning, partial policy."""
        rid = create_ref(api, 120000.0)
        row = self._add_other_row(api, proj["id"], "TEST_AGG_NOSIG", 1)
        try:
            assert row["unit_sigma"] is None, row["unit_sigma"]
            t = api.get(f"{API}/projects/{proj['id']}", timeout=TIMEOUT).json()["totals"]
            assert t["rows_without_valid_sigma"] >= 1
            assert any("no computable sigma" in w for w in t["warnings"]), t["warnings"]
        finally:
            api.delete(f"{API}/projects/{proj['id']}/rows/{row['id']}", timeout=TIMEOUT)
            api.delete(f"{API}/equipment/{rid}", timeout=TIMEOUT)


# ================================================================== AACE METADATA
class TestAACEMetadata:
    def test_aace_does_not_affect_range(self, api, three_other_refs):
        p = api.post(f"{API}/projects", json={"name": "TEST_v3_aace", "output_currency": "EUR",
                                              "target_year": BASE_YEAR, "aace_class": "Class 5"},
                     timeout=TIMEOUT).json()
        try:
            for tag, qty in (("TEST_A1", 2), ("TEST_A2", 1)):
                r = api.post(f"{API}/projects/{p['id']}/rows", json={
                    "tag": tag, "category": OTHER_CAT, "subtype": OTHER_SUB, "size": BASE_SIZE,
                    "material": BASE_MAT, "quantity": qty}, timeout=TIMEOUT)
                assert r.status_code == 200, r.text[:300]
            t1 = api.get(f"{API}/projects/{p['id']}", timeout=TIMEOUT).json()["totals"]
            u = api.put(f"{API}/projects/{p['id']}", json={"aace_class": "Class 2"}, timeout=TIMEOUT)
            assert u.status_code == 200, u.text[:300]
            assert u.json()["aace_class"] == "Class 2"
            g2 = api.get(f"{API}/projects/{p['id']}", timeout=TIMEOUT).json()
            t2 = g2["totals"]
            assert g2["project"]["aace_class"] == "Class 2"
            assert t2["aace_class"] == "Class 2"
            assert t2["expected"] == pytest.approx(t1["expected"], rel=1e-9)
            assert t2["sigma_project"] == pytest.approx(t1["sigma_project"], rel=1e-9)
            assert t2["low"] == pytest.approx(t1["low"], rel=1e-9)
            assert t2["high"] == pytest.approx(t1["high"], rel=1e-9)
        finally:
            api.delete(f"{API}/projects/{p['id']}", timeout=TIMEOUT)


# ================================================================== DUMMY PROJECT INTEGRITY
class TestSeededData:
    def test_dummy_project_rows(self, api):
        projects = api.get(f"{API}/projects", timeout=TIMEOUT).json()
        dummy = [p for p in projects if p["name"].startswith("DUMMY")]
        assert dummy, "DUMMY project missing"
        g = api.get(f"{API}/projects/{dummy[0]['id']}", timeout=TIMEOUT).json()
        rows = g["rows"]
        assert len(rows) == 8, len(rows)
        by_tag = {r["tag"]: r for r in rows}
        assert by_tag["P-501"]["flow_rate_m3_h"] == 100
        assert by_tag["P-501"]["head_m"] == 45
        assert by_tag["P-501"]["estimate_available"] is True
        assert by_tag["B-901"]["thermal_duty_kw"] == 6000
        assert by_tag["B-901"]["estimate_available"] is True
        for r in rows:
            assert r["model_version"] == MODEL_VERSION
            assert r["subtype"] in (
                "Tray", "Packed", "CSTR", "PFR", "2-Phase", "3-Phase", "Fixed Roof",
                "Floating Roof", "Shell and Tube", "Reboiler", "Air Cooler", "Centrifugal",
                "Positive Displacement", "Reciprocating", "Ball", "Gate", "Globe", "Butterfly",
                "Check", "PSV", "TRV", "SDV", "General", "Flow", "Level", "Temperature",
                "Pressure", "Analyzer", "Process Burner", "Boiler Burner", "Duct Burner",
                "Flare Burner", "User Defined")
        assert g["totals"]["expected"] > 0

    def test_no_leftover_test_refs(self, api):
        eq = api.get(f"{API}/equipment", timeout=TIMEOUT).json()
        leftovers = [e for e in eq if (e.get("notes") or "").startswith("TEST_v3")]
        assert not leftovers, f"{len(leftovers)} temp refs not cleaned up"
