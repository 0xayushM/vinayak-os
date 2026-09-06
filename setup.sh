#!/usr/bin/env bash
# setup.sh — one-time local setup: Python venv + backend deps, pnpm + frontend deps,
# and env files. Safe to re-run (idempotent). Then use ./dev.sh to run both apps.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"; cd "$ROOT"

say()  { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
ok()   { printf '  \033[1;32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[1;33m!\033[0m %s\n' "$*"; }

say "Checking tools"
command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }
command -v node    >/dev/null || { echo "node is required (v20+)"; exit 1; }
ok "python $(python3 --version 2>&1 | cut -d' ' -f2)  ·  node $(node --version)"
if ! command -v pnpm >/dev/null; then
  command -v corepack >/dev/null && corepack enable >/dev/null 2>&1 && ok "pnpm enabled via corepack" \
    || { echo "pnpm is required: npm i -g pnpm"; exit 1; }
fi

say "Backend: Python venv (.venv) + dependencies"
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r vinayak/requirements.txt
[ -f requirements-dev.txt ] && pip install -q -r requirements-dev.txt
pip install -q python-docx >/dev/null 2>&1 || true
ok "backend deps installed into .venv"

say "Frontend: pnpm install (workspace)"
pnpm install --silent
ok "frontend deps installed"

say "Env files"
if [ ! -f .env ]; then cp .env.example .env; warn "created .env from .env.example — fill in DATABASE_URL, INTERNAL_API_KEY, FERNET_KEY, ANTHROPIC_API_KEY, SUPABASE_*"; else ok ".env present"; fi
if [ ! -f apps/web/.env.local ]; then
  cat > apps/web/.env.local <<'EOF'
FASTAPI_INTERNAL_URL=http://localhost:8000
INTERNAL_API_KEY=
NEXT_PUBLIC_APP_URL=http://localhost:3000
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
EOF
  warn "created apps/web/.env.local — set INTERNAL_API_KEY (same as backend) and the NEXT_PUBLIC_SUPABASE_* pair"
else ok "apps/web/.env.local present"; fi

say "Sanity: backend imports + test suite"
PYTHONPATH=. VINAYAK_DEV_MODE=1 python -c "import vinayak.api.main" && ok "backend imports"
PYTHONPATH=. VINAYAK_DEV_MODE=1 python -m pytest tests/ -q 2>&1 | tail -1

printf '\n\033[1;32mSetup complete.\033[0m  Run both apps with:  ./dev.sh\n\n'
