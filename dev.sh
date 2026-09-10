#!/usr/bin/env bash
# dev.sh — run the FastAPI backend (:8000) and the Next.js frontend (:3000) together.
# Run ./setup.sh once first. Ctrl+C stops both.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"; cd "$ROOT"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

# ── Python env (prefer .venv, fall back to venv) ─────────────────────────────
if   [ -f .venv/bin/activate ]; then source .venv/bin/activate
elif [ -f venv/bin/activate ];  then source venv/bin/activate
else echo "No virtualenv found — run ./setup.sh first."; exit 1; fi

# ── Env: load .env for the backend (frontend reads apps/web/.env.local itself) ─
[ -f .env ] || { echo "Missing .env — run ./setup.sh"; exit 1; }
set -a; # shellcheck disable=SC1091
source .env; set +a
export VINAYAK_DEV_MODE="${VINAYAK_DEV_MODE:-1}"
export PYTHONPATH="$ROOT"

# ── Frontend must reach the local backend ────────────────────────────────────
export FASTAPI_INTERNAL_URL="http://localhost:${BACKEND_PORT}"

# NEXT_PUBLIC_* vars from root .env are documentation only (see comment above) —
# `set -a; source .env` still puts them in process.env, and Next.js's env load
# order (process.env > .env.local) would let a stale one here silently shadow
# the real value in apps/web/.env.local. Unset so apps/web/.env.local always wins.
unset NEXT_PUBLIC_SUPABASE_URL NEXT_PUBLIC_SUPABASE_ANON_KEY NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY

cleanup() {
  echo; echo "Shutting down…"
  kill "${BACKEND_PID:-}" "${FRONTEND_PID:-}" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# ── Backend ──────────────────────────────────────────────────────────────────
echo "▶ backend  → uvicorn on :${BACKEND_PORT} (scheduler in-process for dev)"
# One process locally: RUN_SCHEDULER=1 puts the syncs, the brief and the
# brain tick back inside the API, so `./dev.sh` is still all you need.
# Production runs them in the separate worker service instead (Procfile).
RUN_SCHEDULER=1 uvicorn vinayak.api.main:app --reload --port "$BACKEND_PORT" &
BACKEND_PID=$!

# wait for /health (up to ~30s)
for i in $(seq 1 30); do
  if curl -fsS "http://localhost:${BACKEND_PORT}/health" >/dev/null 2>&1; then
    echo "  ✓ backend healthy"; break; fi
  sleep 1
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then echo "  ✗ backend exited — see log above"; exit 1; fi
done

# ── Frontend ─────────────────────────────────────────────────────────────────
echo "▶ frontend → next dev on :${FRONTEND_PORT}"
# `pnpm exec` runs the package's own `next` binary and forwards args cleanly.
# (Don't use `pnpm run dev -- --port`: pnpm passes the literal `--` through and
#  next then treats `--port` as a project directory.)
(cd apps/web && exec pnpm exec next dev --port "$FRONTEND_PORT") &
FRONTEND_PID=$!

cat <<EOF

  ✅ Backend  → http://localhost:${BACKEND_PORT}/docs
  ✅ Frontend → http://localhost:${FRONTEND_PORT}
  Auth mode  → $([ -n "${SUPABASE_JWT_SECRET:-}" ] && echo "Supabase" || echo "legacy JWT")
  Press Ctrl+C to stop both.

EOF
wait
