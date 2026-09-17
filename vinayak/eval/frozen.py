"""
eval/frozen.py
───────────────
The frozen 50 — the question set Milestone 1's criterion 3 is judged on.

The criterion says "50-question eval", and a set that can still be edited is
not a set anyone can be held to: a case that got hard could be quietly
softened the week before the review and the score would still read "50". So
the freeze is two things, both checked in code:

  1. an explicit list of exactly 50 case ids, and
  2. a content hash of each frozen case's question and expectations.

Edit a frozen case's wording, its expected intent, a forbidden phrase or an
oracle, and `check_frozen()` names it. Changing a frozen case after the freeze
is allowed — it is sometimes right — but it has to be a visible act: regenerate
the manifest, which shows up in the diff and in `frozen_hash` on every run
recorded after it.

What is NOT hashed is the `verified` metadata. Recording who checked a case
and when does not change what the case asks, and must not break the freeze.

The manifest below is EMPTY until the hand-verification with Shourya is done
(target 15 Jan 2027). Generate it from the chosen ids, never by hand:

    python -m vinayak.eval.frozen <id> <id> ... [--on 2027-01-15]          # print
    python -m vinayak.eval.frozen <id> <id> ... [--on 2027-01-15] --write  # rewrite this file

`python -m vinayak.eval.worksheet --select` proposes the ids.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

from vinayak.eval.cases import BOTH, CASES

FROZEN_SIZE = 50

# The criterion's own thresholds, in one place so the rule and the status line
# cannot disagree about what "met" means.
FACTUAL_ACCURACY_MIN = 0.80
CITATION_COMPLIANCE_REQUIRED = 1.0

# ── manifest (generated — see the module docstring) ─────────────────────────
# BEGIN MANIFEST
FROZEN_ON: str | None = None
FROZEN: dict[str, str] = {}
# END MANIFEST


class FreezeError(ValueError):
    """The frozen set cannot be used as asked — empty, drifted, or malformed."""


# The fields that define what a case ASKS and what counts as right. Anything
# else on a case (today only `verified`) is commentary about the case.
_HASHED_FIELDS = ("id", "q", "companies", "expect_intent", "expect_bucket", "refusal",
                  "must_not_say", "seed_facts", "expect_values")


def _canonical(value):
    """Sets become sorted lists so the hash does not depend on set order."""
    if isinstance(value, (set, frozenset)):
        return sorted(_canonical(v) for v in value)
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    return value


def case_hash(case: dict) -> str:
    """Hash of the question and its expectations. Absent fields hash as their
    defaults, so adding `"refusal": False` to a case is not an edit."""
    body = {
        "id": case["id"],
        "q": case["q"],
        "companies": sorted(case.get("companies", BOTH)),
        "expect_intent": case.get("expect_intent"),
        "expect_bucket": _canonical(case.get("expect_bucket")),
        "refusal": bool(case.get("refusal")),
        "must_not_say": list(case.get("must_not_say", [])),
        "seed_facts": _canonical(case.get("seed_facts", [])),
        "expect_values": _canonical(case.get("expect_values", [])),
    }
    assert set(body) == set(_HASHED_FIELDS)
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def manifest_hash(manifest: dict[str, str]) -> str | None:
    """One fingerprint for the whole freeze, recorded with every frozen run so a
    score can be tied to the exact set it was earned on. Order-independent."""
    if not manifest:
        return None
    raw = "\n".join(f"{k}:{manifest[k]}" for k in sorted(manifest))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# ── verification metadata ───────────────────────────────────────────────────
def verification(case: dict) -> dict | None:
    """The case's `verified` record, or None. A record looks like
    {"by": "shourya", "on": "2027-01-10", "note": "...", "keep": True};
    `keep` defaults to True, and False means verified-and-rejected."""
    return case.get("verified") or None


def is_verified(case: dict) -> bool:
    return verification(case) is not None


def verification_problems(case: dict) -> list[str]:
    """A malformed record is worse than none — it reads as a sign-off."""
    v = case.get("verified")
    if v is None:
        return []
    out = []
    if not isinstance(v, dict):
        return [f"{case['id']}: verified must be a dict or None"]
    if not str(v.get("by") or "").strip():
        out.append(f"{case['id']}: verified.by is empty")
    try:
        date.fromisoformat(str(v.get("on")))
    except ValueError:
        out.append(f"{case['id']}: verified.on is not an ISO date ({v.get('on')!r})")
    if "keep" in v and not isinstance(v["keep"], bool):
        out.append(f"{case['id']}: verified.keep must be true or false")
    return out


def applies_everywhere(case: dict, companies=BOTH) -> bool:
    return set(companies) <= set(case.get("companies", BOTH))


# ── building and checking the freeze ────────────────────────────────────────
def build_manifest(ids: list[str], cases: list[dict] = CASES) -> dict[str, str]:
    """The manifest for these ids, refusing anything that would make the freeze
    mean less than it says.

    Every frozen case must apply to every workspace. The criterion is "50
    questions", and a case that only runs on kbrushes would leave a protegere
    run grading 49 — so "50" would be true of one workspace and not the other.
    Requiring coverage keeps the count the same in every reading.

    Every frozen case must be verified and not marked `keep: False`. A freeze
    is Shourya's sign-off on the set; an unverified case in it is not signed.
    """
    by_id = {c["id"]: c for c in cases}
    problems = []
    if len(ids) != FROZEN_SIZE:
        problems.append(f"a freeze holds exactly {FROZEN_SIZE} cases, got {len(ids)}")
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        problems.append(f"duplicate ids: {', '.join(dupes)}")
    for i in ids:
        c = by_id.get(i)
        if c is None:
            problems.append(f"{i}: no such case")
            continue
        if not applies_everywhere(c):
            problems.append(f"{i}: does not run on every workspace")
        v = verification(c)
        if v is None:
            problems.append(f"{i}: not verified")
        elif v.get("keep") is False:
            problems.append(f"{i}: verified as not worth keeping")
        problems.extend(verification_problems(c))
    if problems:
        raise FreezeError("cannot freeze:\n  " + "\n  ".join(problems))
    return {i: case_hash(by_id[i]) for i in ids}


def check_frozen(manifest: dict[str, str] | None = None,
                 cases: list[dict] | None = None) -> list[str]:
    """Everything wrong with the freeze as it stands; empty means intact.

    An empty manifest has nothing wrong with it — it means the freeze has not
    happened — so it reports nothing. Callers that NEED a freeze (the harness
    under --frozen) check for emptiness themselves and say so plainly.
    """
    manifest = FROZEN if manifest is None else manifest
    cases = CASES if cases is None else cases
    if not manifest:
        return []
    by_id = {c["id"]: c for c in cases}
    problems = []
    if len(manifest) != FROZEN_SIZE:
        problems.append(f"the manifest holds {len(manifest)} cases, not {FROZEN_SIZE}")
    for cid, want in manifest.items():
        c = by_id.get(cid)
        if c is None:
            problems.append(f"{cid}: frozen but no longer in the case set")
            continue
        got = case_hash(c)
        if got != want:
            problems.append(f"{cid}: edited since the freeze (hash {want} → {got})")
        if not applies_everywhere(c):
            problems.append(f"{cid}: frozen but no longer runs on every workspace")
        # Not hashed, but not optional either: removing a sign-off from a
        # frozen case un-signs the freeze.
        if not is_verified(c):
            problems.append(f"{cid}: frozen but its verification record is gone")
    return problems


def frozen_cases(manifest: dict[str, str] | None = None,
                 cases: list[dict] | None = None) -> list[dict]:
    """The frozen cases, in case-set order — or FreezeError explaining why the
    frozen set cannot be run. A run over a drifted freeze is not a run over the
    frozen set, so it is refused rather than recorded with a caveat."""
    manifest = FROZEN if manifest is None else manifest
    cases = CASES if cases is None else cases
    if not manifest:
        raise FreezeError(
            "the eval set has not been frozen yet — vinayak/eval/frozen.py has an empty "
            "manifest. Verify the candidates with Shourya (python -m vinayak.eval.worksheet), "
            "then generate it with python -m vinayak.eval.frozen <50 ids> --write.")
    problems = check_frozen(manifest, cases)
    if problems:
        raise FreezeError("the frozen set has drifted:\n  " + "\n  ".join(problems))
    return [c for c in cases if c["id"] in manifest]


def set_metadata(run_cases: list[dict], frozen: bool,
                 manifest: dict[str, str] | None = None) -> dict:
    """What a run was graded on, for its metrics row: which set, the freeze's
    fingerprint, and how many of the cases run a person has checked."""
    manifest = FROZEN if manifest is None else manifest
    return {
        "set": "frozen" if frozen else "candidates",
        "frozen_hash": manifest_hash(manifest) if frozen else None,
        "cases_verified": sum(1 for c in run_cases if is_verified(c)),
    }


# ── the criterion ───────────────────────────────────────────────────────────
def criterion_met(metrics: dict, frozen_hash: str | None = None) -> bool:
    """Milestone 1, criterion 3, as a rule: factual accuracy ≥ 80% AND citation
    compliance exactly 100% AND graded on the frozen set AND that set is 50
    questions.

    "50" counts QUESTIONS, not graded rows. A case runs once per workspace it
    applies to, so a run over both workspaces grades 100 rows for 50 questions;
    `questions` (distinct case ids) is the number that must be 50, and
    `cases_run` is only used for metrics recorded before `questions` existed.
    Because every frozen case must run on every workspace (see
    build_manifest), a frozen run has 50 questions whether it covered one
    workspace or all of them — so this rule reads the same on either.

    It does not decide WHICH run to judge. A run over all workspaces pools
    their figures, which can hide one workspace below 80%; the milestone
    review should look at a run per workspace, and the status line reads the
    latest frozen run covering the workspace it describes.

    Pass `frozen_hash` (the current manifest's) to also require the run was on
    THIS freeze — a score earned on a set since edited does not count.

    An ungraded factual accuracy (None) is not met: nothing checked is not
    80% right.
    """
    if metrics.get("set") != "frozen":
        return False
    if frozen_hash is not None and metrics.get("frozen_hash") != frozen_hash:
        return False
    questions = metrics.get("questions", metrics.get("cases_run"))
    if questions != FROZEN_SIZE:
        return False
    fa = metrics.get("factual_accuracy")
    if fa is None or fa < FACTUAL_ACCURACY_MIN:
        return False
    return metrics.get("citation_compliance") == CITATION_COMPLIANCE_REQUIRED


# ── generating the manifest ─────────────────────────────────────────────────
_BLOCK = re.compile(r"# BEGIN MANIFEST\n.*?# END MANIFEST\n", re.S)


def manifest_source(manifest: dict[str, str], on: str) -> str:
    """The manifest block as Python source, one id per line so a later diff
    shows exactly which case changed."""
    lines = ["# BEGIN MANIFEST", f"FROZEN_ON: str | None = {on!r}",
             "FROZEN: dict[str, str] = {"]
    lines += [f"    {cid!r}: {h!r}," for cid, h in manifest.items()]
    lines += ["}", "# END MANIFEST", ""]
    return "\n".join(lines)


def replace_manifest(module_source: str, block: str) -> str:
    """This module's source with its manifest block swapped for `block`."""
    if len(_BLOCK.findall(module_source)) != 1:
        raise FreezeError("could not find exactly one manifest block to replace")
    return _BLOCK.sub(lambda _m: block, module_source)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="python -m vinayak.eval.frozen",
                                description="Freeze the eval set at exactly 50 verified cases.")
    p.add_argument("ids", nargs="*", help="the 50 case ids to freeze")
    p.add_argument("--on", default=date.today().isoformat(), help="freeze date (ISO)")
    p.add_argument("--write", action="store_true", help="rewrite this module's manifest")
    p.add_argument("--check", action="store_true", help="check the current freeze and exit")
    args = p.parse_args(argv)

    if args.check or not args.ids:
        if not FROZEN:
            print("Not frozen yet (empty manifest).")
            return 0
        problems = check_frozen()
        for line in problems:
            print(f"  ✗ {line}")
        print(f"Frozen on {FROZEN_ON}, hash {manifest_hash(FROZEN)}: "
              f"{'INTACT' if not problems else 'DRIFTED'}.")
        return 1 if problems else 0

    try:
        manifest = build_manifest(args.ids)
    except FreezeError as e:
        print(str(e), file=sys.stderr)
        return 2
    block = manifest_source(manifest, args.on)
    if args.write:
        path = Path(__file__)
        path.write_text(replace_manifest(path.read_text(encoding="utf-8"), block),
                        encoding="utf-8")
        print(f"Wrote {len(manifest)} frozen cases to {path} "
              f"(hash {manifest_hash(manifest)}).")
    else:
        print(block)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
