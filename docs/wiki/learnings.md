# Learnings

Things that surprised us, dated, and what we do differently now.

- 2026-09-09 · `tz_sync_runs` had a column default that tagged every TranzAct sync run to one workspace; nothing complained because the insert never failed. → Migration 019 dropped the default; write company_id explicitly everywhere.
- 2026-09-07 · TranzAct silently changed report identifiers; `/generate_report` returned 500 instead of 404 for the old ids. → Resolve ids through the catalogue at fetch time; alert on the first failed sync, not the tenth.
- 2026-05 · Re-fetching overlapping pages multiplied rows 7–32× before deduplication. → Content-hash upsert keys; never truncate-and-reload.
