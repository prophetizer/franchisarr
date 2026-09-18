"""Guards against regressing base-URL handling (docs/DESIGN.md technical challenge #10):
every route must be reachable under a configured BASE_URL subpath, not just at root.
"""

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.config import _normalize_base_url


def _build_app(base_url: str) -> FastAPI:
    app = FastAPI()
    router = APIRouter()

    @router.get("/health")
    def health():
        return {"status": "ok"}

    app.include_router(router, prefix=base_url)
    return app


def test_normalize_base_url_variants():
    assert _normalize_base_url("/") == ""
    assert _normalize_base_url("") == ""
    assert _normalize_base_url("franchisarr") == "/franchisarr"
    assert _normalize_base_url("/franchisarr") == "/franchisarr"
    assert _normalize_base_url("/franchisarr/") == "/franchisarr"


def test_health_reachable_under_subpath():
    app = _build_app("/franchisarr")
    client = TestClient(app)
    resp = client.get("/franchisarr/health")
    assert resp.status_code == 200

    # Root path should NOT respond once mounted under a subpath — a regression here would mean
    # the reverse-proxy subpath isn't actually being respected.
    resp_root = client.get("/health")
    assert resp_root.status_code == 404


def test_health_reachable_at_root_when_base_url_unset():
    app = _build_app("")
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
