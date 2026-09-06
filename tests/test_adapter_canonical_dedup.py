"""
Stage 2 dedup tests: the shared TokenCacheRegistry (adapters/base.py) and the
shared distinct_company_ids helper (canonical/base.py). No DB/network required.
"""
import threading

from vinayak.adapters.base import TokenCacheRegistry
from vinayak.canonical.base import distinct_company_ids


def test_token_cache_registry_get_or_create_is_stable():
    reg = TokenCacheRegistry()
    made = []
    def factory():
        obj = object()
        made.append(obj)
        return obj
    a = reg.get_or_create(("dc", "id"), factory)
    b = reg.get_or_create(("dc", "id"), factory)   # same key → same object
    c = reg.get_or_create(("dc", "other"), factory)
    assert a is b
    assert a is not c
    assert len(made) == 2                            # factory ran once per new key


def test_token_cache_registry_is_thread_safe():
    reg = TokenCacheRegistry()
    results = []
    def worker():
        results.append(reg.get_or_create("k", lambda: object()))
    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(set(id(r) for r in results)) == 1     # all got the one cache


class _FakeCursor:
    def __init__(self, rows): self._rows = rows; self.sql = None
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql): self.sql = sql
    def fetchall(self): return self._rows

class _FakeConn:
    def __init__(self, rows): self._rows = rows; self.last = None
    def cursor(self): self.last = _FakeCursor(self._rows); return self.last


def test_distinct_company_ids_queries_the_given_table():
    conn = _FakeConn([("acme",), ("globex",)])
    out = distinct_company_ids(conn, "tz_sales_invoices")
    assert out == ["acme", "globex"]
    assert "tz_sales_invoices" in conn.last.sql
    assert "DISTINCT company_id" in conn.last.sql
