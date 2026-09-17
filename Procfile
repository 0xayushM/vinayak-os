# Two processes, one image.
#   web    — the API. Serves requests only; runs no background jobs.
#   worker — the syncs, the morning brief, the brain tick and the heartbeat.
#
# On Railway this is two services from the same repo, each with its own
# config-as-code file:
#   web    → railway.json         (uvicorn, healthcheck on /health)
#   worker → railway.worker.json  (python -m vinayak.worker, no healthcheck —
#            it serves no HTTP, so a healthcheck would fail every deploy)
# For the worker service: Settings → Config-as-code → Railway Config File →
# set the path to /railway.worker.json. Without that it reads railway.json,
# starts uvicorn and waits for a /health that the worker never serves.
# Share the API's variables with the worker (DATABASE_URL, FERNET_KEY, email
# provider, ALERT_EMAIL, ...). RUN_SCHEDULER must stay unset on web — the
# worker owns the jobs, and a second scheduler would run each one twice (the
# worker itself ignores the variable).
#
# The API watches the worker's heartbeat and emails ALERT_EMAIL if it stops
# (vinayak/health.py) — so a worker that is never deployed is noticed too.
web: uvicorn vinayak.api.main:app --host 0.0.0.0 --port $PORT
worker: python -m vinayak.worker
