# Marketing Workflow Spec — the revenue engine on data we already have

> Deep dive on "marketing" for our segment: not ads or content — **systematically
> extracting more revenue from the customer base the business already has**, using
> invoice history we already sync. Four engines, one campaign machine, holdout-proven
> attribution. Companion to `V0_FINANCE_SPEC.md` (shares the Wave-0 substrate:
> tools, ledger, approval inbox, events).

**Grounding — live kbrushes numbers (July 2026):** 32 active customers · 124 SKUs ·
avg 6.4 SKUs per customer (max 46) · 7 customers with a computable order rhythm, of
which **6 are past their reorder window today** · 15 customers silent 60+ days,
including KIRPAL BRUSH (₹21L lifetime, silent since 31 Mar) and YAHIA STORES (₹5.9L,
silent since 17 Apr). The demo writes itself.

---

## 1. The one hard data gap: contacts

TranzAct reports carry **no email or phone**. Verified: neither `tz_sales_invoices`
nor `canon_customer` has a contact field. Fix is small because the customer count is
small (~34):

```sql
CREATE TABLE customer_contacts (
  company_id    TEXT NOT NULL,
  customer_code TEXT NOT NULL,        -- joins canon_customer
  contact_name  TEXT, role TEXT,      -- 'owner', 'purchase manager'
  email         TEXT, whatsapp        TEXT,
  consent       BOOLEAN DEFAULT TRUE, -- can we message them?
  added_by      TEXT, updated_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (company_id, customer_code)
);
```

Capture: a settings page with the 34 customers listed + CSV import. **This is a
30-minute task for the owner's accountant, and it's the single prerequisite for
everything below.** No contact → customer silently excluded from campaigns, shown
as "missing contact" count on the campaign screen.

---

## 2. The four engines (detection formulas)

All computed from `tz_sales_invoices` / canonical equivalents. Each engine yields a
**target list**: (customer, reason, evidence, suggested message angle, revenue at stake).

### E1 · Reorder nudges — "your regulars forgot to order"
- **Customer cadence:** for customers with ≥ 4 distinct order dates in 12 mo:
  `median_gap = median(gap between consecutive order dates)`;
  regular ⇢ `median_gap ≤ 60d` and `stddev(gap)/mean(gap) < 1` (rhythm is real).
- **Trigger:** `days_since_last_order > 1.5 × median_gap`.
- **Per-SKU variant** (sharper, more volume): same formula per (customer, SKU) with
  ≥ 3 purchases — catches "they still buy from us but stopped buying THIS item"
  (which is quiet share-of-wallet loss to a competitor).
- **Revenue at stake:** `avg order value` (customer variant) or `avg line value ×
  expected orders/quarter` (SKU variant).
- Tool: `mkt.get_reorder_due()` — supersedes Pulse P5's read-only card.

