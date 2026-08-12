"""
vinayak.agents
──────────────
The orchestration layer: the AgentRunner port and its implementations. The native
tool-use loop is the default; the Google ADK adapter is an alternative behind the
same interface. Callers depend on the port (`get_runner`), never on a concrete
engine — so swapping orchestrators changes nothing above this package.
"""
from vinayak.agents.runner import AgentRunner, NativeAgentRunner, make_runner, get_runner
from vinayak.agents.adk import AdkAgentRunner

__all__ = ["AgentRunner", "NativeAgentRunner", "AdkAgentRunner", "make_runner", "get_runner"]
