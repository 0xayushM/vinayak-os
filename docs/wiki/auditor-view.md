# What a CA needs, and what we can give them

Written by working through a statutory review of a ₹30–60 Cr manufacturing
group as its Chartered Accountant would, then checking each question against
the data actually synced. The answer divides cleanly in two, and the division
is the useful part.

## The first ten minutes of a review

An auditor does not ask what is **big**. They ask what is **old**, what is
**unusual**, and what they will have to **explain**. That is a different set
of questions from the owner's, and the product now answers them:

| The question | Intent | What it reads |
|---|---|---|
| How much is more than 90 / 180 days past due? | `ar_ageing_over` | Aged from due date, recomputed today |
| Which balances may need a provision? | `ar_ageing_over` | Shows what is old; never states a provision |
| What did we bill to group companies? | `related_party` | Customer names matched to connected workspaces |
| How much working capital is tied up? | `working_capital` | Stock + receivables; says payables are missing |
| What data problems are there before the audit? | `data_quality` | Field coverage, issues, negative stock |
| This month against last month | `month_compare` | Monthly billing series |
| What is in the quotation pipeline? | `quotes` | Open value and conversion |
| Goods received, rejected, awaiting inspection | `grn_status` | GRN / QIR |
| Reject rate and work in progress | `production` | Process details |
| Which customers are a credit risk? | `credit_risk` | Deterministic flags, not a decision |

Two findings from the first run against live data, both the sort a review
would have surfaced weeks later:

- **Protegere has ₹50.4L — 21.8% of its receivable book — more than 180 days
  past due**, across three customers, the oldest at 294 days.
- **13.9% of Protegere's revenue is billed to Vinayak Technoplast**, a group
  company, and ₹14.7L of that balance is itself over 180 days overdue. That is
  a related-party disclosure *and* an intercompany balance to reconcile.

### Two definitions that had to be pinned down

**Ageing is computed from the due date, now — never from the `days_overdue`
the source stored.** On live data the stored figure is already four days
behind, because TranzAct computed it when the report was generated. Four days
is enough to move an invoice across a bucket boundary, and a provisioning
number that moves depending on when the report ran is a number that starts an
argument instead of ending one.

**Related parties are matched by name**, against the names of the other
connected workspaces. A group company trading under a name we do not hold is
missed; a customer whose name happens to contain a group name is a false
positive. The matched names are returned with the figure so a person can
check them, and the answer is labelled PROBABLE rather than CERTAIN. That is
the honest way to ship a number like this, and it stops being necessary the
day the group's legal entities are held as data rather than inferred.

## What we cannot give them, and why

Roughly a third of a CA's questions cannot be answered from operational ERP
documents at all. This is the half that matters most, because it is where a
confident wrong answer costs everything: an auditor who catches the brain
inventing a margin will not open it again, and will be right not to.

| Asked for | Missing |
|---|---|
| GST liability, GSTR-2A reconciliation, ITC | The returns and the purchase register |
| TDS / TCS deducted and deposited | The tax ledgers |
| Bank balance, bank reconciliation | A bank feed, or the cash and bank ledgers |
| P&L, balance sheet, trial balance | The general ledger — this reads documents, not accounts |
| Gross margin, profitability by product | Cost per unit; nothing in the feed carries it |
| Creditors ageing, DPO | Vendor bills with **due dates and payment dates** — purchase invoices sync without either |
| Depreciation, fixed assets | The asset register |
| Cash flow statement | Ledgers and bank. The 30-day cash view is a forecast from receivables, not a statement |
| Payroll | The payroll system |

These are not silences. `not_in_data` is a real intent with a real handler: it
names what is missing and what would supply it, so the refusal doubles as a
roadmap. Before it existed, *"reconcile GSTR-2A against our purchase register"*
matched the keyword `purchase` and returned a confident spend summary, and
*"give me the creditors ageing"* matched `ageing` and returned the **debtors**
ageing. Both read as answers.

**Tally closes most of this list in one integration** — ledgers, bills
outstanding with dates, and payment vouchers would unlock creditors ageing,
DPO, the true working-capital cycle, real days-to-pay, and the bank position.
That is the strongest argument for the Tally bridge that exists, and it comes
from an auditor's question list rather than from an architecture diagram.

**Cost per SKU is the other unlock**, and it is a CSV, not an integration.
Margin is the single most-asked question the product refuses.
