"""
eval/worksheet.py
──────────────────
The paper for the hand-verification session with Shourya.

The harness says whether an answer met its expectations. It cannot say whether
the expectations were right, whether anyone would phrase the question that
way, or whether the case is worth one of the fifty places. Those are a
person's calls, and an hour with Shourya is only enough for them if every case
is already on the page: the question, what the engine actually said, every
figure it showed, the independently computed truth, and which checks passed.

Failing cases come first, then refusals — the two places a wrong judgement
costs most — and then everything else. Each case ends with three boxes and a
notes line, and the outcome is written back into eval/cases.py as a `verified`
record, which is what `--select` and the freeze read.

    python -m vinayak.eval.worksheet [company] [--runner native] [--frozen] --out sheet.md
    python -m vinayak.eval.worksheet --select [--out sheet.md]   # also propose the 50

Rendering and selection are pure functions of a report dict, so they are tested
without a database; only `main` runs the cases.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date

from vinayak.eval import frozen as F
from vinayak.eval.cases import BOTH, CASES

# ── grouping ────────────────────────────────────────────────────────────────


def group_results(results: list[dict]) -> dict[str, list[dict]]:
    """Per-workspace rows gathered under their case id, first-seen order."""
    out: dict[str, list[dict]] = {}
    for r in results:
        out.setdefault(r["id"], []).append(r)
    return out


def case_passed(rows: list[dict]) -> bool | None:
    """Passed on every workspace it ran on; None when it did not run."""
    if not rows:
        return None
    return all(r.get("passed") for r in rows)


def order_for_review(cases: list[dict], results: list[dict]) -> list[dict]:
    """Failing first, then refusals, then the rest — each group in case-set
    order. Cases that did not run are left off: there is nothing to check."""
    grouped = group_results(results)
    ran = [c for c in cases if c["id"] in grouped]

    def rank(c: dict) -> int:
        if not case_passed(grouped[c["id"]]):
            return 0
        return 1 if c.get("refusal") else 2

    return sorted(ran, key=rank)   # sorted is stable, so case order holds within a rank


# ── rendering ───────────────────────────────────────────────────────────────


def _cell(v) -> str:
    """A value safe inside a markdown table cell."""
    if v is None:
        return "—"
    if isinstance(v, float):
        v = f"{v:,.2f}".rstrip("0").rstrip(".") if abs(v) >= 1 or v == 0 else f"{v:.4g}"
    return str(v).replace("|", "\\|").replace("\n", " ").strip() or "—"


def _quote(text: str) -> str:
    lines = (text or "").strip().splitlines() or ["(empty answer)"]
    return "\n".join(f"> {ln}" if ln.strip() else ">" for ln in lines)


def _mark(ok) -> str:
    return "✓" if ok else "✗"


_CHECK_NAMES = {"intent_ok": "intent", "bucket_ok": "confidence", "refusal_ok": "refusal",
                "must_not_say_ok": "forbidden phrases", "no_unsupported": "cited",
                "facts_ok": "facts"}


def _expectations(case: dict) -> str:
    parts = []
    if case.get("refusal"):
        parts.append("**must refuse**")
    if case.get("expect_intent"):
        parts.append(f"intent `{case['expect_intent']}`")
    if case.get("expect_bucket"):
        parts.append("confidence " + " / ".join(sorted(case["expect_bucket"])))
    if case.get("must_not_say"):
        parts.append("must not say " + ", ".join(f"“{s}”" for s in case["must_not_say"]))
    if case.get("expect_values"):
        parts.append("checks " + ", ".join(f"`{w['evidence']}` against `{w['oracle']}`"
                                           for w in case["expect_values"]))
    if case.get("seed_facts"):
        parts.append(f"{len(case['seed_facts'])} seeded fact(s)")
    return " · ".join(parts) or "no expectations beyond a grounded answer"


def _verified_line(case: dict) -> str:
    v = F.verification(case)
    if v is None:
        return "not yet verified"
    keep = "" if v.get("keep", True) else " — **marked not to keep**"
    note = f" — {v['note']}" if v.get("note") else ""
    return f"verified by {v.get('by')} on {v.get('on')}{note}{keep}"


def _render_row(r: dict) -> list[str]:
    status = "passed" if r.get("passed") else "FAILED"
    out = [f"**{r['company']}** — {r.get('confidence')} · intent `{r.get('intent')}` · {status}", ""]
    out.append(_quote(r.get("answer", "")))
    out.append("")

    checks = r.get("checks", {})
    out.append("Checks: " + " · ".join(f"{_CHECK_NAMES.get(k, k)} {_mark(v)}"
                                       for k, v in checks.items()))
    if r.get("must_not_violations"):
        out.append("Forbidden phrases said: " + ", ".join(f"“{s}”" for s in r["must_not_violations"]))
    out.append("")

    evidence = r.get("evidence") or []
    if evidence:
        out += ["| Evidence | Label | Value | Shown as |", "|---|---|---|---|"]
        out += [f"| `{_cell(e.get('id'))}` | {_cell(e.get('label'))} | {_cell(e.get('value'))} "
                f"| {_cell(e.get('display'))} |" for e in evidence]
    else:
        out.append("_No evidence carried._")
    out.append("")

    facts = r.get("fact_checks") or []
    if facts:
        out += ["| Checked figure | Oracle | Truth | Answer had | Right? |", "|---|---|---|---|---|"]
        for f in facts:
            why = f" — {_cell(f['why'])}" if f.get("why") else ""
            out.append(f"| `{_cell(f.get('evidence'))}` | `{_cell(f.get('oracle'))}` "
                       f"| {_cell(f.get('truth'))} | {_cell(f.get('got'))} "
                       f"| {_mark(f.get('ok'))}{why} |")
        out.append("")
    elif not r.get("is_refusal"):
        out += ["_No oracle for this answer — check the figures above by hand._", ""]
    return out


def render_worksheet(report: dict, cases: list[dict] | None = None, *,
                     runner: str | None = None, generated_on: str | None = None,
                     proposal: dict | None = None) -> str:
    """The worksheet as markdown. Pure: a report dict in, text out."""
    cases = CASES if cases is None else cases
    results = report.get("results", [])
    m = report.get("metrics", {})
    grouped = group_results(results)
    ordered = order_for_review(cases, results)
    failing = sum(1 for c in ordered if not case_passed(grouped[c["id"]]))
    refusals = sum(1 for c in ordered if c.get("refusal"))
    verified = sum(1 for c in ordered if F.is_verified(c))

    fa = m.get("factual_accuracy")
    out = [
        "# Eval verification worksheet",
        "",
        f"_Generated {generated_on or date.today().isoformat()} · runner `{runner or 'engine'}` · "
        f"set `{m.get('set', 'candidates')}` · {len(ordered)} cases "
        f"({failing} failing, {refusals} refusals, {verified} already verified)._",
        "",
        f"Run: {m.get('passed', '—')}/{m.get('cases_run', '—')} graded rows passed · "
        f"citation {_pct(m.get('citation_compliance'))} · "
        f"factual {_pct(fa) if fa is not None else 'not graded'} over {m.get('facts_graded', 0)} figures.",
        "",
        "## How to use this",
        "",
        "For each case, read the question and the answer, then tick:",
        "",
        "- **Correct?** — is the answer right about this business, figures included? "
        "Where an oracle computed the truth it is shown; where none did, check the figures by hand.",
        "- **Phrasing real?** — would Sandeep or the group's CA actually ask it this way? "
        "If not, write the real phrasing in the notes.",
        "- **Keep in the 50?** — is this worth one of the fifty frozen places?",
        "",
        "Afterwards, record every case you looked at in `vinayak/eval/cases.py` as "
        "`\"verified\": {\"by\": \"shourya\", \"on\": \"YYYY-MM-DD\", \"note\": \"...\", \"keep\": true}` "
        "(`\"keep\": false` for a rejected case). A case whose question or expectations you change "
        "must be re-run before it is verified. Then `python -m vinayak.eval.worksheet --select` "
        "proposes the fifty and `python -m vinayak.eval.frozen <ids> --write` freezes them.",
        "",
    ]

    for n, case in enumerate(ordered, 1):
        rows = grouped[case["id"]]
        tag = ("FAILING" if not case_passed(rows) else "refusal" if case.get("refusal") else "passing")
        out += [
            "---",
            "",
            f"## {n}. `{case['id']}` — {tag}",
            "",
            f"**Q:** {case['q']}",
            "",
            f"Expected: {_expectations(case)}",
            "",
            f"Status: {_verified_line(case)}",
            "",
        ]
        for r in rows:
            out += _render_row(r)
        out += [
            "- [ ] Correct?",
            "- [ ] Phrasing real?",
            "- [ ] Keep in the 50?",
            "",
            "Notes: ______________________________________________",
            "",
        ]

    if proposal is not None:
        out += ["---", "", render_proposal(proposal, cases)]
    return "\n".join(out).rstrip() + "\n"


def _pct(v) -> str:
    return "—" if v is None else f"{v:.0%}"


# ── proposing the fifty ─────────────────────────────────────────────────────


def _intent_group(case: dict) -> str:
    """Refusals that route to no intent all go through `not_in_data`; grouping
    them under one name keeps "balanced across intents" from treating eleven
    unrouted refusals as eleven different intents."""
    if case.get("expect_intent"):
        return case["expect_intent"]
    return "not_in_data" if case.get("refusal") else "unrouted"


def propose_freeze(cases: list[dict] | None = None, results: list[dict] | None = None,
                   n: int = F.FROZEN_SIZE, companies=BOTH) -> dict:
    """Which `n` cases to freeze, and why. Pure.

    Eligible: runs on every workspace (see frozen.build_manifest) and not
    verified as `keep: False`.

    Priority, in tiers: verified and passing, verified and failing, unverified
    and passing, unverified and failing (or not run). Verified outranks passing
    because a freeze requires every case to be verified — an unverified case
    can be proposed, but only to say "verify this next".

    Failing cases are not excluded. The criterion is ≥ 80%, not 100%, and a
    set built only from what passes today measures nothing but the choice of
    set.

    Refusals are included in proportion to their share of the eligible
    cases, and within each half the pick is balanced across intents: at every
    step, from the best tier still available, take the case whose intent has
    been picked least so far (ties by case-set order). Fifty ageing questions
    would pass and prove nothing.
    """
    cases = CASES if cases is None else cases
    grouped = group_results(results or [])

    eligible = [c for c in cases if F.applies_everywhere(c, companies)
                and (F.verification(c) or {}).get("keep", True) is not False]

    def tier(c: dict) -> int:
        passed = bool(case_passed(grouped.get(c["id"], [])))
        return (0 if passed else 1) if F.is_verified(c) else (2 if passed else 3)

    refusal_pool = [c for c in eligible if c.get("refusal")]
    answer_pool = [c for c in eligible if not c.get("refusal")]
    refusal_quota = round(n * len(refusal_pool) / len(eligible)) if eligible else 0

    def pick(pool: list[dict], k: int, taken: Counter) -> list[dict]:
        chosen: list[dict] = []
        left = list(pool)
        while left and len(chosen) < k:
            best = min(tier(c) for c in left)
            at_tier = [c for c in left if tier(c) == best]
            c = min(at_tier, key=lambda c: taken[_intent_group(c)])  # min is first-wins on ties
            chosen.append(c)
            taken[_intent_group(c)] += 1
            left.remove(c)
        return chosen

    taken: Counter = Counter()
    chosen = pick(refusal_pool, min(refusal_quota, len(refusal_pool)), taken)
    chosen += pick(answer_pool, n - len(chosen), taken)
    if len(chosen) < n:   # answerable ran short — top up with the remaining refusals
        chosen += pick([c for c in refusal_pool if c not in chosen], n - len(chosen), taken)

    ids = {c["id"] for c in chosen}
    ordered = [c for c in cases if c["id"] in ids]
    return {
        "ids": [c["id"] for c in ordered],
        "short_by": max(0, n - len(ordered)),
        "refusals": sum(1 for c in ordered if c.get("refusal")),
        "verified": sum(1 for c in ordered if F.is_verified(c)),
        "unverified": [c["id"] for c in ordered if not F.is_verified(c)],
        "failing": [c["id"] for c in ordered if not case_passed(grouped.get(c["id"], []))],
        "by_intent": dict(Counter(_intent_group(c) for c in ordered)),
        "left_out": [c["id"] for c in eligible if c["id"] not in ids],
        "ineligible": [c["id"] for c in cases if c not in eligible],
    }


def render_proposal(p: dict, cases: list[dict] | None = None) -> str:
    cases = CASES if cases is None else cases
    ready = not p["unverified"] and not p["short_by"]
    out = [
        f"## Proposed freeze — {len(p['ids'])} cases",
        "",
        f"{p['refusals']} refusals · {p['verified']} verified · {len(p['failing'])} failing or not run"
        + (f" · **short by {p['short_by']}**" if p["short_by"] else ""),
        "",
        "By intent: " + ", ".join(f"`{k}` {v}" for k, v in sorted(p["by_intent"].items())),
        "",
    ]
    if p["unverified"]:
        out += [f"Not yet verified ({len(p['unverified'])}) — verify these before freezing: "
                + ", ".join(f"`{i}`" for i in p["unverified"]), ""]
    if p["left_out"]:
        out += ["Left out: " + ", ".join(f"`{i}`" for i in p["left_out"]), ""]
    if p["ineligible"]:
        out += ["Not eligible (single-workspace, or verified as not worth keeping): "
                + ", ".join(f"`{i}`" for i in p["ineligible"]), ""]
    out += [
        "Freeze with:" if ready else "When every proposed case is verified, freeze with:",
        "",
        "```",
        "python -m vinayak.eval.frozen " + " ".join(p["ids"]) + " --write",
        "```",
    ]
    return "\n".join(out) + "\n"


# ── CLI ─────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m vinayak.eval.worksheet",
                                description="Write the hand-verification worksheet.")
    p.add_argument("company", nargs="?", default=None, help="one workspace (default: all)")
    p.add_argument("--runner", default=None, help="grade an agent runner (native | adk)")
    p.add_argument("--frozen", action="store_true", help="only the frozen 50")
    p.add_argument("--select", action="store_true", help="propose the 50 to freeze")
    p.add_argument("--out", default=None, help="write the worksheet here (default: stdout)")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    import os

    import psycopg2
    from dotenv import load_dotenv

    from vinayak.eval.harness import FreezeError, cases_for, run_eval

    if args.frozen:
        try:
            cases_for(True)
        except FreezeError as e:
            print(f"--frozen: {e}", file=sys.stderr)
            return 2

    load_dotenv()
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        report = run_eval(conn, args.company, runner_name=args.runner, frozen=args.frozen)
    finally:
        conn.close()

    proposal = propose_freeze(CASES, report["results"]) if args.select else None
    text = render_worksheet(report, CASES, runner=args.runner, proposal=proposal)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"Wrote {args.out}.")
        if proposal is not None:
            print(render_proposal(proposal, CASES))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
