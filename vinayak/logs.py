"""
logs.py
────────
One logging setup for the API and the worker, with the two ids that make a
log line findable: which request it belongs to, and which workspace.

"Sandeep's Pulse errored at 9:14" is a question about one request among
hundreds, and without an id the only way to answer it is to guess from
timestamps. The request middleware (api/main.py) puts a request id and the
workspace into contextvars; the filter here copies them onto every record, so
any `logger.info` anywhere in the call stack carries them without being passed
anything.

Human-readable by default, because the person reading these logs is usually
reading them in the Railway console. LOG_FORMAT=json switches to one JSON
object per line for when they are shipped somewhere that parses them.
"""
from __future__ import annotations

import contextvars
import json
import logging
import os
import re
from datetime import datetime, timezone

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None)
company_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "company_id", default=None)

_HUMAN = "%(asctime)s  %(levelname)-8s  %(name)s %(ctx)s— %(message)s"

# Ids arrive in headers, so they are untrusted input headed for a log line:
# anything that is not a short plain token is replaced rather than logged.
_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def safe_id(value: str | None) -> str | None:
    """The value if it is a short plain token, else None."""
    if value and _SAFE_ID.match(value):
        return value
    return None


class ContextFilter(logging.Filter):
    """Stamps request_id / company_id (and a pre-formatted `ctx`) on a record."""

    def filter(self, record: logging.LogRecord) -> bool:
        rid, cid = request_id_var.get(), company_id_var.get()
        record.request_id = rid
        record.company_id = cid
        parts = []
        if rid:
            parts.append(f"req={rid}")
        if cid:
            parts.append(f"ws={cid}")
        record.ctx = f"[{' '.join(parts)}] " if parts else ""
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "company_id": getattr(record, "company_id", None),
        }
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Idempotent. Safe to call from both the API module and the worker."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=level)
    root.setLevel(level)
    fmt: logging.Formatter = (
        JsonFormatter() if os.getenv("LOG_FORMAT", "").strip().lower() == "json"
        else logging.Formatter(_HUMAN))
    for h in root.handlers:
        if not any(isinstance(f, ContextFilter) for f in h.filters):
            h.addFilter(ContextFilter())
        h.setFormatter(fmt)
