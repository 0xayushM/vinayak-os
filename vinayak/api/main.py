"""
api/main.py
────────────
FastAPI application entry point for Vinayak Brain OS.

Serves the dashboard and AI endpoints. Background jobs run in the worker
(vinayak/worker.py) unless RUN_SCHEDULER=1; the API watches that the worker is
alive (vinayak/health.py).

Run locally:
    uvicorn vinayak.api.main:app --reload --port 8000

Deploy (production):
    uvicorn vinayak.api.main:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from vinayak.pipelines.scheduler import start_scheduler, stop_scheduler

from vinayak.logs import (configure_logging, request_id_var, company_id_var,
                          safe_id)

configure_logging()
logger = logging.getLogger(__name__)


# Background work belongs to the worker process (`python -m vinayak.worker`),
# not to the API. Set RUN_SCHEDULER=1 to put it back in here — which is what
# local development wants, and what production must not do: the API is
# horizontally scaled, so a scheduler inside it runs every job once per
# replica. Default off, so adding a second replica is a boring thing to do.
RUN_SCHEDULER = os.getenv("RUN_SCHEDULER", "").strip().lower() in ("1", "true", "yes")


def _warn_if_migrations_pending() -> None:
    """See scripts/migrate.warn_if_pending."""
    from vinayak.scripts.migrate import warn_if_pending
    warn_if_pending(logger)


# When this API process started. The worker watchdog uses it to tell "the
# worker has not beaten yet because we both just deployed" from "the worker
# was never started".
STARTED_AT = datetime.now(timezone.utc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the in-process scheduler only when this instance owns it, and the
    worker watchdog always.

    The watchdog lives here, not in the worker, because it exists to notice
    the worker being dead — see vinayak/health.py."""
    from vinayak import health

    _warn_if_migrations_pending()
    if RUN_SCHEDULER:
        logger.info("RUN_SCHEDULER is set — starting APScheduler in the API process")
        from vinayak.worker import build_scheduler   # adds the brain tick + heartbeat
        build_scheduler(role="api")
        start_scheduler()
    else:
        logger.info("Scheduler not started here; background jobs run in the worker")

    watchdog = None
    if health.watchdog_enabled():
        watchdog = asyncio.create_task(health.watchdog(STARTED_AT))
    else:
        logger.warning("WORKER_WATCHDOG is off — a dead worker will not raise an alert")
    yield
    if watchdog is not None:
        watchdog.cancel()
    if RUN_SCHEDULER:
        logger.info("Stopping APScheduler...")
        stop_scheduler()


