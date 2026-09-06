"""
reasoning/adk_runner.py  (compat facade)
────────────────────────────────────────
The Google ADK adapter moved to vinayak.agents.adk (Stage 4). Re-exported here so
existing imports keep working. New code should import from vinayak.agents.adk.
"""
from vinayak.agents.adk import AdkAgentRunner, _adk_available  # noqa: F401
