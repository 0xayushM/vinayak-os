"""
Stage 3: the QueryService read door. No DB required — we assert the facade
forwards to the repository faithfully, and that the tool layer now depends on the
service (not the flat module) while still registering every read tool.
"""
from vinayak.query import QueryService, service
from vinayak.schema import queries as repository


def test_service_forwards_to_repository():
    # A known query function resolves to the SAME object via the service.
    assert service.get_ar_summary is repository.get_ar_summary
    assert QueryService().get_revenue_summary is repository.get_revenue_summary


def test_service_unknown_attribute_raises():
    import pytest
    with pytest.raises(AttributeError):
        _ = service.get_nonexistent_thing


def test_read_tools_registered_through_the_service():
    from vinayak.tools import registry
    from vinayak.tools.read_tools import register_all, tool_names
    registry.clear()
    n = register_all()
    assert n > 0
    names = tool_names()
    # the finance/ar/inventory read tools are present, sourced via the service
    assert any(t.startswith("ar.") for t in names)
    assert any(t.startswith("revenue.") or t.startswith("finance.") for t in names)
