# Tool Catalog — every workflow, every tool, every connection

> The single reference for Layers 7–10 development. Each of the 94 workflows from the
> Build Manual is mapped to the tools it gathers with and acts through. Tools are
> **shared bricks** — defined once, reused by every workflow that needs them.
> Status legend: ✅ ready now (wraps an existing query / existing data) ·
> 🟡 needs a new query over data we already sync ·
> 🔴 blocked on a data source we don't ingest yet (adapter/vector store first) ·
> ⚙️ needs an external service hookup (email/WhatsApp provider, write-back API).

**Naming:** `domain.verb_noun`. **Kinds:** `read` (never gated), `action` (proposes; the
ledger + approval inbox execute), `memory`, `meta`, `external`.
**The rule that never bends:** no tool both reads and writes; `moves_money` / `files_regulator`
actions ALWAYS terminate at a human regardless of confidence.

---

## 0. Core tools (cross-field, used by nearly every workflow)

| Tool | Kind | Description | Status |
|---|---|---|---|
| `memory.get_business_profile` | memory | Industry, fiscal year, margin benchmark, seasonality — the agent's standing context | ✅ |
| `memory.get_facts` | memory | Owner-taught durable facts (payment terms, relationships), with stale flags | ✅ |
| `memory.save_fact` | action (writes) | Store a fact the owner just confirmed; supersedes the old value | ✅ |
| `meta.get_data_freshness` | meta | Last-sync age per report; lets the agent hedge or refuse on stale data | ✅ wraps `get_sync_health` |
| `meta.get_ingest_quality` | meta | Unmapped/dropped-row counts per source — "how trustworthy is this data" | ✅ |
| `notify.draft_email` | action (writes) | Compose an email (to, subject, body) as a PROPOSAL for the approval inbox | 🟡 template + ledger |
| `notify.send_approved` | external | Executor-only (never callable by the model): sends what a human approved | ⚙️ SMTP/Resend |
| `notify.send_whatsapp` | external | Same pattern for WhatsApp | ⚙️ provider + DLT reg. |
| `notify.post_inapp` | action (writes) | In-app notification/toast to a user | ✅ notification table exists |
| `docs.search` | read | Semantic search over uploaded documents (contracts, KB, policies) | 🔴 vector store (L5) |
| `events.publish` | infra | Not a model tool — workflows emit events (`invoice.overdue`) via code | 🟡 events table |

---

## 1. Finance & Accounts (17 workflows)

The anchor field. Reads are largely ✅ today; the money-touching actions are the most tightly gated in the system.

### Read tools

| Tool | Description | Status |
|---|---|---|
| `fin.get_revenue_summary` | Sales for a window: goods + invoiced bases, counts, averages, YTD | ✅ |
| `fin.get_revenue_trend` | Month-by-month revenue with MoM deltas, any range | ✅ |
| `fin.get_revenue_daily` | Day-level revenue, gap-filled | ✅ |
| `fin.get_sales_by_category` | Revenue split by product category | ✅ |
| `fin.get_top_customers` | Ranked customers with revenue, share, invoice counts | ✅ |
| `fin.get_customer_concentration` | Top-5 share + Others; the dependence-risk number | ✅ |
| `fin.get_customer_changes` | Who grew / shrank vs the prior period | ✅ |
| `fin.get_customer_movement` | New customers and lapsed ones | ✅ |
| `ar.get_summary` | Total outstanding, overdue, aging buckets, top exposures | ✅ |
| `ar.get_customer_exposure` | Per-customer outstanding, oldest days overdue | ✅ |
| `ar.get_collections_priority` | The chase list, ranked by impact × lateness | ✅ |
| `ar.get_dso` | Days-sales-outstanding (how long money takes to come home) | ✅ |
| `ar.get_invoice_details` | One invoice: lines, amounts, due date, status — for chase emails | 🟡 |
| `ar.get_payment_history` | One customer's payment behaviour over time (avg days-to-pay, trend) | 🟡 |
| `ap.get_purchases_summary` | Spend, vendors, invoices for a window | ✅ |
| `ap.get_top_vendors` | Ranked vendor spend + share | ✅ |
| `ap.get_open_pos` / `ap.get_overdue_pos` | POs awaiting delivery / late | ✅ |
| `fin.get_cashflow_forecast` | Projected in/out from AR due dates + PO commitments + order book | 🟡 the flagship new query |
| `fin.get_gl_entries` | Ledger/journal reads | 🔴 GL not in synced reports |

