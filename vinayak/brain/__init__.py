"""
vinayak.brain
──────────────
The part of the system that runs when nobody is looking.

Layer 10 of the architecture, first real use. Four pieces, in the order a
fact travels through them:

    detectors.py  deterministic SQL that turns the data into typed EVENTS
                  ('invoice.overdue_rung', 'data.stale', 'anomaly.detected').
                  No model involved: a detector is a query and a threshold.

    bus.py        the events table, with a dedupe key. A detector is free to
                  re-derive the same fact every hour; the bus makes sure the
                  fact is recorded — and therefore acted on — exactly once.

    consumer.py   reads pending events and proposes ACTIONS into the ledger.
                  Proposals only: the executor's rule that non-read tools are
                  never executed by a model holds here too.

    strategy.py   the weekly watcher. Reads the Pulse and files EXPERIMENTS
                  with a metric and a window, for a person to accept.

    runner.py     runs one watcher inside a brain_runs episode, so every pass
                  leaves a record of what it looked at and what it did.

The rule that makes this safe is the one from the reference document: the
brain proposes, deterministic code disposes, and a person approves anything
that leaves the building.
"""
