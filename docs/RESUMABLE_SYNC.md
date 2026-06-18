# Resumable TranzAct sync (page-walk migration)

How Vinayak Brain OS pulls a brand's full TranzAct history without making the
user wait, and how it resumes a sync instead of re-fetching everything.

---

## 1. Why this exists

TranzAct's reporting endpoint, `POST /generate_report`, has **no usable
server-side date filter**. We probed 15 filter shapes (`from_date`/`to_date`,
the real column name `documentDate`, epoch-ms, `DD/MM/YYYY`, filter arrays,
`$gte/$lte`, top-level keys) against a known historical window — every one
returned the *full* report. The column metadata confirmed it: the date columns
carry `filter_type: null`. The TranzAct UI filters client-side.

Consequence: we cannot ask the API for "only the rows since last sync." Every
fetch returns the whole report. So a large history has to be pulled by **walking
pages**, and to avoid re-pulling everything each time we **persist a cursor**.

---

## 2. How the API paginates

- The request body carries `{"pagination": {"page": N, "per_page": P}}`.
- **`per_page` is ignored.** The server always returns a fixed page of **~50
  rows**, so `page` is effectively a 50-row index: page 1 = rows 1–50, page 2 =
  rows 51–100, and so on.
- Rows are returned **newest-first** (verified: 367 rows, 0 out-of-order pairs).
- The response includes `data.total_items` (the server's total row count).
- The server is **stateless** — it doesn't remember what it sent you. *We* pick
  the slice by sending the page number. The bookmark lives on our side.

There is no cursor/keyset token, so we use offset (page-number) pagination.

---

## 3. The rate limiter

`vinayak/adapters/tranzact/client.py` throttles to stay under TranzAct's
~10 requests/min/machine limit:

```
TRANZACT_REQUESTS_PER_MINUTE = 8          # configurable in .env
_MIN_INTERVAL = 60 / 8 = 7.5 s            # min gap between any two requests
```

The throttle is **global** (module-level), so all reports share one budget and
requests are effectively serialized. This is the dominant cost of a sync.

**Throughput ceiling:**

| metric | value |
|---|---|
| rows per page | 50 |
| seconds per page (1 request) | 7.5 s |
| **effective throughput** | **50 ÷ 7.5 ≈ 6.7 rows/s ≈ 400 rows/min** |

So sync time is essentially `rows ÷ 400` minutes, regardless of how the run is
triggered — the rate limit, not data size or trigger style, is the bottleneck.

---

## 4. The cursor

Table `tz_sync_cursor` (one row per company × report):

| column | meaning |
|---|---|
| `company_id`, `pipeline_name` | identity (primary key) |
| `next_page` | the next page to fetch on resume |
| `total_items` | last-seen server total (for the progress bar) |
| `rows_stored` | rows pulled during the current walk (progress) |
| `complete` | the walk reached the end of the report |
| `updated_at` | last update |

Defined in `schema/init.sql` and `schema/migrations/007_sync_cursor.sql`; the
route also runs `CREATE TABLE IF NOT EXISTS` lazily so it works on live DBs that
predate the migration.

---

## 5. The algorithm

### Fetch one chunk — `fetch_report(..., start_page, max_pages)`
Walks pages `start_page … start_page + max_pages − 1` (or until the data ends or
the time cap hits) and reports via `stats`:

- `last_page` — the last page fetched
- `total_items` — server total
- `reached_end` — a page came back empty (fully done)
- `more_available` — stopped on the chunk limit with a full last page (more left)
- `truncated` — stopped on the wall-clock cap

`BasePipeline.run_chunk(start_page, max_pages, …)` wraps that with
validate + upsert and returns the same stats. `run()` is just
`run_chunk(start_page=1, max_pages=None)` — a full pull, used for routine
refreshes (scheduler, full sync).

### The migration walk — `connections._run_single_pipeline`
Runs in a **background thread** (the user never waits):

```
cur = read_cursor(company, report)          # {next_page, rows_stored, complete}
if cur.complete and not restart:
    run_chunk(start_page=1, max_pages=REFRESH_PAGES)   # refresh newest only
    rebuild_canonical(); return

next_page = cur.next_page
while True:
    res = run_chunk(start_page=next_page, max_pages=CHUNK_PAGES)
    rows_stored += res.rows_fetched
    next_page    = res.last_page + 1
    complete     = res.reached_end or not res.more_available
    rebuild_canonical(company)                         # progressive dashboard fill
    write_cursor(next_page, total_items, rows_stored, complete)   # persisted each chunk
    if complete: break
```

Key properties:

- **Resumable / restart-safe.** The cursor is written after *every* chunk, so a
  process restart mid-migration resumes from `next_page` — never from scratch.
- **No waiting.** The endpoint returns immediately; the walk continues in the
  background. The UI polls `GET …/sync/pipelines` for a live progress bar.
- **Progressive.** The canonical layer is rebuilt after each chunk, so dashboard
  panels fill in as the walk proceeds.
- **Completion** is reached when a page returns no more data (`reached_end`) or
  the chunk stops without a full last page. On completion `next_page` resets to
  1 so future runs do a cheap newest-pages refresh.

### Config knobs (`connections.py`)

```
CHUNK_PAGES       = 10    # pages per chunk (~75 s at the rate limit)
REFRESH_PAGES     = 4     # newest pages pulled when refreshing a complete report
CHUNK_MAX_SECONDS = 150   # per-chunk wall-clock safety cap
```

---

## 6. Endpoints, triggers & UI

| Endpoint | Purpose |
|---|---|
| `GET  …/sync/pipelines` | per-report `{status, complete, rows_stored, total_items, next_page, percent}` |
| `POST …/sync/pipeline/{key}` | resume one report's walk |
| `POST …/sync/pipeline/{key}?restart=true` | re-walk one report from page 1 |
| `POST …/sync/all` | **Sync all** — re-walk every report from page 1 (full re-check; `restart=true` default) |
| `POST …/sync/refresh` | incremental newest-only refresh of every report (login/hourly) |

Three ways a sync is triggered:

1. **"Sync all" button** (`/sync/all`, `restart=true` by default). **Re-walks
   every report from page 1**, so clicking it again after a previous migration
   re-checks the whole report and re-adds any rows that were deleted/missing from
   the DB (content-hash upsert dedups — existing rows are overwritten, not
   duplicated). Runs in the background; the user can roam the dashboard. Onboarding
   and "re-sync to cross-check" are therefore the same action. (Pass
   `restart=false` to merely resume incomplete reports instead of re-walking.)
2. **On login — incremental refresh** (`/sync/refresh`). A client component
   (`SyncOnLogin`) fires this once per browser session. It pulls only the newest
   pages of each report (`refresh_only`) and never disturbs an in-progress
   migration. No-op if nothing's connected or a sync is already running.
3. **Hourly background — the scheduler.** Every report runs an incremental
   newest-only refresh hourly (staggered by minute), so data stays fresh even
   when no one is logged in. The full historical migration is **not** auto-run by
   the scheduler — that's the "Sync all" button's job.

**refresh_only mode:** pulls `REFRESH_PAGES` newest pages and upserts (content-hash
dedup). If the whole report fits in that window it's marked complete; otherwise
migration progress (`next_page` / `complete`) is left untouched — the refresh
just keeps the newest rows current.

**UI:** Settings → **Data sync** has a **Sync all** button plus a per-report list
with progress bars and **Run / Resume / Refresh** (and ↺ re-sync-from-start when
complete). Live progress also appears at the top of the **notification sidebar**
(`MigrationProgress`) while any sync is running — overall `done/total reports ·
rows` plus the reports currently in flight.

---

## 7. Real metrics

Measured on **kbrushes** (sales invoices, report 29): **367 rows = 8 pages**,
`total_items = 367`, span 25 Feb → 15 Jun. A full pull = 8 requests ≈ **60 s**.

### Per-chunk timing (CHUNK_PAGES = 10)

| step | time |
|---|---|
| 10 page requests × 7.5 s | ~75 s |
| canonical rebuild | ~1–5 s |
| **per chunk** | **~80 s** |

### Projected migration time (≈ `rows ÷ 400` min)

A brand with **2 years** of history, extrapolating sales_invoices from kbrushes
and estimating the other reports (only sales_invoices is grounded in real data):

| Report | ~rows (2 yr) | pages | chunks | time |
|---|---|---|---|---|
| sales_invoices | 2,400 | 48 | 5 | ~6.0 min |
| sales_orders | 2,000 | 40 | 4 | ~5.0 min |
| process_details | 2,000 | 40 | 4 | ~5.0 min |
| purchase_invoices | 1,800 | 36 | 4 | ~4.5 min |
| sales_quotations | 1,500 | 30 | 3 | ~3.8 min |
| purchase_orders | 1,200 | 24 | 3 | ~3.0 min |
| grn_qir | 1,200 | 24 | 3 | ~3.0 min |
| inventory_valuation* | 800 | 16 | 2 | ~2.0 min |
| process_routing* | 500 | 10 | 1 | ~1.3 min |
| ar_aging* | 150 | 3 | 1 | ~0.4 min |
| **Total** | **~13,500** | **~270** | — | **~34 min** |

(*snapshot/master reports — current state, not 2 years of history.)

- The whole 2-year migration runs **in the background** in roughly **30–45
  minutes** of wall clock; the user sees a progress bar and can leave.
- **Triggering reports "one by one" vs "all at once" takes the same total time** —
  the global rate limiter serializes requests either way.
- Raising `TRANZACT_REQUESTS_PER_MINUTE` from 8 → 10 (6 s/page) cuts ~20% off
  (~27 min), but risks 429s; the client backs off and retries on 429 anyway.

### Example call trace — sales_invoices, fresh brand

```
chunk 1: pages 1–10   → 500 rows   (~75s)  cursor.next_page=11  complete=false
chunk 2: pages 11–20  → 500 rows   (~75s)  cursor.next_page=21  complete=false
chunk 3: pages 21–30  → 500 rows   (~75s)  cursor.next_page=31  complete=false
chunk 4: pages 31–40  → 500 rows   (~75s)  cursor.next_page=41  complete=false
chunk 5: pages 41–48  → 400 rows + short last page → reached_end
                                    (~60s)  cursor.next_page=1   complete=true
total: ~2,400 rows, ~360s (~6 min), 5 cursor checkpoints, dashboard filling after each chunk
```

If the server restarts after chunk 3, the next run resumes at page 31 — the
1,500 rows already stored are not re-fetched.

---

## 8. Correctness notes

Offset pagination over a **newest-first** list has one known hazard: if rows are
inserted/deleted *during* a multi-chunk walk, page boundaries shift.

- **Inserts at the top (new invoices)** push older rows to higher page numbers.
  Resuming at the stored `next_page` then causes **overlap** (re-fetching a few
  rows), never a gap. Overlap is harmless — upserts are keyed on a **content
  hash**, so a re-fetched row overwrites in place rather than duplicating.
- **Deletions of recent rows** shift older rows to *lower* page numbers and
  could cause a **skip**. This is rare in an ERP (you don't usually delete recent
  invoices), and is reconciled by the next full refresh.
- A periodic **routine refresh** (scheduler / the "Refresh" button on a complete
  report) re-pulls the newest pages and picks up new + recently-edited rows.

The fully drift-proof alternative is cursor/keyset pagination
(`WHERE date < last_seen`), which needs a server-side filter this API doesn't
provide. Given that constraint, the page-walk + content-hash upsert +
periodic refresh is correct in practice.
