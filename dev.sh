#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

# ---- Backend ----
echo "Starting FastAPI backend on :8000 ..."
source venv/bin/activate
uvicorn vinayak.api.main:app --reload --port 8000 &
BACKEND_PID=$!

# ---- Frontend ----
echo "Starting Next.js frontend on :3000 ..."
pnpm dev &
FRONTEND_PID=$!

# ---- Cleanup on exit ----
trap "echo 'Shutting down...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM

echo ""
echo "✅ Backend  → http://localhost:8000/docs"
echo "✅ Frontend → http://localhost:3000"
echo "Press Ctrl+C to stop both."
echo ""

wait
