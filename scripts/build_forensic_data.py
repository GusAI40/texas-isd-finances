"""Build the forensic file: the money questions TEA's own reporting hides.

Everything here is already public. None of it is easy to see, because the way
Texas reports school finance splits each question across files that do not
share a key, and reports two of the biggest numbers in a form that understates
them. This assembles the four questions a resident actually has, per district,
from artefacts already committed to this repo — no database, no new source.

The four questions
------------------
1. WHAT IS OUTSIDE THE OPERATING TOTAL.  Debt service is not in TEA's
   operating spend. A district can look lean on instruction while carrying the
   state's heaviest debt, and the two numbers are never printed together.
   Composed, never subtracted: total = operating + debt.
2. WHO PAYS.  TEA reports maintenance-and-operations revenue NET of recapture,
   so a district that sends money to the state looks less locally funded than
   it is. This uses GROSS local collections, which is why the statewide split
   here is 54/37/9 and not what the net figures imply.
3. WHAT THE BALLOT PROMISED.  TEA does not itemise facilities, so the ballot
   is the only public record of what school debt was FOR. Lifetime asked,
   approved, refused, and how much of it named athletics.
4. WHERE IT LANDED.  Results against what the district's own student need
   predicts — not against the state, which mostly measures poverty.

What this deliberately does NOT do
----------------------------------
- **No composite score.** Adding debt, recapture and results into one ranking
  would manufacture a league table that implies wrongdoing where the inputs
  measure four unrelated things. Each measure is ranked on its own terms and
  the thresholds are published in the payload.
- **No causal claim per district.** The bond-to-results test is statewide,
  fragile (see bond_data.json), and cannot be run on one district's handful of
  elections. A district's own numbers are reported as facts; the question of
  what caused them is left where the evidence leaves it.
- **No named individuals.** This is an account of public money, not of people.

Flags are descriptive and carry their own number, so "carries debt in the top
10% statewide" is a reading of the data, not an accusation.

Inputs are the committed artefacts, so this is reproducible with no network:
  static/economics_data.json  static/bond_data.json  static/outcomes_data.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Thresholds, published in the payload rather than buried here, so a reader
# can disagree with them explicitly.
TOP_DECILE = 90          # percentile at which "among the highest" starts
DEBT_VS_INSTRUCTION = 50  # cents of debt per dollar of instruction
LOCAL_SHARE_HIGH = 65     # % of gross revenue raised locally
ATHLETICS_SHARE = 50      # % of lifetime asks naming athletics (upper bound)
BEATS_BY = 3.0            # points at Meets, vs what student need predicts
MIN_PROPS_FOR_RATE = 3    # a pass rate below this many elections is noise


def pct_rank(values: list[float], v: float) -> int:
    """Percentile of v within values, 0-100. Ties count as below."""
    if not values:
        return 0
    below = sum(1 for x in values if x < v)
    return round(below / len(values) * 100)


def median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if not n:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def load(p: Path) -> dict:
    if not p.exists():
        print(f"missing {p} — run its build script first", file=sys.stderr)
        raise SystemExit(1)
    return json.loads(p.read_text())


def build(econ: dict, bonds: dict, outcomes: dict) -> dict:
    E = econ["districts"]
    B = bonds["districts"]
    OUT = outcomes["districts"]

    # Distributions are built once over every district that reports the
    # measure, so a percentile means the same thing on every page.
    debt_all = [d["allocation"]["debt_per_student"] for d in E.values()
                if d.get("allocation", {}).get("debt_per_student") is not None]
    recap_all = [d["recapture"]["per_student"] for d in E.values()
                 if d.get("recapture", {}).get("per_student")]
    local_all = [d["revenue"]["local_pct"] for d in E.values()
                 if d.get("revenue", {}).get("local_pct") is not None]

    districts, table = {}, []
    for num, e in E.items():
        alloc, rev = e.get("allocation") or {}, e.get("revenue") or {}
        recap, tax = e.get("recapture") or {}, e.get("tax") or {}
        b, o = B.get(num), OUT.get(num)
        students = e.get("students") or 0
        flags = []

        # --- 1. outside the operating total ---------------------------------
        debt = alloc.get("debt_per_student")
        debt_pct = pct_rank(debt_all, debt) if debt is not None else None
        outside = None
        if debt is not None:
            outside = {
                "per_student": debt,
                "percentile": debt_pct,
                "state_median": round(median(debt_all)),
                "cents_per_dollar_taught": alloc.get("cents_on_debt_per_dollar_taught"),
                "teachers_equivalent": alloc.get("teachers_equivalent_of_debt"),
                "operating_per_student": alloc.get("operating_per_student"),
                "total_per_student": alloc.get("total_per_student"),
                "annual_total": round(debt * students) if students else None,
            }
            if debt_pct is not None and debt_pct >= TOP_DECILE:
                flags.append({
                    "key": "debt_heavy", "tone": "watch",
                    "label": "Debt service among the highest in Texas",
                    "detail": f"${debt:,.0f} per student a year, above "
                              f"{debt_pct}% of districts. The state median is "
                              f"${median(debt_all):,.0f}.",
                })
            cents = alloc.get("cents_on_debt_per_dollar_taught")
            if cents and cents >= DEBT_VS_INSTRUCTION:
                flags.append({
                    "key": "debt_vs_instruction", "tone": "watch",
                    "label": "Debt costs more than half of what instruction costs",
                    "detail": f"{cents}¢ goes to debt for every dollar that "
                              f"reaches a classroom. None of it appears in the "
                              f"operating total TEA reports.",
                })

        # --- 2. who pays ----------------------------------------------------
        pays = None
        if rev.get("local_pct") is not None:
            r_ps = recap.get("per_student") or 0
            pays = {
                "local_pct": rev["local_pct"], "state_pct": rev.get("state_pct"),
                "federal_pct": rev.get("federal_pct"),
                "local_percentile": pct_rank(local_all, rev["local_pct"]),
                "state_local_pct": econ["macro"]["revenue"]["local_pct"],
                "tax_bill_on_home": tax.get("bill_on_home"),
                "home_value": tax.get("home_value"),
                "leaves_district": tax.get("leaves_district"),
                "recapture_per_student": r_ps,
                "recapture_paid": recap.get("paid"),
                "recapture_share_of_local_mo": recap.get("share_of_local_mo"),
                "recapture_percentile": pct_rank(recap_all, r_ps) if r_ps else None,
                "basis": rev.get("note"),
            }
            if r_ps:
                flags.append({
                    "key": "recapture", "tone": "info",
                    "label": "Sends money back to the state",
                    "detail": f"${r_ps:,.0f} per student leaves under recapture — "
                              f"${recap.get('paid', 0):,.0f} a year. TEA reports "
                              f"this district's revenue after that is taken out.",
                })
            if rev["local_pct"] >= LOCAL_SHARE_HIGH:
                flags.append({
                    "key": "locally_funded", "tone": "info",
                    "label": "Paid for locally, not by the state",
                    "detail": f"{rev['local_pct']}% of revenue is raised from local "
                              f"property, against {econ['macro']['revenue']['local_pct']}% "
                              f"statewide.",
                })

        # --- 3. what the ballot promised ------------------------------------
        ballot = None
        if b:
            t = b["totals"]
            approved_ps = round(t["approved"] / students) if students else None
            ath_share = round(t.get("athletics_asked", 0) / t["asked"] * 100) \
                if t.get("asked") else 0
            ballot = {
                "props": t["props"], "passed": t["passed"],
                "pass_rate": t["pass_rate"], "asked": t["asked"],
                "approved": t["approved"], "approved_per_student": approved_ps,
                "refused": round(t["asked"] - t["approved"]),
                "first_year": t["first_year"], "last_year": t["last_year"],
                "athletics_asked": t.get("athletics_asked", 0),
                "athletics_share_pct": ath_share,
                "match_method": b.get("match", {}).get("method"),
                "match_exact": b.get("match", {}).get("exact", True),
                "last_election": b["elections"][-1] if b.get("elections") else None,
            }
            if ath_share >= ATHLETICS_SHARE and t["asked"]:
                flags.append({
                    "key": "athletics", "tone": "watch",
                    "label": "Athletics named in most of what was asked for",
                    "detail": f"${t['athletics_asked']:,.0f} of ${t['asked']:,.0f} "
                              f"asked names athletics. Propositions bundle, so this "
                              f"is an upper bound, not an athletics-only figure.",
                })
            if t["props"] >= MIN_PROPS_FOR_RATE and t["pass_rate"] < 50:
                flags.append({
                    "key": "voters_refuse", "tone": "info",
                    "label": "Voters turn these down more often than not",
                    "detail": f"{t['passed']} of {t['props']} propositions passed "
                              f"since {t['first_year']}.",
                })

        # --- 4. where it landed ---------------------------------------------
        landed = None
        if o and o.get("expectation"):
            ex = o["expectation"]
            landed = {
                "actual": ex["actual"], "expected": ex["expected"],
                "gap": ex["gap"], "model_r2": ex.get("model_r2"),
                "spend_per_student": o.get("spend_per_student"),
                "spend_state_median": o.get("spend_state_median"),
                "need": o.get("need"), "year": o.get("year"),
            }
            if ex["gap"] >= BEATS_BY:
                flags.append({
                    "key": "beats_prediction", "tone": "good",
                    "label": "Does better than its student need predicts",
                    "detail": f"{ex['actual']}% at Meets against {ex['expected']}% "
                              f"predicted — {ex['gap']:+.1f} points.",
                })
            elif ex["gap"] <= -BEATS_BY:
                flags.append({
                    "key": "below_prediction", "tone": "watch",
                    "label": "Does worse than its student need predicts",
                    "detail": f"{ex['actual']}% at Meets against {ex['expected']}% "
                              f"predicted — {ex['gap']:+.1f} points.",
                })

        districts[num] = {
            "district_number": num,
            "district_name": e.get("district_name"),
            "students": students, "year": e.get("year"),
            "outside_operating": outside, "who_pays": pays,
            "ballot": ballot, "where_it_landed": landed,
            "flags": flags,
        }
        table.append({
            "n": num, "name": e.get("district_name"), "students": students,
            "debt": debt, "debt_pct": debt_pct,
            "recapture": recap.get("per_student") or 0,
            "local_pct": rev.get("local_pct"),
            "bill": tax.get("bill_on_home"),
            "approved_ps": ballot["approved_per_student"] if ballot else None,
            "gap": landed["gap"] if landed else None,
            "flags": len(flags),
        })

    table.sort(key=lambda r: -(r["students"] or 0))
    top = lambda k, n=25: [  # noqa: E731
        r for r in sorted((x for x in table if x.get(k) is not None),
                          key=lambda r: -r[k])[:n]]

    statewide = {
        "districts": len(districts),
        "revenue": econ["macro"]["revenue"],
        "recapture": econ["macro"]["recapture_concentration"],
        "debt_median": round(median(debt_all)),
        "debt_p90": round(sorted(debt_all)[int(len(debt_all) * 0.9)]) if debt_all else 0,
        "debt_total": round(sum((E[r["n"]]["allocation"].get("debt_per_student") or 0)
                                * (r["students"] or 0) for r in table)),
        "recapture_payers": sum(1 for r in table if r["recapture"]),
        "ballot": {
            "propositions": bonds["meta"]["propositions"],
            "districts": bonds["meta"]["districts_with_history"],
            "asked": bonds["meta"]["total_asked"],
            "approved": bonds["meta"]["total_approved"],
            "matched_pct": bonds["meta"]["matched_pct"],
        },
        "did_it_work": bonds.get("did_it_work"),
    }

    return {
        "meta": {
            "year": econ["meta"].get("year"),
            "built_from": ["static/economics_data.json", "static/bond_data.json",
                           "static/outcomes_data.json"],
            "sources": econ["meta"].get("sources", []),
            "thresholds": {
                "top_decile": TOP_DECILE,
                "debt_cents_per_dollar_taught": DEBT_VS_INSTRUCTION,
                "local_share_high_pct": LOCAL_SHARE_HIGH,
                "athletics_share_pct": ATHLETICS_SHARE,
                "beats_prediction_points": BEATS_BY,
                "min_propositions_for_a_pass_rate": MIN_PROPS_FOR_RATE,
            },
            "limits": [
                "Nothing here is a finding of wrongdoing. Every flag is a "
                "description of a published number against a published "
                "threshold, and the thresholds are above so you can disagree "
                "with them.",
                "There is deliberately no combined score. Debt, recapture, "
                "ballot history and results measure four unrelated things, and "
                "adding them would invent a ranking the data cannot support.",
                "Debt service sits outside TEA's operating total, so it is "
                "composed with it, never subtracted from it.",
                "Local revenue is gross property collections before recapture "
                "is deducted. TEA reports it net, which understates how "
                "locally funded a paying district is.",
                "Ballot amounts are as asked, in the dollars of their year, "
                "and are not inflation-adjusted.",
                "Whether a passed bond changed results is a statewide test, "
                "not a district one, and it is fragile — see the bond section.",
            ],
        },
        "statewide": statewide,
        "leaderboards": {
            "debt_per_student": top("debt"),
            "recapture_per_student": top("recapture"),
            "approved_per_student": top("approved_ps"),
            "beats_prediction": top("gap"),
        },
        "table": table,
        "districts": districts,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--economics", type=Path, default=Path("static/economics_data.json"))
    ap.add_argument("--bonds", type=Path, default=Path("static/bond_data.json"))
    ap.add_argument("--outcomes", type=Path, default=Path("static/outcomes_data.json"))
    ap.add_argument("--out", type=Path, default=Path("static/forensic_data.json"))
    args = ap.parse_args()

    payload = build(load(args.economics), load(args.bonds), load(args.outcomes))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, separators=(",", ":")))

    s = payload["statewide"]
    flagged = sum(1 for d in payload["districts"].values() if d["flags"])
    print(f"wrote {args.out} — {s['districts']:,} districts, "
          f"{args.out.stat().st_size / 1024:,.0f} KB")
    print(f"  debt outside the operating total: ${s['debt_total'] / 1e9:,.1f}B a year, "
          f"median ${s['debt_median']:,}/student, 90th pct ${s['debt_p90']:,}")
    print(f"  recapture payers: {s['recapture_payers']:,} districts")
    print(f"  ballot record: {s['ballot']['propositions']:,} propositions, "
          f"{s['ballot']['matched_pct']}% matched")
    print(f"  districts carrying at least one flag: {flagged:,}")
    from collections import Counter
    c = Counter(f["key"] for d in payload["districts"].values() for f in d["flags"])
    for k, v in c.most_common():
        print(f"    {k:22}{v:>6,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
