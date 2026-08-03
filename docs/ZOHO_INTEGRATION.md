# Zoho Books Integration — setup & architecture

> Source #2. TranzAct and Zoho now live in separate namespaces:
> **`/tranzact/*`** (existing connection/sync endpoints; legacy `/connections/*`
> still works so the frontend is unbroken) and **`/zoho/*`** (new).
> Adapter code mirrors the same split: `vinayak/adapters/{tranzact,zoho}/` and
> `vinayak/pipelines/{tranzact-rooted files, zoho/}`.

## 1. One-time setup per customer org (when the Zoho account exists)

1. **Create the API client** — go to `api-console.zoho.in` (note: `.in` for Indian
   orgs) → **Self Client** → Create. Copy the *Client ID* and *Client Secret*.
2. **Generate a grant code** — in the Self Client screen: scope
   `ZohoBooks.fullaccess.READ`, duration 10 minutes, generate. Copy the code.
3. **Exchange for a refresh token** (within 10 minutes):
   ```
   curl -X POST "https://accounts.zoho.in/oauth/v2/token" \
     -d grant_type=authorization_code -d code=GRANT_CODE \
     -d client_id=CLIENT_ID -d client_secret=CLIENT_SECRET
   ```
   Save the `refresh_token` from the response — it never expires unless revoked.
4. **Find the organization ID** — Zoho Books → Settings → Organization Profile
   (or `GET /organizations`).
5. **Connect in our product**:
   ```
   POST /zoho/connect
   { "client_id": "...", "client_secret": "...", "refresh_token": "...",
     "organization_id": "...", "dc": "in" }
   ```
   The endpoint live-tests the credentials against Zoho (fetches the org) before
   storing them Fernet-encrypted in `tool_connections` (tool_name `zoho_books`).
   Nothing is stored if the test fails.

Then `POST /zoho/sync` for the first pull; the scheduler refreshes hourly at :12
for every workspace with an active connection (no-op otherwise).

## 2. What syncs (Phase 1)

| Pipeline | Zoho endpoint | Lands in | Why it matters |
|---|---|---|---|
| `zoho_contacts` | `/contacts` | `zb_contacts` | customers+vendors **with email/phone** (marketing engine's missing contact data, free) and per-contact payment terms |
| `zoho_invoices` | `/invoices` | `zb_invoices` | invoice headers **with live `balance`** — real AR per invoice, plus `last_payment_date` (real payment behaviour, no snapshot inference needed) |
| `zoho_bills` | `/bills` | `zb_bills` | purchases + live accounts payable |
| `zoho_items` | `/items` | `zb_items` | item master with stock **and `purchase_rate` (cost!)** — real margin becomes computable for Zoho orgs |

All four: full-page walk (`page`/`per_page=200`/`has_more_page`), throttled to
~50 req/min (limit is 100), Pydantic-validated (bad rows skipped, never crash),
upserted on Zoho's stable IDs, raw JSON retained per row, runs logged to
`tz_sync_runs` (`pipeline_name` like `zoho_%`).

## 3. Architecture notes

- **Auth** (`adapters/zoho/auth.py`): refresh-token → 1-hour access tokens,
  cached per org, renewed 2 min early, DC-aware (`in`/`com`/`eu`/`au`).
- **Client** (`adapters/zoho/client.py`): retries with backoff on 429/5xx, one
  forced token refresh on 401, Zoho in-band error codes surfaced.
- **Pipelines** (`pipelines/zoho/base.py`): deliberately does NOT inherit the
  TranzAct `BasePipeline` (which is coupled to the TranzAct client). Same safety
  contract: stale-is-better-than-empty, validated rows only, in-place upserts.
- **Better-source dividends**: Zoho gives three things TranzAct structurally
  couldn't — contact info, real payment dates, and item cost. Each one
  removes a workaround elsewhere in the product (contact capture form, AR
  snapshot inference, margin refusal).

## 4. Phase 2 — honest gaps (next build)

1. **Canonical mapping** (`canonical/zoho_canonical.py`): map `zb_*` →
   `canon_customer` / `canon_sales_invoice` / `canon_payment` with
   `source='zoho_books'`. This is the step that proves the source-agnostic
   architecture — and what the dashboard needs.
2. **Dashboard reads**: today's panels query `tz_*` tables directly, so a
   Zoho-only workspace shows empty panels until either (a) panels move to
   canonical tables (right fix, per the build manual) or (b) interim zb-aware
   queries. Decision needed at Phase 2 kickoff.
3. **Invoice line items**: the list endpoint returns headers only; line-level
   detail (top SKUs etc.) needs per-invoice `GET /invoices/{id}` — batched,
   rate-limit-aware, on-demand backfill.
4. **Customer payments** (`/customerpayments`): exact payment events for the AR
   history that `ar_daily_snapshot` approximates for TranzAct.
5. **Webhooks**: Zoho supports push notifications — the future real-time trigger
   source for the event bus, replacing hourly pulls.

Sources: [Zoho Books API introduction](https://www.zoho.com/books/api/v3/introduction/) ·
[OAuth](https://www.zoho.com/books/api/v3/oauth/) ·
[Invoices](https://www.zoho.com/books/api/v3/invoices/) ·
[API guide (limits)](https://www.getknit.dev/blog/zoho-books-api-directory-9eeBzn)
