"""
vinayak.domain
──────────────
The zero-dependency core of the system: the value types every layer speaks
(Evidence, Claim, Answer) and pure formatting helpers (money, dates). Nothing
here imports from db, tools, reasoning, or the model — it sits at the bottom of
the dependency DAG so everything else can depend on it without cycles.
"""
