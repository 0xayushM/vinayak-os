"""
reasoning/runner.py  (compat facade)
────────────────────────────────────
The AgentRunner port moved to vinayak.agents (Stage 4 of the restructure). This
module re-exports it so existing imports — `from vinayak.reasoning.runner import
get_runner` / `make_runner` / `NativeAgentRunner` — keep working unchanged.
New code should import from vinayak.agents.
"""
from vinayak.agents.runner import (  # noqa: F401
    AgentRunner,
    NativeAgentRunner,
    make_runner,
    get_runner,
    _make_runner,
)
