"""
api/main.py
────────────
FastAPI application entry point for Vinayak Brain OS.

Starts the APScheduler (pipelines run inside this process — no separate worker).
Exposes all dashboard and AI endpoints.

Run locally:
    uvicorn vinayak.api.main:app --reload --port 8000

Deploy (production):
    uvicorn vinayak.api.main:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from vinayak.pipelines.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# Background work belongs to the worker process (`python -m vinayak.worker`),
# not to the API. Set RUN_SCHEDULER=1 to put it back in here — which is what
# local development wants, and what production must not do: the API is
# horizontally scaled, so a scheduler inside it runs every job once per
# replica. Default off, so adding a second replica is a boring thing to do.
RUN_SCHEDULER = os.getenv("RUN_SCHEDULER", "").strip().lower() in ("1", "true", "yes")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the in-process scheduler only when this instance owns it."""
    if RUN_SCHEDULER:
        logger.info("RUN_SCHEDULER is set — starting APScheduler in the API process")
        from vinayak.worker import build_scheduler   # adds the brain tick
        build_scheduler()
        start_scheduler()
    else:
        logger.info("Scheduler not started here; background jobs run in the worker")
    yield
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

# ── Global exception handler — ensures all errors return JSON, not plain text ──
@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )


# ── Register routers ──────────────────────────────────────────────────────────
from vinayak.api.routes import auth, connections, dashboard, workspaces, zoho, milestones, pulse, brain  # noqa: E402
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
