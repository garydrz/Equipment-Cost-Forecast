import os
import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
_base = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not _base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing from env and /app/frontend/.env")
BASE_URL = _base.rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def base_url():
    return API


@pytest.fixture(scope="session")
def sim_defaults(api):
    """Original similarity config, restored at end of session."""
    r = api.get(f"{API}/admin/similarity-settings", timeout=30)
    r.raise_for_status()
    cfg = r.json()
    cfg.pop("defaults", None)
    cfg.pop("updated_at", None)
    yield dict(cfg)
    api.put(f"{API}/admin/similarity-settings", json=cfg, timeout=30)


@pytest.fixture(scope="session")
def project(api):
    """Temp project used across row tests."""
    r = api.post(f"{API}/projects", json={
        "name": "TEST_it2_project",
        "description": "TEST iteration2",
        "output_currency": "EUR",
        "target_year": 2026,
        "aace_class": "Class 3",
    }, timeout=30)
    r.raise_for_status()
    p = r.json()
    yield p
    api.delete(f"{API}/projects/{p['id']}", timeout=30)
