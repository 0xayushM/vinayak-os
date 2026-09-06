"""
adapters/base.py
─────────────────
Shared building blocks for source adapters. Right now: the thread-safe
get-or-create registry both the Tranzact and Zoho auth modules used to reimplement
(each had its own `_caches` dict + lock + `_cache_for`). Each adapter still owns
its own token-cache type and cache key; only the concurrency-safe store is shared.
"""
from __future__ import annotations

import threading
from typing import Callable, Generic, Hashable, TypeVar

V = TypeVar("V")


class TokenCacheRegistry(Generic[V]):
    """A thread-safe get-or-create store of per-key token caches. The adapter
    supplies the cache type via `factory`, so this stays agnostic to what a token
    cache actually contains."""

    def __init__(self) -> None:
        self._caches: dict[Hashable, V] = {}
        self._lock = threading.Lock()

    def get_or_create(self, key: Hashable, factory: Callable[[], V]) -> V:
        with self._lock:
            cache = self._caches.get(key)
            if cache is None:
                cache = factory()
                self._caches[key] = cache
            return cache
