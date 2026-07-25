"""
Wave 0 tests: the tool contract, registry, and executor safety rules.
These guard the invariants everything above Layer 7 assumes:
  • read tools execute; non-read tools only ever PROPOSE (ledger row)
  • bad side_effect declarations are rejected at definition time
  • argument validation catches missing/unknown/mistyped inputs
  • idempotency blocks repeat proposals on the same entity
"""
import json

import pytest

from vinayak.tools import registry
from vinayak.tools.contract import Tool, ToolInput, ToolResult, tool
from vinayak.tools.executor import ToolContext, execute, GATE_FOR
from vinayak.reasoning.engine import Evidence


@pytest.fixture(autouse=True)
def clean_registry():
    registry.clear()
    yield
    registry.clear()


# ── fakes ─────────────────────────────────────────────────────────────────────
class FakeCursor:
    def __init__(self, db):
        self.db = db
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def execute(self, sql, params=None):
        self.db.queries.append((" ".join(sql.split()), params))
        if "INSERT INTO actions" in sql:
            self.db.actions.append(params)
            self._out = ("fake-action-id",)
        elif "SELECT created_at" in sql:
            self._out = self.db.duplicate
        else:
            self._out = None
    def fetchone(self):
        return self._out


class FakeConn:
    def __init__(self, duplicate=None):
        self.queries, self.actions = [], []
        self.duplicate = duplicate
        self.committed = 0
    def cursor(self):
        return FakeCursor(self)
    def commit(self):
        self.committed += 1


def ctx(conn=None):
    return ToolContext(conn=conn or FakeConn(), company_id="testco", user_id="ayush")


# ── contract ──────────────────────────────────────────────────────────────────
def test_bad_side_effect_rejected_at_definition():
    with pytest.raises(ValueError):
        tool(name="x.bad", description="d", side_effect="explodes")(lambda ctx: None)


def test_duplicate_name_rejected():
    tool(name="x.a", description="d", side_effect="read")(lambda ctx: ToolResult(data={}))
    with pytest.raises(ValueError):
        tool(name="x.a", description="d", side_effect="read")(lambda ctx: ToolResult(data={}))


def test_anthropic_schema_shape():
    t = tool(name="ar.get_summary", description="AR totals", side_effect="read",
             inputs={"period_days": ToolInput(int, "window", required=False)})(
        lambda ctx, period_days=None: ToolResult(data={}))
    s = t.anthropic_schema()
    assert s["name"] == "ar__get_summary"          # dots not allowed in SDK names
    assert s["input_schema"]["properties"]["period_days"]["type"] == "integer"
    assert s["input_schema"]["required"] == []


def test_registry_lookup_both_names():
    t = tool(name="ar.get_summary", description="d", side_effect="read")(
        lambda ctx: ToolResult(data={}))
    assert registry.get("ar.get_summary") is t
    assert registry.get("ar__get_summary") is t


def test_read_only_schema_filter():
    tool(name="a.read", description="d", side_effect="read")(lambda ctx: ToolResult(data={}))
    tool(name="a.write", description="d", side_effect="writes")(lambda ctx: ToolResult(data={}))
    names = [s["name"] for s in registry.anthropic_schemas(read_only=True)]
    assert names == ["a__read"]


# ── executor: read path ───────────────────────────────────────────────────────
def test_read_tool_executes_inline():
    t = tool(name="fin.get_x", description="d", side_effect="read")(
        lambda ctx: ToolResult(data={"total": 5},
                               evidence=[Evidence("e1", "total", 5, "5")]))
    out = execute(ctx(), t, {})
    assert out.data["total"] == 5 and out.error is None


def test_read_tool_exception_becomes_error_result():
    def boom(ctx):
        raise RuntimeError("db down")
    t = tool(name="fin.get_boom", description="d", side_effect="read")(boom)
    out = execute(ctx(), t, {})
    assert out.error and "db down" in out.error


# ── executor: argument validation ─────────────────────────────────────────────
def _echo_tool(**inputs):
    return tool(name="t.echo", description="d", side_effect="read", inputs=inputs)(
        lambda ctx, **kw: ToolResult(data=kw))

def test_missing_required_arg():
    t = _echo_tool(n=ToolInput(int, "num"))
    assert "missing required" in execute(ctx(), t, {}).error

def test_unknown_arg_rejected():
    t = _echo_tool(n=ToolInput(int, "num", required=False))
    assert "unknown inputs" in execute(ctx(), t, {"bogus": 1}).error

def test_type_coercion_and_failure():
    t = _echo_tool(n=ToolInput(int, "num"))
    assert execute(ctx(), t, {"n": "42"}).data["n"] == 42
    assert "must be int" in execute(ctx(), t, {"n": "forty"}).error


# ── executor: non-read tools only propose ─────────────────────────────────────
def _draft_tool():
    return tool(
        name="ar.draft_collection_email", description="d", side_effect="writes",
        inputs={"customer_ref": ToolInput(str, "customer")})(
        lambda ctx, customer_ref: ToolResult(
            data={"to": "x@y.com", "body": "pay ₹1L", "summary": f"chase {customer_ref}"}))

def test_write_tool_never_executes_only_proposes():
    conn = FakeConn()
    t = _draft_tool()
    out = execute(ctx(conn), t, {"customer_ref": "DEV COLOUR"})
    assert out.data["queued"] is True
    assert out.data["gate"] == "confirm"
    assert len(conn.actions) == 1                    # exactly one ledger row
    payload = json.loads(conn.actions[0][3])
    assert payload["to"] == "x@y.com"

def test_money_tools_gate_to_human():
    assert GATE_FOR["moves_money"] == "human"
    assert GATE_FOR["files_regulator"] == "human"

def test_idempotency_blocks_repeat_proposal():
    conn = FakeConn(duplicate=("2026-07-05",))      # ledger says: already chased
    t = _draft_tool()
    out = execute(ctx(conn), t, {"customer_ref": "DEV COLOUR"})
    assert out.error and "idempotency" in out.error
    assert conn.actions == []                        # nothing written