### Action tools

| Tool | side_effect | Description | Status |
|---|---|---|---|
| `ar.draft_collection_email` | writes | Personalised payment chase from live invoice data → approval inbox | 🟡 **Wave 2 centrepiece** |
| `ar.record_promise_to_pay` | writes | Log "customer promised payment by X" as a decaying fact | ✅ via `memory.save_fact` |
| `fin.flag_transaction` | writes | Mark a transaction/invoice suspicious for human review | 🟡 |
| `fin.draft_journal_entry` | writes → **money-gated** | Draft a JE for human posting | 🔴 needs GL + write-back |
| `fin.assemble_gst_summary` | **files_regulator** | Assemble return data; a HUMAN files, always | 🔴 GST data not synced |
| `fin.release_payment` | **moves_money** | Never automated. Exists only as an inbox-executed act | 🔴 banking integration |

### Workflow → tool map

| Workflow | Gather | Act | Status / notes |
|---|---|---|---|
| NL financial querying | all Finance reads + memory | — | ✅ live today; Wave 1 ports it to the agent |
| AR aging & collections | `ar.get_collections_priority`, `ar.get_invoice_details`, `ar.get_payment_history`, `memory.get_facts` | `ar.draft_collection_email` → `notify.send_approved` | 🟡 **Wave 2** · emits `collection.chased` |
| Credit & concentration risk | `ar.get_customer_exposure`, `fin.get_customer_concentration`, `ar.get_payment_history` | `sales.flag_customer_credit` | 🟡 **Wave 3 synapse** · emits `credit.flagged` |
| Cashflow forecasting | `fin.get_cashflow_forecast`, `ap.get_open_pos`, `sales.get_order_book` | `notify.post_inapp` alert | 🟡 Wave 4-ish |
| Duplicate-payment / fraud | `ap.get_purchases_summary` + 🟡 pattern query | `fin.flag_transaction` | 🟡 |
| Transaction categorisation | 🔴 GL feed | auto-code entries | 🔴 |
| Invoice & bill capture (OCR) | 🔴 email/scan intake | post draft | 🔴 |
| Reconciliation · Cash application | 🔴 bank feed | match/apply | 🔴 |
| Journal entries · Period close · Statements | 🔴 GL | drafts, checklists | 🔴 |
| GST returns · e-Invoicing · Payroll · Continuous audit | 🔴 GST/HR/GL data | assemble → HUMAN files/pays | 🔴 |

**Connections:** feeds Sales (credit gate), Strategy (cash, concentration). Fed by Order Tracking (dispatch→invoice) and every spending field.

---

## 2. Sales (8 workflows)

