# BIDE — Run Guide

How to set up, run, and verify the system as it is built today. Two processes
run side by side:

- **`apps/web`** — Next.js app (UI + BFF route handlers). The browser only ever talks to this.
- **`vinayak/`** — Python/FastAPI backend (auth verification, connections, pipelines,
  canonical rebuild, dashboard queries, reasoning). Private; reached only through the BFF.

Data path: **Browser → Next.js `/api/*` (BFF) → FastAPI → Supabase Postgres / TranzAct / Zoho**.
The FastAPI URL, the internal key, and every ERP token stay server-side.

---

## 0. Prerequisites

- Node.js ≥ 20 and pnpm 9.15.0 (`corepack enable` is enough)
- Python ≥ 3.11
- A Supabase project: its **direct** Postgres connection string (port 5432) and its Auth settings
- TranzAct (and optionally Zoho Books) credentials for the workspace you will connect

---

## 1. One-time setup

```bash
./setup.sh
```

This creates `.venv`, installs backend + frontend deps, and creates the two env files
from their templates if missing. Then fill them in:

### 1a. Backend — repo root `.env`

Loaded by `vinayak/config.py`. Required outside dev mode: `DATABASE_URL`, `JWT_SECRET`,
`INTERNAL_API_KEY`, `FERNET_KEY`. Everything else is optional.

```dotenv
DATABASE_URL=postgresql://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres
JWT_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
INTERNAL_API_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
FERNET_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# Supabase Auth — set SUPABASE_JWT_SECRET to switch the backend from the legacy
# cookie JWT to verifying Supabase access tokens (the production mode).
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_JWT_SECRET=

# Optional — turns on the tool-calling agent + Claude phrasing.
ANTHROPIC_API_KEY=

# Optional — outbound email for approved actions (Resend or SMTP).
RESEND_API_KEY=
EMAIL_FROM=
```

ERP credentials are **not** env vars: they are entered in the UI and stored
Fernet-encrypted per workspace in `tool_connections`. Admin/user accounts live in
Supabase Auth; the backend's `users` table is the allowlist mapping email → workspace.

### 1b. Frontend — `apps/web/.env.local`

```dotenv
FASTAPI_INTERNAL_URL=http://localhost:8000
INTERNAL_API_KEY=            # identical to the backend value
NEXT_PUBLIC_APP_URL=http://localhost:3000
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
```

`INTERNAL_API_KEY` must match in both files: every FastAPI business route is
mounted behind `require_internal_key`, so a request without the BFF's
`X-Internal-Key` header is refused (403) before any auth or DB work. Only `/`
and `/health` are open.

### 1c. Database

```bash
psql "$DATABASE_URL" -1 -f vinayak/schema/init.sql
for f in vinayak/schema/migrations/*.sql; do psql "$DATABASE_URL" -1 -f "$f"; done
python -m vinayak.scripts.setup_db       # creates the admin allowlist row
```

Migrations are idempotent and ordered by number. Migration `019` matters on any
database created before September 2026: it drops the legacy
`tz_sync_runs.company_id` default that was mis-attributing TranzAct sync runs.

---

## 2. Run

```bash
./dev.sh      # backend :8000 + frontend :3000 (Ctrl+C stops both)
```

`dev.sh` exports `VINAYAK_DEV_MODE=1`, which relaxes the fail-hard checks
(ephemeral JWT secret, optional internal key, localhost CORS). Never set it in
production. The backend also starts APScheduler: eleven hourly jobs (ten
TranzAct reports + one Zoho batch), staggered by minute.

Useful flags:

```bash
AGENT_MODE=0  ./dev.sh          # force the deterministic keyword engine for /ask
AGENT_RUNNER=adk ./dev.sh       # drive the agent with the (incomplete) ADK adapter
```

---

## 3. The user flow

1. **Sign in** at `/login` via Supabase Auth. `proxy.ts` gates every `/` and `/w/*`
   route on a Supabase session; the BFF forwards the access token as a Bearer
   header and FastAPI verifies it (HS256 secret or JWKS) and maps the email to a
   workspace through `users`. An account with no `users` row is denied.
2. **Pick a workspace** — the landing page resolves the owner's brands; each brand
   lives under `/w/{brand}/dashboard` and the BFF tags calls with `X-Workspace-Id`.
3. **Connect a source.** `OnboardingGate` shows the Connect TranzAct / Zoho card
   until an active connection exists. Connect → test → migrate walks every report
   page by page with a resumable cursor (`tz_sync_cursor`), rebuilding the
   canonical layer after each chunk.
4. **Dashboard renders** from `canon_*` views only; each panel carries its own
   freshness. **Ask** answers through the tool-calling agent (or the keyword
   engine), grounded on tool evidence. **Approvals** holds every proposed action;
   nothing is sent until a person approves it, and an approved-but-undelivered
   message can be retried from the same page.

---

## 4. Verify

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/ -q            # unit suite
PYTHONPATH=. .venv/bin/python -m vinayak.eval.harness         # eval ship-gate (needs DB)
cd apps/web && pnpm typecheck                                 # frontend types
curl -s localhost:8000/health                                 # {"status":"ok"}
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/dashboard/tools   # 403 without X-Internal-Key
```

Checklist:

- [ ] `/health` is ok and the log shows "Scheduler started — 11 jobs registered".
- [ ] Sign-in lands on a workspace; an unlisted email gets "no workspace access".
- [ ] A fresh workspace shows the Connect card, not empty panels.
- [ ] After a migration, **Sync** lists `success` runs per pipeline **for that workspace**.
- [ ] The browser network tab shows only `/api/*` calls — never `:8000` or an ERP host.

---

## 5. Deploy

- **Backend** → Railway from `Dockerfile` (`railway.json`: health check on `/health`).
  Set every backend env var above; `.env.railway` is the gitignored paste-ready set.
- **Frontend** → Vercel (`vercel.json` builds `@vinayak/web`). Set the `apps/web`
  vars, with `FASTAPI_INTERNAL_URL` pointing at the private Railway URL.
- CI (`.github/workflows/ci.yml`) runs the unit suite on every push and the eval
  ship-gate when `EVAL_DATABASE_URL` is configured.
