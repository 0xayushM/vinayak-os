"""
query/service.py
─────────────────
QueryService — the encapsulated read API. Every read the brain performs should go
through this one object (the "single retrieval door" from the finalized
architecture), so provenance, caps, and (later) caching live in one place.

For now it is a faithful facade over the repository (schema/queries.py): any
`service.get_xxx(...)` call forwards to the same function, so migrating a caller
from `queries.get_xxx` to `service.get_xxx` changes the dependency direction
(caller → abstraction) without changing behaviour. As queries.py is split into
domain repositories, these dynamic forwards become explicit, typed methods.
"""
from __future__ import annotations

from vinayak.schema import pulse as _pulse_repository
from vinayak.schema import queries as _repository


class QueryService:
    def __init__(self, repository=_repository) -> None:
        # Normal instance attribute → found by ordinary lookup, so __getattr__
        # (below) never recurses on it.
        self._repository = repository

    def __getattr__(self, name: str):
        """Forward any read call to the underlying repository, then to the Pulse
        repository (schema/pulse.py — the derived-insight reads). Raises the
        usual AttributeError for genuinely unknown names."""
        try:
            return getattr(self._repository, name)
        except AttributeError:
            return getattr(_pulse_repository, name)


# The shared read door.
service = QueryService()
