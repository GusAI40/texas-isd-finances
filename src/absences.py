"""When a section has nothing in it, say what the nothing means.

The finding that produced this module
-------------------------------------
A thousand simulated superintendents ran real journeys against production
(docs/SUPERINTENDENT_SIM.md). 830 completed with no fault. Of the 170 that
failed, almost none hit an error — they hit a **200 response with nothing in
it**. 331 districts (27.5%, 533,917 students) have at least one section that
renders empty, and the benchmarking journey — the one a superintendent runs
when they are actually trying to improve — broke 57.1% of the time.

Every one of those was correct behaviour. `/turnarounds` looks for a peer that
reversed a sustained deficit; for roughly half of districts none has, so it
returns an empty list. The endpoint was honest and the product was not, because
an empty list rendered as an empty box.

The emptiness is usually the more interesting finding
-----------------------------------------------------
    None of your 14 structural peers reversed a sustained deficit in
    seventeen years.

That is a stronger, more quotable claim than a list would have been, and it was
being thrown away. Likewise "never went to the voters for building debt since
1958" is a fact about a district, not the absence of one.

The distinction that has to survive
-----------------------------------
Three different things were rendering identically as a blank:

    NOT_APPLICABLE  the thing cannot exist here — a charter levies no property
                    tax, so it has no tax bill and never will
    DID_NOT_HAPPEN  it could have happened and did not — no bond election, no
                    peer that turned around. **This is a finding.**
    NOT_MEASURED    we do not know — a figure withheld because two estimates of
                    the tax base disagreed, or too few years to call a trend

"We don't know" and "it didn't happen" mean opposite things, and a reader who
cannot tell them apart is being misled by silence. Every absence here carries
its kind, a plain sentence, and — where one exists — the number that makes the
absence concrete.
"""
from __future__ import annotations

from typing import Any

NOT_APPLICABLE = "not_applicable"
DID_NOT_HAPPEN = "did_not_happen"
NOT_MEASURED = "not_measured"

KINDS = {
    NOT_APPLICABLE: "This cannot exist for this district.",
    DID_NOT_HAPPEN: "This could have happened here and did not. That is the finding.",
    NOT_MEASURED: "We do not have this. That is different from it not happening.",
}


def absence(section: str, kind: str, sentence: str, **extra: Any) -> dict:
    """One empty section, explained.

    `is_finding` is what the UI keys off: a DID_NOT_HAPPEN absence is promoted
    to look like any other finding, because it is one.
    """
    return {
        "section": section,
        "kind": kind,
        "is_finding": kind == DID_NOT_HAPPEN,
        "sentence": sentence,
        "what_kind_means": KINDS[kind],
        **extra,
    }


# --------------------------------------------------------------------------
# the absences the data can produce
# --------------------------------------------------------------------------

def no_bond_history(name: str, since: int = 1958) -> dict:
    """266 districts, 463,784 students. Not a gap — a decision, repeated."""
    return absence(
        "bonds", DID_NOT_HAPPEN,
        f"{name} has never asked voters for building debt in the "
        f"{2024 - since} years of records going back to {since}. Every other "
        f"district's debt on this site was approved at a ballot box; this one "
        f"has none to show.",
        first_year_of_record=since)


def no_tax_figure(name: str, is_charter: bool) -> dict:
    """188 districts, 440,240 students — but for two different reasons, and
    they are not interchangeable."""
    if is_charter:
        return absence(
            "tax", NOT_APPLICABLE,
            f"{name} is a charter district. It levies no property tax at all, "
            f"so there is no school tax on a home here — its money comes from "
            f"the state and federal government instead.")
    return absence(
        "tax", NOT_MEASURED,
        f"The tax figure for {name} is withheld. Two independent estimates of "
        f"its tax base disagree by more than 25%, and a wrong number on "
        f"someone's tax bill is worse than no number.")


def no_peer_turnaround(name: str, peers_scanned: int, years: int = 17) -> dict:
    """The single largest fault line: ~48% of requests, 1,567,284 students."""
    if not peers_scanned:
        return absence(
            "turnarounds", NOT_MEASURED,
            f"No structural peers could be identified for {name}, so there is "
            f"nothing to compare against. This happens for districts whose size "
            f"and student need are unusual enough to have no close match.",
            peers_scanned=0)
    return absence(
        "turnarounds", DID_NOT_HAPPEN,
        f"None of the {peers_scanned} districts most like {name} reversed a "
        f"sustained deficit or a sustained enrolment decline in {years} years. "
        f"There is no local example to follow — which is worth knowing before "
        f"anyone claims there is.",
        peers_scanned=peers_scanned, years=years)


def no_better_peer(name: str, pct_poor: float | None = None) -> dict:
    """58 districts, 77,580 students. Being at the top of your peer group is a
    finding, and it was rendering as a blank box."""
    context = (f" — among districts with a similar share of low-income students "
               f"({pct_poor:.0f}%)" if pct_poor is not None else "")
    return absence(
        "who_does_better", DID_NOT_HAPPEN,
        f"No district of {name}'s size and student need does better than it{context}. "
        f"On this measure it is already the one others would be compared against.")


def no_trend(name: str, years_reported: int, needed: int = 8) -> dict:
    """24 districts. Genuinely 'we don't know', and it must not read as
    'nothing changed'."""
    return absence(
        "trends", NOT_MEASURED,
        f"{name} reported finances in only {years_reported} of the seventeen "
        f"years, and {needed} are needed before a direction means anything. "
        f"This is missing data, not a flat line.",
        years_reported=years_reported, years_needed=needed)


def no_equity_record(name: str) -> dict:
    """115 districts, 33,362 students."""
    return absence(
        "equity", NOT_MEASURED,
        f"TEA's district STAAR file does not break out results for {name}'s "
        f"low-income students. Small groups are suppressed to protect student "
        f"privacy, which is why this is most often missing in small districts.")


def no_outcome_join(name: str) -> dict:
    return absence(
        "where_it_landed", NOT_MEASURED,
        f"No TEA Snapshot record could be matched to {name} for the reported "
        f"year, so its results cannot be set against what its student need "
        f"predicts.")


def nothing_crosses_a_threshold(name: str, thresholds: int) -> dict:
    """The 'no flags' case. Silence here was reading as a clean bill of health,
    which is a claim this data cannot support."""
    return absence(
        "flags", DID_NOT_HAPPEN,
        f"Every measure on {name} sits inside the ordinary range for Texas — "
        f"none of the {thresholds} published thresholds is crossed. That is a "
        f"statement about these four measures, not a clean bill of health.",
        thresholds_checked=thresholds)


def summarise(absences: list[dict]) -> dict:
    """What a page needs to decide how loudly to render this."""
    return {
        "count": len(absences),
        "findings": sum(1 for a in absences if a["is_finding"]),
        "sections": [a["section"] for a in absences],
        "kinds": sorted({a["kind"] for a in absences}),
    }
