"""
scripts/milestone_status.py
────────────────────────────
Prints the current milestone numbers as a markdown block, for pasting into
docs/reference/MILESTONES.md under "Where the numbers stand".

    python -m vinayak.scripts.milestone_status              # every workspace
    python -m vinayak.scripts.milestone_status kbrushes     # one
    python -m vinayak.scripts.milestone_status --json
    python -m vinayak.scripts.milestone_status --demo       # + month-3 demo readiness

The tracker is a document on purpose (see vinayak/milestones.py). This is the
half of it that has to be counted rather than written.
"""
from __future__ import annotations

import json
import sys

import psycopg2

from vinayak import demo_readiness, milestones
from vinayak.config import DATABASE_URL


def _companies(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT company_id FROM tool_connections "
                    "WHERE is_active = TRUE ORDER BY 1")
        return [r[0] for r in cur.fetchall()]


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    demo = "--demo" in argv
    wanted = [a for a in argv if not a.startswith("-")]

    conn = psycopg2.connect(DATABASE_URL)
    try:
        ids = wanted or _companies(conn)
        if not ids:
            print("No connected workspaces.", file=sys.stderr)
            return 1
        out = []
        for company_id in ids:
            s = milestones.status(conn, company_id)
            if demo:
                s["demo_readiness"] = demo_readiness.assess(demo_readiness.gather(
                    conn, company_id, s["tracked_user"], s["evals"]))
            out.append(s)
            if not as_json:
                print(f"\n### {company_id}\n")
                print(milestones.as_markdown(s))
                if demo:
                    print()
                    print(demo_readiness.as_markdown(company_id, s["demo_readiness"]))
        if as_json:
            print(json.dumps(out, indent=2, default=str))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
