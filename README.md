# Vinayak — Business Brain OS (BIDE)

A grounded, agentic operating system for running an SMB: it ingests the
company's real operational data (TranzAct, Zoho), normalises it into one
canonical model, answers questions with **calibrated confidence and cited
evidence**, remembers what it learns, and proposes actions that a human approves.

- **Backend** — FastAPI (`vinayak/`), Postgres on Supabase, hourly sync scheduler.
- **Frontend** — Next.js (`apps/web/`), Supabase Auth, BFF proxy to the backend.
- **Deploy** — backend on Railway (`Dockerfile`, `railway.json`), frontend on Vercel (`vercel.json`).

## Run it locally

```bash
./setup.sh   # one-time: python venv + deps, pnpm install, env templates, test run
./dev.sh     # backend :8000 + frontend :3000 together (Ctrl+C stops both)
```

Fill in `.env` (backend) and `apps/web/.env.local` (frontend) — `setup.sh`
creates them from the templates. `.env.railway` / `.env.vercel` are the
paste-ready production variable sets (all gitignored).

## Verify

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/ -q          # unit suite
PYTHONPATH=. .venv/bin/python -m vinayak.eval.harness       # eval ship-gate (needs DB)
cd apps/web && pnpm typecheck                               # frontend types
```

## Where to read next

- `docs/ARCHITECTURE.md` — how the system runs: module map, call-flows, where to change what.
- `docs/vinayak/The_Business_IDE_BIDE.docx` — the product & architecture reference (Part 1A = the finalized architecture).
- `implementation.md` — the development plan and current status, layer by layer.
- `docs/RUN_GUIDE.md`, `docs/TOOL_CATALOG.md`, `docs/V0_FINANCE_SPEC.md`, `docs/ZOHO_INTEGRATION.md` — operating guide and specs.
