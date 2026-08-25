"""Check the model's prose against the figures this site already publishes.

The gap this closes
-------------------
`/query` validates the SHAPE of what the agent does — SQLGlot rejects every
unreviewed AST node, the role can read two views, the transaction is read-only
and timeout-bounded. None of that checks whether the NUMBER is right.

On 2026-08-23 a probe of twenty live questions found the agent answering
`operating_spend` with `total_spend` four times out of four. Tioga ISD 2014 came
back as $5,603,166 against a true $3,205,610 — a 75% overstatement — and two of
the four answers volunteered "that is the district's all-funds total
disbursements" without noticing that was the wrong figure. The prompt has since
been fixed. The point is that nothing in the running system noticed: it took a
hand-built probe, run once, by a person who already suspected something.

So this is the missing node. It reads the numbers out of the model's sentence
and compares them with the same artefacts the rest of the site serves.

What it will and will not say
-----------------------------
**It never edits the answer.** A verifier that rewrites prose is a second
author, and the second author is unreviewable. This annotates.

**Silence is not agreement.** A figure this layer holds no opinion about
returns `unchecked`, never `agrees`. The distinction matters: `agrees` is a
claim that something was compared, and most sentences contain a number nobody
can check.

**A disagreement is reported, not resolved.** The finance view and the
economics artefact legitimately differ — the view is all-funds including
construction, the artefact is operating plus debt — and both are right about
different questions. Where the basis differs the verdict says so rather than
picking a winner, because picking one would make the site quietly inconsistent
with itself.

**Tolerance is real, not generous.** The DB view does integer division, so a
per-student figure can differ by a dollar from an artefact computed in floating
point. One dollar is rounding. Ten percent is a different column.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"

AGREES = "agrees"
DISAGREES = "disagrees"
DIFFERENT_BASIS = "different_basis"
UNCHECKED = "unchecked"

# A dollar of slack absorbs the view's integer division against the artefact's
# float. Anything beyond 1% is not rounding.
ABS_TOLERANCE = 1.0
REL_TOLERANCE = 0.01

# What we can check, and where the truth lives. Each entry names the phrases a
# reader would actually type or a model would actually write — matching on the
# artefact's field name would only catch answers that already used our
# vocabulary, which is not the failure mode.
_CHECKS: list[dict[str, Any]] = [
    {
        "key": "operating_per_student",
        "any_of": ("operating", "operations", "running the"),
        "per_student": True,
        "path": ("economics", "allocation", "operating_per_student"),
        "basis": "all-funds operating expenditure, excluding construction "
                 "and debt service",
    },
    {
        "key": "instruction_per_student",
        "any_of": ("instruction", "instructional", "classroom", "teaching"),
        "per_student": True,
        "path": ("economics", "allocation", "instruction_per_student"),
        "basis": "PEIMS function 11,95",
    },
    {
        "key": "total_per_student",
        "any_of": ("total", "all funds", "all-funds", "altogether", "overall"),
        "per_student": True,
        "path": ("economics", "allocation", "total_per_student"),
        "basis": "operating plus debt service, WITHOUT bond-funded "
                 "construction — the finance view's all-funds figure is larger "
                 "and both are correct about different questions",
        "expect_basis_conflict": True,
    },
    {
        "key": "debt_per_student",
        "any_of": ("debt",),
        "per_student": True,
        "path": ("economics", "allocation", "debt_per_student"),
        "basis": "annual debt service, not the outstanding balance",
    },
    {
        "key": "students",
        "any_of": ("enrollment", "enrolment", "enrolled", "students in",
                   "serves"),
        "per_student": False,
        "path": ("economics", "students"),
        "basis": "fall survey enrollment",
    },
    {
        "key": "tax_rate",
        "any_of": ("tax rate",),
        "per_student": False,
        "path": ("economics", "tax", "total_rate"),
        "basis": "adopted rate per $100 of value",
    },
]

_ARTIFACTS = {"economics": "economics_data.json"}
_cache: dict[str, Any] = {}


def _artifact(name: str) -> dict[str, Any] | None:
    if name not in _cache:
        path = STATIC / _ARTIFACTS[name]
        if not path.exists():
            _cache[name] = None
        else:
            _cache[name] = json.loads(path.read_text())
    return _cache[name]


def _published(path: tuple[str, ...], district_number: str) -> float | None:
    blob = _artifact(path[0])
    if not blob:
        return None
    node: Any = (blob.get("districts") or {}).get(district_number)
    for part in path[1:]:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return float(node) if isinstance(node, (int, float)) else None


# A number with optional $ , and decimals, plus the million/billion suffixes a
# model reaches for on large totals.
_NUM = re.compile(
    r"\$?\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s?(million|billion|m\b|bn\b)?",
    re.I)


def numbers_with_context(text: str, window: int = 80) -> list[tuple[float, str]]:
    """Every number in the prose, paired with the words around it.

    Anchored on the NUMBER rather than on a phrase list. The first version
    matched cue strings like "operating spend per student" and missed
    "$14,210 per student on operations" — which is how a person actually
    writes it. A checker that only recognises our own vocabulary catches
    answers that were already using it, which is not the failure mode.
    """
    out: list[tuple[float, str]] = []
    for m in _NUM.finditer(text):
        raw, suffix = m.group(1), (m.group(2) or "").lower()
        try:
            v = float(raw.replace(",", ""))
        except ValueError:
            continue
        if suffix.startswith("m"):
            v *= 1_000_000
        elif suffix.startswith("b"):
            v *= 1_000_000_000
        ctx = text[max(0, m.start() - window): m.end() + window].lower()
        out.append((v, ctx))
    return out


def _close(a: float, b: float) -> bool:
    if abs(a - b) <= ABS_TOLERANCE:
        return True
    scale = max(abs(a), abs(b))
    return scale > 0 and abs(a - b) / scale <= REL_TOLERANCE


def check(answer_text: str, district_number: str | None) -> dict[str, Any]:
    """Compare the prose against what this site publishes for that district.

    Returns a verdict and the checks behind it. Never raises: a verifier that
    can fail the request it was added to protect is a new outage, not a
    safeguard.
    """
    if not district_number or not answer_text:
        return {"verdict": UNCHECKED, "checks": [],
                "note": "No district in context, so nothing to compare against."}
    try:
        seen = numbers_with_context(answer_text)
        results = []
        for spec in _CHECKS:
            published = _published(spec["path"], district_number)
            if published is None:
                continue
            found = [
                v for v, ctx in seen
                if any(q in ctx for q in spec["any_of"])
                # A per-student metric must actually say per student. Without
                # this a total in the same sentence is compared against a
                # per-pupil figure and every answer "disagrees".
                and (not spec["per_student"]
                     or "per student" in ctx or "per-student" in ctx
                     or "per pupil" in ctx or "per-pupil" in ctx)
            ]
            if not found:
                continue
            agree = any(_close(v, published) for v in found)
            if agree:
                verdict = AGREES
            elif spec.get("expect_basis_conflict"):
                verdict = DIFFERENT_BASIS
            else:
                verdict = DISAGREES
            results.append({
                "metric": spec["key"],
                "published": published,
                "in_answer": sorted(set(found))[:4],
                "verdict": verdict,
                "basis": spec["basis"],
            })

        if not results:
            return {"verdict": UNCHECKED, "checks": [],
                    "note": "This answer contains no figure this site "
                            "independently publishes for that district. "
                            "Unchecked is not the same as correct."}
        if any(r["verdict"] == DISAGREES for r in results):
            verdict = DISAGREES
        elif any(r["verdict"] == DIFFERENT_BASIS for r in results):
            verdict = DIFFERENT_BASIS
        else:
            verdict = AGREES
        return {"verdict": verdict, "checks": results,
                "note": _NOTES[verdict]}
    except Exception as exc:  # noqa: BLE001 — must never fail the answer
        return {"verdict": UNCHECKED, "checks": [],
                "note": f"Could not check ({type(exc).__name__}); "
                        f"the answer is unverified, not wrong."}


_NOTES = {
    AGREES: "Every figure this site can check matches what it publishes.",
    DISAGREES: "A figure in this answer does not match what this site "
               "publishes for that district. Trust the district page.",
    DIFFERENT_BASIS: "A figure differs because it is measured on a different "
                     "basis — the query engine reads all funds including "
                     "construction, the district page separates operating from "
                     "debt. Both are right about different questions.",
    UNCHECKED: "Nothing here could be checked against published data.",
}
