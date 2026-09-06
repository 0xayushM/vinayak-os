"""
vinayak.query
─────────────
The read layer — the single "door" through which tools (and, later, the engine)
fetch pre-aggregated data. `QueryService` is that door; `service` is the shared
instance. It currently proxies the repository (schema/queries.py); as that
2,425-line module is split into domain repositories, the proxy's dynamic
forwarding is replaced by explicit typed methods — without changing callers.
"""
from vinayak.query.service import QueryService, service
from vinayak.schema import queries as repository

__all__ = ["QueryService", "service", "repository"]
