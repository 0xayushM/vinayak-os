# Incidents

The record behind "no critical production incidents in the prior 60 days".
Incidents are logged at the bottom of this file, and in the `incidents` table, so the count
is computed, not asserted; this file holds the definitions and the write-ups.

## What counts as critical

An incident is **critical** when, in production, any of these was true:

1. An owner or accountant could not use the product for their daily work for
   more than 2 working hours (login, Pulse, Inbox or Ask unavailable).
2. A number shown on a card, in an answer, or in a sent message was **wrong**
   (not stale — wrong): it did not match the source system for the same date.
3. A message was sent to a customer without approval, twice, or to the wrong
   contact.
4. Data from one workspace was visible in another.
5. Data was lost (a table blanked, history not recoverable from raw).

**Major**: degraded but usable — a source stale beyond 25 h without an alert,
a watcher silently not running, a panel erroring. **Minor**: cosmetic or
self-healing within an hour.

Stale data that is *marked* stale is not an incident. A refusal ("I can't
answer that reliably") is not an incident. A model outage that fell back to
the deterministic engine is not an incident.

## How to log one

Add an entry to the log at the bottom of this file, and insert the row in `incidents`. Severity, one-line title, detail. Mark
resolved when it is. For anything critical, add a write-up below within a
week: what happened, impact, root cause, what changed so it cannot recur.

## Log

One row per incident, newest last. The `incidents` table carries the same
entries and is what `python -m vinayak.scripts.milestone_status` counts for the
"no critical incident in the last 60 days" criterion — so write both, or the
number and the story disagree.

| Started | Severity | Title | Resolved | Notes |
|---|---|---|---|---|
| — | — | _None yet._ | — | |

## Write-ups

_None yet._
