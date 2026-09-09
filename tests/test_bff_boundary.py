"""
The BFF boundary: every business route must refuse a request that did not come
through the Next.js BFF (i.e. without the shared X-Internal-Key), while the
platform health probe stays open. conftest sets INTERNAL_API_KEY, so the check
is active here exactly as in production.
"""
from fastapi.testclient import TestClient

from vinayak.api.main import app
from vinayak.api.routes.auth import INTERNAL_KEY

client = TestClient(app)


def test_health_is_open():
    assert client.get("/health").status_code == 200
    assert client.get("/").status_code == 200


def test_business_routes_reject_missing_internal_key():
    for path in ("/dashboard/tools", "/workspaces/", "/connections/",
                 "/zoho/status", "/auth/me"):
        r = client.get(path)
        assert r.status_code == 403, (path, r.status_code, r.text)
        assert "internal API key" in r.json()["detail"]


def test_wrong_internal_key_rejected():
    r = client.get("/dashboard/tools", headers={"X-Internal-Key": INTERNAL_KEY + "x"})
    assert r.status_code == 403


def test_correct_internal_key_passes_the_boundary():
    # With the key present the request reaches the route's own auth
    # (401: no user token) instead of being stopped at the boundary (403).
    r = client.get("/auth/me", headers={"X-Internal-Key": INTERNAL_KEY})
    assert r.status_code == 401


def test_milestone_routes_are_behind_the_boundary_and_auth():
    for path in ("/dashboard/milestones", "/dashboard/experiments", "/dashboard/usage/me",
                 "/dashboard/incidents", "/workspaces/users"):
        assert client.get(path).status_code == 403                                        # no key
        assert client.get(path, headers={"X-Internal-Key": INTERNAL_KEY}).status_code == 401  # key, no user
