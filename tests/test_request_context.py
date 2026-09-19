"""
Every API log line can be traced to its request and its workspace. The ids
travel in contextvars set by the middleware, so a log call deep in a query
function carries them without being passed anything.
"""
import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vinayak.api.main import RequestContextMiddleware, app
from vinayak.logs import ContextFilter, JsonFormatter, company_id_var, request_id_var, safe_id


def _tiny_app():
    tiny = FastAPI()
    tiny.add_middleware(RequestContextMiddleware)
    seen = {}

    @tiny.get("/probe")
    def probe():            # sync, so it runs in the threadpool like the real routes
        seen["rid"], seen["cid"] = request_id_var.get(), company_id_var.get()
        return {"ok": True}

    return TestClient(tiny), seen


def test_every_response_carries_a_request_id():
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert len(r.headers["x-request-id"]) == 16


def test_an_incoming_request_id_is_kept_so_the_bff_can_correlate_its_logs():
    r = TestClient(app).get("/health", headers={"X-Request-ID": "bff-abc.123"})
    assert r.headers["x-request-id"] == "bff-abc.123"


def test_a_request_id_that_is_not_a_plain_token_is_replaced_not_logged():
    r = TestClient(app).get("/health", headers={"X-Request-ID": "evil\nFAKE LOG LINE"})
    assert "evil" not in r.headers["x-request-id"]


def test_sync_routes_see_the_request_id_and_workspace():
    client, seen = _tiny_app()
    r = client.get("/probe", headers={"X-Request-ID": "req1", "X-Workspace-Id": "kbrushes"})
    assert r.status_code == 200
    assert seen == {"rid": "req1", "cid": "kbrushes"}


def test_safe_id_accepts_workspace_slugs_and_rejects_anything_else():
    assert safe_id("kbrushes") == "kbrushes"
    assert safe_id("a" * 65) is None
    assert safe_id("x y") is None
    assert safe_id(None) is None


def _record(msg="hello"):
    return logging.LogRecord("vinayak.test", logging.INFO, __file__, 1, msg, None, None)


def test_log_records_carry_the_ids_in_human_and_json_formats():
    rt, ct = request_id_var.set("r42"), company_id_var.set("protegere")
    try:
        rec = _record()
        ContextFilter().filter(rec)
        assert rec.ctx == "[req=r42 ws=protegere] "
        line = json.loads(JsonFormatter().format(rec))
        assert line["request_id"] == "r42" and line["company_id"] == "protegere"
        assert line["msg"] == "hello"
    finally:
        request_id_var.reset(rt)
        company_id_var.reset(ct)


def test_log_records_outside_a_request_have_no_context_prefix():
    rec = _record()
    ContextFilter().filter(rec)
    assert rec.ctx == "" and rec.request_id is None


# ── settings read from the environment ───────────────────────────────────
def test_a_blank_numeric_setting_falls_back_to_its_default(monkeypatch):
    """Railway passes a reference to a variable the other service never set
    as an empty string. That once stopped the worker at import."""
    from vinayak.config import env_int
    monkeypatch.setenv("SOME_LIMIT", "")
    assert env_int("SOME_LIMIT", 8) == 8
    monkeypatch.setenv("SOME_LIMIT", "  ")
    assert env_int("SOME_LIMIT", 8) == 8
    monkeypatch.setenv("SOME_LIMIT", "not a number")
    assert env_int("SOME_LIMIT", 8) == 8
    monkeypatch.setenv("SOME_LIMIT", "12")
    assert env_int("SOME_LIMIT", 8) == 12
