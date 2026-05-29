# Vinayak Brain OS — Setup Guide

A pnpm monorepo with a **Next.js frontend** (Vercel) and a **FastAPI backend** (Railway / any Docker host).

---

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Node.js | ≥ 20 | [nodejs.org](https://nodejs.org) |
| pnpm | 9.x | `npm install -g pnpm@9` |
| Python | 3.11 | [python.org](https://python.org) |
| Git | any | [git-scm.com](https://git-scm.com) |

You also need a **Supabase** project (free tier works).

---

## 1. Clone the repo

```bash
git clone https://github.com/0xayushM/vinayak-os.git
cd vinayak-os
```

---

## 2. Environment variables

Copy the example file and fill in real values:

```bash
cp .env.example .env
```

Open `.env` and set every variable. Key ones:

| Variable | How to get it |
|---|---|
| `DATABASE_URL` | Supabase → Settings → Database → URI (port 5432, Direct connection) |
| `JWT_SECRET` | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `FERNET_KEY` | `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `INTERNAL_API_KEY` | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_EMAIL` | Your login email for the dashboard |
| `ADMIN_PASSWORD` | Your login password for the dashboard |
| `TRANZACT_EMAIL` | TranzAct ERP account email |
| `TRANZACT_PASSWORD` | TranzAct ERP account password |
| `DEFAULT_COMPANY_ID` | `kbrushes` |

---

## 3. Set up Supabase schema

Run the SQL schema against your Supabase database:

```bash
psql $DATABASE_URL -f vinayak/schema/init.sql
```

Or paste the contents of `vinayak/schema/init.sql` into **Supabase → SQL Editor → Run**.

---

## 4. Python backend

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# Install dependencies
pip install -r vinayak/requirements.txt

# Start the FastAPI server
uvicorn vinayak.api.main:app --reload --port 8000
```

Backend is now running at **http://localhost:8000**  
Docs available at **http://localhost:8000/docs**

---

## 5. Next.js frontend

In a **separate terminal**:

```bash
# Install dependencies
pnpm install

# Start the dev server
pnpm dev
```

Frontend is now running at **http://localhost:3000**

---

## 6. Log in

Open **http://localhost:3000** and sign in with the `ADMIN_EMAIL` / `ADMIN_PASSWORD` you set in `.env`.

---

## Production Deployment

### Frontend → Vercel

1. Push to GitHub
2. Import repo on [vercel.com](https://vercel.com)
3. Add these environment variables in Vercel project settings:

| Variable | Value |
|---|---|
| `FASTAPI_INTERNAL_URL` | URL of your deployed backend |
| `INTERNAL_API_KEY` | Same value as in `.env` |

### Backend → Railway (recommended free tier)

1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Select this repo — Railway auto-detects the `Dockerfile` and `railway.json`
3. Add all backend env vars from `.env` in the Railway **Variables** tab
4. Go to **Settings → Networking → Generate Domain** to get your backend URL
5. Paste that URL as `FASTAPI_INTERNAL_URL` in Vercel

---

## Project Structure

```
vinayak-os/
├── apps/
│   └── web/                  # Next.js frontend (TypeScript)
│       ├── app/              # App Router pages + API routes (BFF proxy)
│       └── lib/              # Shared utilities
├── vinayak/                  # Python FastAPI backend
│   ├── api/
│   │   ├── main.py           # FastAPI app entry point
│   │   └── routes/           # auth, connections, dashboard, ai
│   ├── pipelines/            # TranzAct data sync pipelines (10 reports)
│   ├── adapters/tranzact/    # TranzAct API client + auth
│   ├── schema/
│   │   └── init.sql          # Supabase table definitions
│   └── requirements.txt
├── Dockerfile                # Backend container (used by Railway)
├── railway.json              # Railway deployment config
├── vercel.json               # Vercel build config
├── package.json              # pnpm workspace root
└── pnpm-workspace.yaml
```

---

## Common Issues

**`python: command not found`** — Use `python3` or activate the venv: `source venv/bin/activate`

**`psycopg2` install fails** — Install system deps first:
```bash
# macOS
brew install libpq
# Ubuntu/Debian
sudo apt-get install libpq-dev python3-dev
```

**Login shows "Could not reach the server"** — The FastAPI backend is not running. Start it with step 4 above, or set `FASTAPI_INTERNAL_URL` to your deployed backend URL.

**TranzAct sync returns 0 rows** — Check `TRANZACT_EMAIL` and `TRANZACT_PASSWORD` in `.env`. Run the test endpoint: `curl -X POST http://localhost:8000/connections/tranzact/test`