| Tool | Kind | Description | Status |
|---|---|---|---|
| `sales.get_quote_pipeline` | read | Won / open / conversion rate + quote list | ✅ |
| `sales.get_order_book` | read | Open orders, value, dispatched %, overdue | ✅ |
| `sales.get_overdue_orders` | read | Orders past delivery date (we're late to customers) | ✅ |
| `sales.check_customer_credit` | read | **The synapse tool.** Composite verdict: outstanding + overdue + terms + payment history → ok / caution / stop | 🟡 Wave 3 |
| `sales.get_win_loss` | read | Why quotes were lost | 🔴 loss reasons not captured in source |
| `sales.flag_customer_credit` | action (writes) | Set a visible credit flag on a customer (quotes/orders UI shows it) | 🟡 Wave 3 · consumes `invoice.overdue` |
| `sales.draft_followup` | action (writes) | Nudge email for a quiet quote/customer, via notify | 🟡 |
| `sales.draft_quote` | action (writes) | Draft a quotation (price, stock, credit-aware) | 🔴 needs source write-back |
| Lead gen / ICP scoring / outreach sequencing | — | — | 🔴 no lead/CRM source connected |

| Workflow | Gather | Act | Status |
|---|---|---|---|
| Quote & proposal generation | `inv.get_summary` + `sales.check_customer_credit` + `fin.get_top_customers` | `sales.draft_quote` | 🔴 write-back; the *credit check* part ships in Wave 3 |
| Follow-up nudges | `sales.get_quote_pipeline`, `fin.get_customer_movement` | `sales.draft_followup` | 🟡 |
| Deal forecasting | `sales.get_quote_pipeline`, `sales.get_order_book` | publish to Finance | 🟡 emits `forecast.updated` |
| Pipeline hygiene | `sales.get_quote_pipeline` | `notify.post_inapp` | 🟡 |
| Win/loss · Lead gen · ICP · Outreach | — | — | 🔴 |

**Connections:** consumes `invoice.overdue`, `credit.flagged` (Finance), `stock.low` (Inventory). Emits demand signals to Inventory/Production.

---

## 3. Marketing (7 workflows) — mostly blocked, honestly

No marketing data source (ads, social, web analytics) is connected, and none is planned before Stage 3.

| Workflow | What it needs | Status |
|---|---|---|
| Content generation / SEO briefs / ad copy | `memory.get_business_profile` + `mkt.draft_content` (writes) | 🟡 pure-LLM drafting possible; low value until channels exist |
| Campaign performance / segmentation / social / sentiment | ad & social adapters | 🔴 |

**Connections (future):** feeds Sales (leads), R&D (demand signal). Fed by Support (FAQs→content).

---

## 4. Support (7 workflows) — blocked on ticket ingestion

The prerequisite is an email/IMAP or helpdesk adapter (Layer 2) + vector store (Layer 5). High value, right after Stage 2.

| Tool (future) | Description |
|---|---|
| `sup.get_ticket` / `sup.list_tickets` | Read tickets with status, sentiment, customer link |
| `sup.classify_ticket` | Topic + priority + sentiment scoring |
| `sup.draft_reply` (writes) | Grounded reply from `docs.search` + customer 360 |
| `sup.escalate` (writes) | Route to a person, with reason |
| `sup.extract_kb_article` (writes) | Turn a resolved ticket into a draft KB entry |

All 7 workflows (deflection, routing, escalation, replies, KB gen, SLA, themes) compose from these five. **Emits** `ticket.themed` → R&D/QA; **consumes** order/AR context for customer-aware replies.

---

## 5. CRM (6 workflows)

The customer axis. V1 is buildable NOW from sales+AR data; full 360 waits for Support.

| Tool | Description | Status |
|---|---|---|
| `crm.get_customer_360` | One customer: revenue history, AR state, orders, facts, (later: tickets) | 🟡 composite over existing reads |
| `crm.get_health_score` | Fused score: payment behaviour + order momentum (+ tickets later) | 🟡 v1 two-signal; Synapse 6 completes it |
| `crm.get_segments` | Customers bucketed by value/behaviour | 🟡 |
| `crm.suggest_next_action` | Read composite: what to do about this account | 🟡 agent-composed, no new query |
| `crm.merge_duplicates` (writes) | Entity-resolution merge, human-confirmed | 🔴 needs L3 entity resolution |

**Connections:** consumes `invoice.overdue`, `order.dispatched`, `ticket.*`; **emits** `customer.at_risk` → Sales & Strategy.

---

## 6. Order Tracking (5 workflows)

| Tool | Description | Status |
|---|---|---|
| `ord.get_status` | Order state, dates, dispatch % (per order or book) | ✅ |
| `ord.get_delay_risk` | Open orders vs promised dates + production WIP → at-risk list | 🟡 |
| `ord.draft_customer_notice` (writes) | Status/delay notice to a customer via notify | 🟡 |
| Fulfillment orchestration / invoice trigger | dispatch event → Accounts | 🔴 needs dispatch write-back; the *event* (order.dispatched) is 🟡 detectable from status change |

**Connections:** emits `order.dispatched` (→ invoice nudge, CRM), `order.delayed` (→ Support/CRM).

---

## 7. Inventory (6 workflows)

| Tool | Description | Status |
|---|---|---|
| `inv.get_summary` | Stock value, SKU count, negative-stock flags, warehouses | ✅ |
| `inv.get_by_category` / `inv.get_top_holdings` | Where the stock money sits | ✅ |
| `inv.get_dead_stock` | No-sale-in-90-days items = trapped capital | ✅ |
| `inv.get_reorder_alerts` | Days-of-cover from sales velocity | ✅ |
| `inv.get_turnover` | Stock turns / days-inventory proxy | ✅ |
| `inv.get_stockout_risk` | Forecast velocity vs on-hand → imminent stockouts | 🟡 |
| `inv.get_abc_ranking` | A/B/C classification by value-velocity | 🟡 |
| `inv.suggest_vendor` | SKU → usual vendor + last price, from purchase history | 🟡 feeds the PO draft |
| `inv.create_draft_po` (writes → **money-gated if large**) | Draft purchase order for a low SKU | 🟡 Wave 4 |

| Workflow | Gather → Act | Status |
|---|---|---|
| Stock-health & dead stock | `inv.get_dead_stock` → `notify.post_inapp`; emits `capital.trapped` → Strategy | ✅ read today, 🟡 event |
| Auto-reorder | `inv.get_reorder_alerts` + `inv.suggest_vendor` → `inv.create_draft_po` | 🟡 Wave 4 |
| Stockout prediction | `inv.get_stockout_risk` → alert Sales & Production; emits `stock.low` | 🟡 |
| Demand forecasting | 🟡 sales-velocity proxy → Production | 🟡 |
| Negative-stock monitor | `inv.get_summary` → `fin.flag_transaction`-style flag | ✅/🟡 |
| ABC analysis | `inv.get_abc_ranking` | 🟡 |

---

## 8. Production & QA (6 workflows)

| Tool | Description | Status |
|---|---|---|
| `prod.get_summary` | FG produced, rejected, reject rate, WIP, completed | ✅ |
| `prod.get_wip` | Per-status work orders, planned vs produced | ✅ |
| `prod.get_routing_coverage` | Which manufactured SKUs have recipes on file | ✅ (BOM) |
| `prod.get_reject_trend` | Reject rate over time / by SKU → QA drift alerts | 🟡 |
| Scheduling / capacity planning | machine & calendar data | 🔴 |
| Predictive maintenance / vision QA | sensors / cameras | 🔴 far future |

**Connections:** WIP feeds `ord.get_delay_risk`; reject trends emit `quality.drift` → R&D/Support.

---

## 9. People Management (9 workflows) — blocked on HR data

No HR system is connected; nothing here before Stage 3+. When it comes: `hr.get_leave_balance`, `hr.check_policy` (vector), `hr.draft_onboarding_checklist` (writes), `hr.compute_payroll` (**money-gated**, human disburses). Recruiting/performance stay human-led with logistics-only tools, per the manual. **Connection:** onboarding emits `access.provision` → Technology.

## 10. Legal (6 workflows) — blocked on vector store + document intake

All six workflows compose from `docs.search`, `legal.extract_clauses` (read), `legal.get_renewals` (read over parsed contracts), `legal.draft_from_template` (writes), `legal.flag_risk` (writes). Prerequisite: Layer 5 vector store + a contracts folder/upload flow. Sign-off always human.

## 11. R&D (6 workflows)

Two buildable early, four blocked: competitor/industry research can use **web research tools** (agent + search API ⚙️); customer-need mining is 🔴 until Support tickets exist (Synapse 2). Tools: `rnd.web_research` ⚙️, `rnd.mine_needs` 🔴, `rnd.draft_brief` (writes) 🟡.

## 12. Strategy & Planning (6 workflows)

| Tool | Description | Status |
|---|---|---|
| `strat.get_kpi_dashboard` | Actual vs target across fields | 🟡 needs a small targets table + UI to set them |
| `strat.get_working_capital` | AR + inventory + AP position ("where is my money stuck") | 🟡 composite of existing reads |
| `strat.run_scenario` | What-if over revenue/cost drivers; presents options, human decides | 🟡 later; agent-composed |
| `strat.draft_review_pack` (writes) | Weekly/board summary assembled from all fields | 🟡 great Wave 4/5 demo |

**Connections:** consumes everything — `capital.trapped`, `credit.flagged`, `customer.at_risk`, forecasts. Emits targets downward.

## 13. Technology (5 workflows)

| Tool | Description | Status |
|---|---|---|
| `tech.get_sync_health` | Pipeline run status, last success per report | ✅ |
| `tech.alert_stale_data` (writes) | Freshness watchdog → notify + dashboard flag; **would have caught the July-2 invoice gap** | 🟡 small, build early |
| IT helpdesk / access / licenses / security | HR + IT integrations | 🔴 |

---

## The connection map (events = synapses)

| Event | Emitted by | Consumed by |
|---|---|---|
| `invoice.overdue` | AR sync detection (Finance) | Sales credit flag · CRM health · Strategy risk — **Synapse 1, Wave 3** |
| `collection.chased` | AR collections | CRM (interaction log) · episodic memory |
| `credit.flagged` | Credit-risk workflow | Sales UI · quote generation |
| `stock.low` / `capital.trapped` | Inventory | Sales (ATP) · Procurement · Strategy — Synapse 5 |
| `order.dispatched` / `order.delayed` | Order Tracking | Finance (invoice nudge) · CRM · Support |
| `quality.drift` | Production QA | R&D · Support — Synapse 2 (partial until tickets) |
| `customer.at_risk` | CRM health score | Sales · Strategy — Synapse 6 (full version needs Support) |
| `data.stale` | Technology watchdog | All dashboards · engineering alert |

---

## The honest tally

| | Count | Meaning |
|---|---|---|
| ✅ ready now | ~31 tools | wrap existing queries/data — Wave 1 is almost free |
| 🟡 new query / small build | ~34 tools | buildable on TranzAct data we already have — Waves 2–5 |
| ⚙️ external hookup | ~4 | email, WhatsApp, web search, write-back |
| 🔴 blocked on new data source | ~30 | need adapters (tickets, GL/GST, HR, contracts, bank, sensors) |
| **Workflows fully buildable through Wave 5** | **~30 of 94** | Finance/Sales/Inventory/CRM/Orders/Strategy/Tech core |

The 🔴 column is the adapter roadmap in disguise: **tickets/email intake** unlocks 13 workflows (Support + Synapses 2/6), **GL/GST** unlocks 8 (deep Finance), **vector store** unlocks 9 (Legal + policy/KB), **HR** unlocks 9. That ordering — driven by which customers pay for what — is a Stage-2/3 decision, not a today decision.

## Build waves (recap, now with exact tool lists)

- **Wave 0** — contract, registry, executor, trajectory evals (no tools)
- **Wave 1** — all 31 ✅ tools → agent-powered Ask
- **Wave 2** — `ar.get_invoice_details`, `ar.get_payment_history`, `ar.draft_collection_email`, `notify.draft_email`/`send_approved`, ledger + inbox
- **Wave 3** — `sales.check_customer_credit`, `sales.flag_customer_credit`, events table + `invoice.overdue` → **Synapse 1 live**
- **Wave 4** — `inv.get_stockout_risk`, `inv.suggest_vendor`, `inv.create_draft_po`, `tech.alert_stale_data`, `fin.get_cashflow_forecast`
- **Wave 5** — `crm.get_customer_360`, `crm.get_health_score` (v1), `strat.get_working_capital`, `strat.draft_review_pack`