### E2 · Win-back — "customers who left money on the table"
- **Lapsed:** `days_since_last_order > max(2 × median_gap, 60d)` (cadence-aware so a
  quarterly buyer isn't "lapsed" after 6 weeks).
- **Rank by:** trailing-12-mo revenue × recency decay `exp(-days_silent/180)` — a
  ₹21L customer silent 3 months outranks a ₹50K customer silent a year.
- **Exclusion:** customers whose *last interaction* was a payment dispute or who
  hold `credit.STOP` (see §4 guardrails) — don't win back people who don't pay.
- Tool: `mkt.get_lapsed_customers()`.

### E3 · Cross-sell — "buyers of A who never tried B"
- **Affinity (lift), computed across all customers:**
  `lift(A→B) = P(buys B | buys A) / P(buys B)`, on the customer level (not invoice
  level — B2B baskets span orders). Keep pairs with `lift ≥ 2`, `support ≥ 3 customers`.
- **Targets:** customers who buy A (≥ 2 orders) and never bought B, for the top-lift
  pairs. Suggested angle: "customers like you also use B".
- With 32 customers this is coarse — honest v1 is category-level lift (124 SKUs →
  ~15 categories), SKU-level once we onboard bigger books.
- Tool: `mkt.get_cross_sell_targets()`.

### E4 · Seasonal / stock push — "sell what the season (or the warehouse) wants moved"
- **Seasonality index:** per category `idx(month) = avg revenue in that calendar
  month / overall monthly avg` (needs 12+ mo history; kbrushes has ~5 — ships later
  or uses owner-declared seasonality from the business profile).
- **Stock push (works today):** dead-stock list (existing) × customers who
  historically bought that category → clearance targets. Turns the P7 trapped-capital
  card into revenue.
- Tool: `mkt.get_push_targets(kind='seasonal'|'stock')`.

**Targeting overlay — RFM segments** (used by all engines for tone, not selection):
recency/frequency/monetary terciles → labels: `champion` (recent+frequent+big),
`loyal`, `at_risk` (was frequent, going quiet), `hibernating`. Tool:
`mkt.get_segments()`. Champions get "thank you + new item" tone; at_risk get
"we value you" tone; hibernating get incentive tone (incentive = owner's choice).

---

## 3. The campaign machine (one mechanism for all four engines)

```
detect (engine query) → build audience → draft messages → owner approves batch
→ send (email now, WhatsApp later) → watch invoices → attribute → report
```

### Tables
```sql
CREATE TABLE campaigns (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id TEXT NOT NULL,
  engine TEXT NOT NULL,               -- reorder | winback | crosssell | push
  name TEXT, template TEXT,           -- message template w/ placeholders
  holdout_pct INT DEFAULT 20,
  status TEXT DEFAULT 'draft',        -- draft | approved | sending | done
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE campaign_targets (
  campaign_id UUID REFERENCES campaigns(id),
  company_id TEXT NOT NULL,
  customer_code TEXT NOT NULL,
  arm TEXT NOT NULL,                  -- 'send' | 'holdout'
  action_id UUID,                     -- ledger row for the sent message
  reason JSONB,                       -- engine evidence (days silent, SKUs, ₹ at stake)
  baseline_rev NUMERIC,               -- trailing 90d revenue at send time
  attributed_rev NUMERIC,             -- filled by attribution job
  PRIMARY KEY (campaign_id, customer_code)
);
```

### Message flow — reuses Wave 0 exactly
Each `send`-arm target becomes one `mkt.draft_campaign_message` proposal
(side_effect=`writes`) → `actions` ledger → **batch approval UI** (approve all /
per-message edit / reject) → `notify.send_approved`. The numeric guard runs on every
draft: any ₹ figure or product claim must come from that customer's own evidence.

### Attribution (the trust engine)
- **Response:** target places ≥ 1 order within `attribution_window = 21d` of send.
  `attributed_rev = Σ invoice line_total in window` (cross-sell: only lines of the
  promoted SKU/category).
- **Incremental revenue (the honest number):**
  `lift = avg(attributed_rev | send arm) − avg(attributed_rev | holdout arm)`,
  `incremental = lift × n_send`. Report both raw and incremental; sell with incremental.
- **Holdout assignment:** random 20% per campaign, stratified by RFM segment,
  minimum 3 customers (below that, skip holdout and mark results "unproven").
- Runs as a nightly job; results land on a Pulse card and the campaign screen.
  Tool: `mkt.get_campaign_results(campaign_id)`.

---

## 4. Guardrails (what keeps this from annoying customers or embarrassing the owner)

1. **Frequency cap:** max 1 marketing message per customer per 14 days, across ALL
   engines — enforced in the executor idempotency layer (`entity_ref = customer`).
2. **The AR synapse — never market to a defaulter:** any customer with
   `sales.check_customer_credit = STOP` is excluded from every audience; `CAUTION`
   customers get nudges but never incentive offers. (Consumes the same verdict tool
   as Wave 3 — Finance and Marketing sharing one brain, literally.)
3. **Owner approves every batch in v1.** Auto-send (green gate) only after ≥ 3
   campaigns with > 80% unedited approval — earn autonomy with data.
4. **Incentives are owner-typed, never model-invented.** Templates have an
   `{incentive}` slot the owner fills; the model may not fabricate discounts.
5. **Consent + unsubscribe:** `customer_contacts.consent`; any reply of
   "stop/unsubscribe" flips it and the system hard-excludes.

---

## 5. Tools (contract entries)

| Tool | side_effect | Description |
|---|---|---|
| `mkt.get_reorder_due` | read | E1 target list with cadence evidence + ₹ at stake |
| `mkt.get_lapsed_customers` | read | E2 ranked win-back list |
| `mkt.get_cross_sell_targets` | read | E3 (category-level v1) buyers-of-A-not-B |
| `mkt.get_push_targets` | read | E4 seasonal/stock clearance audiences |
| `mkt.get_segments` | read | RFM labels per customer |
| `mkt.create_campaign` | writes | Create campaign + audience + holdout split (confirm gate) |
| `mkt.draft_campaign_message` | writes | One personalised message → ledger (confirm gate) |
| `mkt.get_campaign_results` | read | Raw + incremental revenue, per campaign and overall |
| `contacts.list_missing` | read | Customers without contact info (nag list) |

**Events:** emits `campaign.sent`, `customer.reactivated` (win-back target ordered);
consumes `credit.flagged` / verdicts (exclusions), `stock.dead` (E4 audiences).

---

## 6. Channels

- **v1: email** — same Resend/SMTP hookup as collections (one integration, two uses).
- **v2: WhatsApp** — where Indian SMB response rates actually live. Needs WhatsApp
  Business API via a BSP (Gupshup/Interakt/Twilio), template pre-approval, and DLT
  compliance. **2–4 week lead time — start the registration paperwork during v0.**

---

## 7. Where it fits in the waves

| Wave | Marketing deliverable |
|---|---|
| 1.5 (Pulse) | P5 reorder card ships read-only — the teaser, no send capability |
| 2 (Collections) | email channel + approval inbox + ledger get built — marketing inherits all three |
| **4 — Campaign engine v1** (~2 wks) | `customer_contacts` + capture UI · E1 + E2 engines · campaign/targets tables · batch approval · attribution job · results card. *Replaces the old "Wave 4 = PO drafts" — revenue proof outranks procurement.* |
| **5 — Engines & channel** (~2 wks) | E3 + E4 · RFM tones · WhatsApp channel · holdout automation · "revenue we caused" cumulative card |

**Definition of done (Wave 4):** owner approves one reorder campaign to ~10 dealers;
21 days later the results card shows raw and incremental revenue with the holdout
comparison — a number he can repeat to another owner.

---

## 8. Open questions for the Technoplast owners (take to the next meeting)

1. Do they have dealer WhatsApp numbers / emails on file (even in a phone/diary)?
   → sizes the contact-capture task.
2. Who should approve campaigns — owner or sales head?
3. Incentive policy: are they willing to offer anything on win-backs (₹ off, credit
   days, freebie), or goodwill-only messages first?
4. Tone: Hindi, English, or Hinglish for dealer messages? (Template design depends.)
5. Are there customers we must never message (family accounts, disputes, related
   entities — e.g. kbrushes' book literally contains "VINAYAK TECHNOPLAST" as a
   customer)?
