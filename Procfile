# Two processes, one image.
#   web    — the API. Serves requests only; runs no background jobs.
#   worker — the syncs, the morning brief, the brain tick and the heartbeat.
#
# On Railway this is two services from the same repo. Railway deprecated
# config-as-code files (no new service may opt in after 28 Aug 2026; existing
# ones stop being read on 1 Dec 2026), so the worker is set in the dashboard:
#   worker → Settings → Deploy → Custom Start Command: python -m vinayak.worker
#            and an EMPTY Healthcheck Path — it serves no HTTP, so a
#            healthcheck would fail every deploy.
# web still reads railway.json until 1 Dec; before then, copy its healthcheck
# (/health, 30s) and restart policy (on failure, 3) into web's dashboard.
# Share the API's variables with the worker as references (${{web.DATABASE_URL}}
# and so on; FERNET_KEY must match). A reference to a variable web never set
# arrives as an empty string, which numeric settings treat as unset. RUN_SCHEDULER must stay unset on web — the
# worker owns the jobs, and a second scheduler would run each one twice (the
# worker itself ignores the variable).
#
# The API watches the worker's heartbeat and emails ALERT_EMAIL if it stops
# (vinayak/health.py) — so a worker that is never deployed is noticed too.
web: uvicorn vinayak.api.main:app --host 0.0.0.0 --port $PORT
worker: python -m vinayak.worker
