# Two processes, one image.
#   web    — the API. Serves requests only; runs no background jobs.
#   worker — the syncs, the morning brief, and the brain tick.
#
# On Railway this is two services from the same repo: the second one overrides
# its start command with the worker line below and shares the API's variables,
# minus RUN_SCHEDULER (which must stay unset on web).
web: uvicorn vinayak.api.main:app --host 0.0.0.0 --port $PORT
worker: python -m vinayak.worker
