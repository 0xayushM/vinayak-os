"""
Unit tests for the Layer-7 read-tool registration. No DB required: we test the
tool catalog shape, the evidence formatting, and the contract guarantees (every
finance/read tool is side_effect='read' with a valid Anthropic schema).
"""
from vinayak.tools import registry
from vinayak.tools import read_tools
from vinayak.tools.read_tools import register_all, tool_names, _display, _evidence


def setup_function():
    registry.clear()


def test_register_all_is_idempotent():
    n1 = register_all()
    n2 = register_all()
    assert n1 == len(tool_names())
    assert n2 == 0                       # second call registers nothing new


def test_all_registered_tools_are_read_only():
    register_all()
    tools = registry.all_tools()
    assert len(tools) == len(tool_names())
    assert all(t.side_effect == "read" for t in tools)


def test_expected_finance_tools_present():
    register_all()
    for name in ["finance.get_overview", "finance.get_collections_priority",
                 "finance.get_credit_risk", "finance.get_dso",
                 "finance.get_monthly_sales", "finance.get_cash_movement",
                 "ar.get_summary", "revenue.get_summary"]:
        assert registry.get(name) is not None, f"missing tool {name}"


def test_anthropic_schema_is_valid_and_sdk_safe():
    register_all()
    t = registry.get("finance.get_dso")
    schema = t.anthropic_schema()
    assert schema["name"] == "finance__get_dso"          # dots → __ for the SDK
    assert schema["input_schema"]["properties"]["days"]["type"] == "integer"
    assert "days" not in schema["input_schema"]["required"]  # optional input


def test_lookup_by_sdk_name():
    register_all()
    # registry.get accepts either canonical or SDK ('__') form
    assert registry.get("finance__get_overview") is not None


def test_money_display_compacts_and_signs():
    assert _display(2100000, "money") == "₹21.00 L"
    assert _display(-2074626, "money") == "-₹20.75 L"
    assert _display(16000000, "money") == "₹1.60 Cr"
    assert _display(None, "money") == "—"
    assert _display(55, "pct") == "55%"
    assert _display(150, "days") == "150 days"


def test_evidence_built_only_for_present_scalars():
    data = {"outstanding": 250000, "overdue": None, "dso_days": 150}
    ev = _evidence("finance.get_overview", data,
                   [("outstanding", "Outstanding", "money"),
                    ("overdue", "Overdue", "money"),
                    ("dso_days", "DSO", "days")])
    ids = {e.id for e in ev}
    assert "finance.get_overview:outstanding" in ids
    assert "finance.get_overview:dso_days" in ids
    assert "finance.get_overview:overdue" not in ids   # None is skipped
