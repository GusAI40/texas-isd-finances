"""Why is this number this number?

The evidence contract shared by the dashboard and the question box. One object
per published figure, carrying everything a reader needs to check it without
trusting us: numerator, denominator, what the denominator MEANS, the formula,
the fiscal year, the publisher, the vintage of the file it came from, and the
verdict of the publication gate.

The rule this exists to enforce
-------------------------------
The language model has EXPLANATORY authority, never NUMERICAL authority. It
receives these objects; it does not produce them and cannot alter them. A
figure reaches a reader only if deterministic code computed it and the gate
passed it.

Why a gate rather than a validation flag
----------------------------------------
"Deterministic" is not the same as "true". Every reader-visible error this
project has shipped came from deterministic code, not from a model: the bond
layer ran two years stale while naming districts as never having passed a bond;
five districts were drawn on another district's land; a test compared an
artefact against a column generated from that same artefact and stayed green.
Reproducible and wrong is still wrong.

So a number is publishable only when four separate questions pass, and each
one has a real failure on record behind it:

  CORRECTNESS   does an independent recomputation agree?
                (the bond→forensic drift that verify_artifacts caught)
  FRESHNESS     is the source current enough to support this claim?
                (the bond layer, two years stale, fully "validated")
  AIM           did we check the artefact we actually publish, or a
                neighbour? (three freshness checks watched the wrong file;
                verify_sources passed the wrong publisher for weeks)
  COMPUTABILITY do we have enough compatible data to compute this at all?
                (the debt ratio is refused where a series has a gap)

Failing COMPUTABILITY produces REFUSED — a published statement that we decline
to compute this, not a guess and not a blank.

The independence rule, stated once
----------------------------------
`recomputed_from` must name a source that is NOT the artefact being validated.
Comparing an artefact to something generated from it proves only that the
generator ran. That mistake shipped here and stayed green through a real bug,
so `gate()` refuses to return VERIFIED on a self-referential check.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Gate verdicts. Order matters: the worst wins.
VERIFIED = "VERIFIED"        # every question passed, including an independent one
UNVERIFIED = "UNVERIFIED"    # nothing failed, but nothing independent confirmed it
STALE = "STALE"              # correct, but the source has moved on
REFUSED = "REFUSED"          # we decline to compute this, and say why
FAILED = "FAILED"            # a check we expected to pass did not

_RANK = {VERIFIED: 0, UNVERIFIED: 1, STALE: 2, REFUSED: 3, FAILED: 4}


@dataclass
class Evidence:
    """One published number and everything needed to check it.

    `value` is what a reader sees. Everything else is why they may believe it.
    """
    metric: str
    value: float | int | None
    numerator: float | int | None = None
    denominator: float | int | None = None
    denominator_type: str = ""          # NEVER just "students" — see below
    formula: str = ""
    unit: str = ""
    fiscal_year: int | None = None
    district_number: str = ""
    source: str = ""                    # the publisher, as they name themselves
    source_url: str = ""
    source_vintage: str = ""            # which release of that file
    calculation_version: str = "1"
    # How much the published value may differ from numerator/denominator purely
    # because it is rounded for display. 0.5 = rounded to whole units; set 0.05
    # for a figure published to one decimal place.
    rounding: float = 0.5
    # Gate inputs
    recomputed_value: float | int | None = None
    recomputed_from: str = ""           # must not be the artefact being checked
    artifact: str = ""                  # the artefact this figure is published in
    independent_test: str = ""          # the CI test that re-derives this from source
    fresh: bool | None = None
    aim_ok: bool | None = None
    refused_because: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["gate"] = gate(self)
        return d


def _close(a: float, b: float) -> bool:
    """Equal enough. Published figures are rounded, so an exact match would
    fire on the rounding itself and be switched off within a month."""
    if a is None or b is None:
        return False
    if a == b:
        return True
    scale = max(abs(a), abs(b), 1.0)
    return abs(a - b) / scale < 1e-6


def gate(ev: Evidence) -> dict[str, Any]:
    """The publication gate. Returns {verdict, checks, why}.

    Never raises. A figure that cannot be assessed is not silently VERIFIED.
    """
    checks: dict[str, str] = {}
    why: list[str] = []

    # 4. COMPUTABILITY first — a refusal makes the other three moot.
    if ev.refused_because:
        checks["computability"] = "REFUSED"
        why.append(ev.refused_because)
        return {"verdict": REFUSED, "checks": checks, "why": why}
    if ev.value is None:
        checks["computability"] = "REFUSED"
        why.append("no value could be computed from the available data")
        return {"verdict": REFUSED, "checks": checks, "why": why}
    if ev.denominator is not None and not ev.denominator:
        checks["computability"] = "REFUSED"
        why.append("the denominator is zero, so a per-unit figure has no meaning")
        return {"verdict": REFUSED, "checks": checks, "why": why}
    checks["computability"] = "ok"

    # A per-unit figure with an unnamed denominator is not checkable. "Per
    # student" means nothing until it says WHICH student count — enrolment and
    # average daily attendance give different answers from the same numerator,
    # and this project already publishes two per-student figures that disagree.
    if ev.denominator is not None and not ev.denominator_type:
        checks["computability"] = "FAILED"
        why.append("a per-unit figure must name its denominator; "
                   "'per student' alone is not a definition")
        return {"verdict": FAILED, "checks": checks, "why": why}

    # 1a. ARITHMETIC — does the published value follow from its own components?
    #
    # This is a REAL check and a NARROW one, and the difference matters enough to
    # give it its own name. It catches a formula edited and a value not rebuilt,
    # a unit slip, a division by the wrong column. It cannot catch a wrong
    # numerator, because the numerator is published in the same file as the
    # value. Folding it into "correctness" would let a figure wear a badge that
    # says checked-against-the-state when nothing left the artefact.
    if ev.numerator is None or ev.denominator is None:
        checks["arithmetic"] = "n/a"
    else:
        implied = float(ev.numerator) / float(ev.denominator)
        if abs(float(ev.value) - implied) <= abs(ev.rounding) + 1e-9:
            checks["arithmetic"] = "ok"
        else:
            checks["arithmetic"] = "FAILED"
            why.append(f"the published numerator and denominator imply "
                       f"{implied:,.4f}, but the published value is {ev.value}")

    # 1b. CORRECTNESS — and the independence rule that makes it mean anything.
    if ev.recomputed_value is None:
        checks["correctness"] = "unchecked"
        if ev.independent_test:
            why.append("no independent recomputation was run here; the "
                       f"re-derivation from the publisher's own file is "
                       f"{ev.independent_test}, which runs in CI")
        else:
            why.append("no independent recomputation was supplied")
    elif ev.recomputed_from and ev.artifact and ev.recomputed_from == ev.artifact:
        checks["correctness"] = "FAILED"
        why.append(
            f"the recomputation derives from {ev.artifact!r}, the very artefact "
            "it is meant to validate — that proves the generator ran, not that "
            "the number is right")
        return {"verdict": FAILED, "checks": checks, "why": why}
    elif _close(float(ev.value), float(ev.recomputed_value)):
        checks["correctness"] = "ok"
    else:
        checks["correctness"] = "FAILED"
        why.append(f"independent recomputation gives {ev.recomputed_value}, "
                   f"published value is {ev.value}")

    # 2. FRESHNESS
    if ev.fresh is None:
        checks["freshness"] = "unchecked"
    elif ev.fresh:
        checks["freshness"] = "ok"
    else:
        checks["freshness"] = "STALE"
        why.append("the publisher has released data newer than the file this "
                   "was computed from")

    # 3. AIM
    if ev.aim_ok is None:
        checks["aim"] = "unchecked"
    elif ev.aim_ok:
        checks["aim"] = "ok"
    else:
        checks["aim"] = "FAILED"
        why.append("the source check did not confirm the exact file this "
                   "figure is published from")

    verdict = VERIFIED
    for state in checks.values():
        if state == "FAILED":
            verdict = max(verdict, FAILED, key=lambda v: _RANK[v])
        elif state == "STALE":
            verdict = max(verdict, STALE, key=lambda v: _RANK[v])
        elif state == "unchecked":
            # A number nobody checked must not wear the same badge as a number
            # somebody checked. VERIFIED is reserved for a figure an independent
            # recomputation agreed with; everything else that merely failed to
            # fail says so in its own word.
            verdict = max(verdict, UNVERIFIED, key=lambda v: _RANK[v])
    return {"verdict": verdict, "checks": checks, "why": why}


def refuse(metric: str, because: str, **kw) -> Evidence:
    """A published refusal. Louder than a blank and more honest than a guess."""
    return Evidence(metric=metric, value=None, refused_because=because, **kw)
