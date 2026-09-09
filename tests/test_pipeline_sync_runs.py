"""
tz_sync_runs rows must carry the workspace that synced. Sync health, panel
freshness and the stale badges all filter by company_id, so a run logged
without it is invisible to (or mis-attributed away from) its workspace.
"""
from vinayak.pipelines.base import BasePipeline


class _Cur:
    def __init__(self):
        self.sql = None
        self.params = None

    def execute(self, sql, params=None):
        self.sql, self.params = sql, params

    def fetchone(self):
        return (42,)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Conn:
    def __init__(self):
        self.cur = _Cur()
        self.committed = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True


class _P(BasePipeline):
    PIPELINE_NAME = "sales_invoices"
    REPORT_ID = "29"
    TABLE_NAME = "tz_sales_invoices"
    RowSchema = dict

    def _upsert(self, conn, rows, company_id):
        return 0


def test_start_run_writes_company_id():
    conn = _Conn()
    run_id = _P()._start_run(conn, "protegere", is_backfill=False)
    assert run_id == 42
    assert conn.committed
    sql = " ".join(conn.cur.sql.split())
    assert "INSERT INTO tz_sync_runs (company_id, pipeline_name, report_id, status, is_backfill)" in sql
    assert conn.cur.params == ("protegere", "sales_invoices", 29, False)