app = FastAPI(
    title="Vinayak Brain OS",
    description="BIDE backend — ingestion, canonical model, grounded reasoning, action spine",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: only allow requests from the Next.js BFF (Vercel URL or local dev).
# The browser NEVER talks to FastAPI directly — all calls go through /api/* on
# the Next.js host, so the wildcard here is safe in dev but lock it to the
# production Vercel URL before shipping.
from vinayak.config import DEV_MODE

ALLOWED_ORIGINS = [os.getenv("NEXT_PUBLIC_APP_URL", "")]
if DEV_MODE:
    ALLOWED_ORIGINS += ["http://localhost:3000", "http://localhost:3001"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in ALLOWED_ORIGINS if o],
    allow_credentials=True,          # needed for httpOnly cookie flow
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# ── Request context: an id per request, and the workspace it is for ──────────
# Pure ASGI rather than BaseHTTPMiddleware: it sets the contextvars before the
# route runs (sync routes run in a threadpool that copies the context, so the
# ids reach their log lines too) and adds nothing else to the request path.
# An incoming X-Request-ID is kept when it is a plain token, so the BFF or a
# proxy can correlate its own logs with ours; otherwise one is generated.
_SLOW_REQUEST_SECONDS = 5.0


class RequestContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers") or []}
        rid = safe_id(headers.get("x-request-id")) or uuid.uuid4().hex[:16]
        # The header is what the BFF sends; require_workspace still decides
        # whether the caller may use it. For logging, the claim is enough.
        cid = safe_id(headers.get("x-workspace-id"))
        # Not reset afterwards: each request runs in its own task with its own
        # context, and leaving them set lets the unhandled-exception handler
        # (which runs outside this middleware) log with the same ids.
        request_id_var.set(rid)
        company_id_var.set(cid)
        started = time.monotonic()
        status_holder = {"status": 500}

        async def _send(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                message.setdefault("headers", [])
                message["headers"] = list(message["headers"]) + [
                    (b"x-request-id", rid.encode("latin-1"))]
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            elapsed = time.monotonic() - started
            status = status_holder["status"]
            if status >= 500 or elapsed >= _SLOW_REQUEST_SECONDS:
                logger.warning("%s %s -> %s in %.2fs", scope.get("method"),
                               scope.get("path"), status, elapsed)


app.add_middleware(RequestContextMiddleware)


# ── Global exception handler — ensures all errors return JSON, not plain text ──
@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    rid = request_id_var.get()
    return JSONResponse(
        status_code=500,
        # The id is what turns "it errored this morning" into one log search.
        content={"detail": "Internal server error", "type": type(exc).__name__,
                 "request_id": rid},
        headers={"X-Request-ID": rid} if rid else None,
    )


# ── Register routers ──────────────────────────────────────────────────────────
from vinayak.api.routes import auth, connections, dashboard, workspaces, zoho, milestones, pulse, brain, collections  # noqa: E402
from vinayak.api.routes.auth import require_internal_key  # noqa: E402

# The BFF boundary. Every business route requires the shared X-Internal-Key the
# Next.js route handlers attach — so FastAPI, even if its URL is discovered,
# only serves requests that came through the BFF (on top of the per-user JWT
# check each route already does). Only "/" and "/health" stay open, for the
# platform health probe. In dev mode with no INTERNAL_API_KEY the check is a
# no-op (see require_internal_key).
_BFF_ONLY = [Depends(require_internal_key)]

app.include_router(auth.router,        prefix="/auth",        tags=["Auth"],        dependencies=_BFF_ONLY)
app.include_router(workspaces.router,  prefix="/workspaces",   tags=["Workspaces"],  dependencies=_BFF_ONLY)
# Source namespaces: each data source lives under its own prefix.
#   /tranzact/*  — TranzAct connection + sync (also mounted at the legacy
#                  /connections/* path so the existing frontend keeps working)
#   /zoho/*      — Zoho Books connection + sync
app.include_router(connections.router, prefix="/connections",  tags=["TranzAct (legacy path)"], dependencies=_BFF_ONLY)
app.include_router(connections.router, prefix="/tranzact",     tags=["TranzAct"],    dependencies=_BFF_ONLY)
app.include_router(zoho.router,        prefix="/zoho",         tags=["Zoho Books"],  dependencies=_BFF_ONLY)
app.include_router(dashboard.router,   prefix="/dashboard",    tags=["Dashboard"],   dependencies=_BFF_ONLY)
# Milestone evidence: usage, experiments, incidents, the board (same prefix, own module).
app.include_router(milestones.router,  prefix="/dashboard",    tags=["Milestones"],  dependencies=_BFF_ONLY)
# The Pulse: the landing cards and the payload the morning brief is written from.
app.include_router(pulse.router,       prefix="/dashboard",    tags=["Pulse"],       dependencies=_BFF_ONLY)
# Layer 10 — what the brain did on its own, and the switches for it.
app.include_router(brain.router,       prefix="/dashboard",    tags=["Brain"],       dependencies=_BFF_ONLY)
# The collections ladder: chase list, recovery proof, promises, disputes.
app.include_router(collections.router, prefix="/dashboard",    tags=["Collections"], dependencies=_BFF_ONLY)

# Register the Layer-7 read tools so the agent + MCP can call the business as a
# tool. Idempotent; read-only wrappers over the proven query functions.
from vinayak.tools.read_tools import register_all as _register_read_tools  # noqa: E402
from vinayak.tools.action_tools import register_action_tools as _register_action_tools  # noqa: E402
_register_read_tools()
_register_action_tools()


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "service": "Vinayak Brain OS"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}
