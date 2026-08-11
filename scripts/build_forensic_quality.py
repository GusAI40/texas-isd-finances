"""Forensic-accounting tests on the filings themselves, and what they refuse to say.

The rest of this project asks what the money did. This asks whether the filings
behave like real filings — the standard forensic-accounting questions, applied
to 20,587 district-years of TEA's own data.

Three tests survive. One does not, and the one that does not is reported too,
because a technique that looks rigorous and does not fit is more dangerous than
no technique at all.

1. BENFORD'S LAW — statewide only
   Naturally occurring accounting figures follow a predictable first-digit
   distribution. Across all 1.2M filed figures the answer is MAD 0.0004 —
   Nigrini's "close conformity", about as clean as this test gets.

   **Per district it does not work, and this refuses to ship it.** Run naively
   it labels 1,104 of 1,211 districts "nonconforming", which would be a false
   accusation at scale. Two things prove it is an artefact: a null simulation
   drawing from a PERFECT Benford distribution scores "marginal" at n=300, and
   after matching each district against a null at its own sample size, 93% of
   districts still sit above z=3 — a population-wide offset, not individual
   anomalies. Benford needs figures spanning several orders of magnitude; one
   district's line items span very few. The test is valid on the pool and
   invalid on the parts.

2. INTERNAL RECONCILIATION — does a district's own filing add up?
   TEA's structure implies three identities. Objects and revenue reconcile for
   100% of district-years. Functions reconcile for 98.83%, and the 79 that do
   not are concentrated in a way worth reporting: 37 districts, all 2022-2025,
   all reporting operating spending their own function breakdown does not
   account for.

3. DEBT WITHOUT A BALLOT — who approved this?
   Texas permits school debt with no election: maintenance tax notes,
   lease-purchase, public facility corporations. TEA reports debt service but
   not how the debt was authorised, and the ballot is the only public record of
   what was voted on. 102 non-charter districts paid debt service between 2009
   and 2025 with no voter-approved bond on record.

What this is not
----------------
None of these is evidence of wrongdoing, and the layer says so in every
payload. A reconciliation gap is most often a coding error. Debt with no ballot
is usually a lawful instrument that simply does not require one. What they have
in common is that the public record does not answer an obvious question — and
naming the question precisely is the whole job.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
FIRST, LAST = 2009, 2025
BENFORD = np.array([math.log10(1 + 1 / k) for k in range(1, 10)])
RECONCILE_TOLERANCE = 0.01     # 1% — below this is rounding, above it is a gap
NULL_DRAWS = 200
SEED = 20260810


def benford_statewide(d: pd.DataFrame) -> dict:
    cols = [c for c in d.columns if c.startswith("all_funds_")]
    v = d[cols].apply(pd.to_numeric, errors="coerce").to_numpy(float).ravel()
    v = np.abs(v[np.isfinite(v)])
    v = v[v >= 10]
    lead = (v / 10 ** np.floor(np.log10(v))).astype(int)
    cnt = np.bincount(lead, minlength=10)[1:10]
    obs = cnt / cnt.sum()
    mad = float(np.abs(obs - BENFORD).mean())
    chi = float((((cnt - BENFORD * cnt.sum()) ** 2) / (BENFORD * cnt.sum())).sum())
    band = ("close conformity" if mad < .006 else "acceptable" if mad < .012
            else "marginally acceptable" if mad < .015 else "nonconformity")
    return {
        "figures_tested": int(cnt.sum()),
        "mad": round(mad, 5), "chi2": round(chi, 1),
        "nigrini_band": band,
        "expected_pct": [round(x * 100, 1) for x in BENFORD],
        "observed_pct": [round(x * 100, 1) for x in obs],
        "reading": "Across every figure Texas districts file, the leading digits "
                   "follow Benford's Law about as closely as this test can "
                   "measure. That is what an unmanipulated corpus looks like.",
    }


def benford_null(sizes: tuple[int, ...]) -> dict:
    """The evidence for refusing to publish the per-district version."""
    rng = np.random.default_rng(SEED)
    out = []
    for n in sizes:
        m = [float(np.abs(np.bincount(rng.choice(9, size=n, p=BENFORD), minlength=9) / n
                          - BENFORD).mean()) for _ in range(NULL_DRAWS)]
        med = float(np.median(m))
        out.append({
            "sample_size": n, "median_mad": round(med, 5),
            "band_it_would_be_assigned":
                "close" if med < .006 else "acceptable" if med < .012
                else "marginal" if med < .015 else "nonconformity",
        })
    return {
        "why": "Nigrini's conformity bands were calibrated on large samples of "
               "homogeneous transaction data. A district files 300-800 aggregate "
               "line items. This is what PERFECT Benford data scores at those "
               "sizes — the bands are meaningless there.",
        "draws_per_size": NULL_DRAWS,
        "null": out,
        "verdict": "per-district Benford is not published",
    }


def reconciliation(d: pd.DataFrame) -> dict:
    n = lambda c: pd.to_numeric(d[c], errors="coerce")  # noqa: E731
    fct = [c for c in d.columns if c.startswith("all_funds_") and "fct" in c]
    obj = ["all_funds_total_payroll_expenditures",
           "all_funds_total_professional_contracted_services_expenditure",
           "all_funds_total_supplies_materials_expenditures",
           "all_funds_total_other_operating_expenditures"]
    rev = ["all_funds_local_tax_revenue_from_m_o",
           "all_funds_other_local_intermediate_revenue",
           "all_funds_state_revenue", "all_funds_federal_revenue"]
    f = pd.DataFrame({
        "year": pd.to_numeric(d.year, errors="coerce"),
        "num": d.district_number, "name": d.district_name,
        "op": n("all_funds_total_operating_expenditures_by_obj"),
        "by_function": sum(n(c).fillna(0) for c in fct),
        "by_object": sum(n(c).fillna(0) for c in obj),
        "rev_total": n("all_funds_total_operating_revenue"),
        "rev_parts": sum(n(c).fillna(0) for c in rev),
        "enr": n("fall_survey_enrollment"),
    }).dropna(subset=["op"])
    f = f[(f.op > 0) & (f.enr > 0) & f.year.between(FIRST, LAST)]

    identities, gaps = [], []
    for label, parts, whole in (("spending by function", "by_function", "op"),
                                ("spending by object", "by_object", "op"),
                                ("revenue by source", "rev_parts", "rev_total")):
        ratio = (f[parts] / f[whole]).replace([np.inf, -np.inf], np.nan)
        off = (ratio - 1).abs()
        identities.append({
            "identity": f"{label} must sum to the reported total",
            "district_years": int(off.notna().sum()),
            "reconciles_within_0_1pct": round(float((off < .001).mean()) * 100, 2),
            "gaps_over_1pct": int((off > RECONCILE_TOLERANCE).sum()),
        })
        if label != "spending by function":
            continue
        bad = f[off > RECONCILE_TOLERANCE].copy()
        bad["shortfall_pct"] = (bad.by_function / bad.op - 1) * 100
        for x in bad.sort_values("shortfall_pct").itertuples():
            gaps.append({
                "district_number": x.num, "district_name": str(x.name),
                "year": int(x.year), "students": int(x.enr),
                "operating_reported": float(x.op),
                "functions_sum_to_pct_of_total": round(float(x.by_function / x.op * 100), 2),
                "unassigned": round(float(x.op - x.by_function)),
            })

    years = sorted({g["year"] for g in gaps})
    districts = sorted({g["district_number"] for g in gaps})
    return {
        "identities": identities,
        "gap_tolerance_pct": RECONCILE_TOLERANCE * 100,
        "gaps": gaps,
        "summary": {
            "district_years_with_a_gap": len(gaps),
            "distinct_districts": len(districts),
            "years_affected": years,
            "confined_to_recent_years": bool(years and min(years) >= 2022),
            "unassigned_total": round(sum(g["unassigned"] for g in gaps)),
        },
        "reading": "Objects and revenue reconcile for every district-year in the "
                   "window. Functions reconcile for all but a handful, and those "
                   "are operating dollars the district's own function breakdown "
                   "does not account for. Most often that is a coding error, not "
                   "a missing dollar — but it is the district's own filing "
                   "disagreeing with itself, and nobody else publishes it.",
    }


def debt_without_a_ballot(d: pd.DataFrame, bonds: dict) -> dict:
    n = lambda c: pd.to_numeric(d[c], errors="coerce")  # noqa: E731
    f = pd.DataFrame({
        "year": pd.to_numeric(d.year, errors="coerce"),
        "num": d.district_number, "name": d.district_name,
        "debt": n("all_funds_total_debt_service_expend_by_obj").fillna(0),
        "enr": n("fall_survey_enrollment"),
    })
    f = f[f.year.between(FIRST, LAST) & (f.enr > 0)]
    paid = f.groupby("num").debt.sum()
    latest = f[f.year == f.year.max()].set_index("num")

    rows = []
    for num, total in paid.items():
        if total <= 0 or num not in latest.index:
            continue
        rec = bonds.get(num)
        approved = float(rec["totals"]["approved"]) if rec else 0.0
        rows.append({"district_number": num,
                     "district_name": str(latest.loc[num, "name"]),
                     "students": int(latest.loc[num, "enr"]),
                     "debt_service_paid": float(total),
                     "principal_ever_approved": approved,
                     # A charter cannot hold a bond election at all, so its lack
                     # of one is not a question about authorisation.
                     "is_charter": num[3] == "8"})
    unexplained = [r for r in rows
                   if r["principal_ever_approved"] == 0 and not r["is_charter"]]
    unexplained.sort(key=lambda r: -r["debt_service_paid"])
    return {
        "districts_paying_debt_service": len(rows),
        "no_voter_approved_bond_on_record": {
            "districts": len(unexplained),
            "students": sum(r["students"] for r in unexplained),
            "debt_service_paid": round(sum(r["debt_service_paid"] for r in unexplained)),
            "largest": unexplained[:25],
        },
        "reading": "Texas permits school debt with no election — maintenance tax "
                   "notes, lease-purchase and public facility corporations among "
                   "them — and TEA reports debt service without recording how the "
                   "debt was authorised. These districts paid debt service across "
                   "the window with no matching voter-approved bond in the ballot "
                   "record. That is a lawful position to be in. It is also a "
                   "question the public record does not answer.",
        "limits": [
            "The ballot record is a compilation of county returns, not an agency "
            "register, so it may be incomplete for some districts. An absent "
            "election is weaker evidence than a present one.",
            "Records begin in 1958. Debt approved earlier would not appear, "
            "though school bonds rarely run long enough for that to explain "
            "service paid after 2009.",
            "Refunding existing debt does not require a new vote — but the "
            "original issue did, and would appear.",
            "Charters are excluded: they cannot hold a bond election, so the "
            "question does not arise for them.",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--finance", type=Path, default=ROOT / "data/texas_finance_clean.csv")
    ap.add_argument("--bonds", type=Path, default=ROOT / "static/bond_data.json")
    ap.add_argument("--out", type=Path, default=ROOT / "static/forensic_quality.json")
    args = ap.parse_args()
    if not args.finance.exists():
        print(f"missing {args.finance}", file=sys.stderr)
        return 1

    d = pd.read_csv(args.finance, dtype={"district_number": str}, low_memory=False)
    bonds = json.loads(args.bonds.read_text())["districts"] if args.bonds.exists() else {}

    payload = {
        "meta": {
            "first_year": FIRST, "last_year": LAST,
            "district_years": int(len(d)),
            "source": "TEA Summarized PEIMS Actual Financial Data; ballot record "
                      "compiled from county election returns",
            "what_this_is_not": "None of these tests is evidence of wrongdoing. A "
                                "reconciliation gap is most often a coding error; "
                                "debt without a ballot is usually a lawful "
                                "instrument that does not require one. What they "
                                "have in common is that the public record does not "
                                "answer an obvious question.",
            "no_named_individuals": True,
        },
        "benford": benford_statewide(d),
        "benford_per_district_refused": benford_null((300, 600, 800, 2000, 10000)),
        "reconciliation": reconciliation(d),
        "debt_without_a_ballot": debt_without_a_ballot(d, bonds),
    }
    args.out.write_text(json.dumps(payload, separators=(",", ":")))

    b, rc, db = payload["benford"], payload["reconciliation"], payload["debt_without_a_ballot"]
    print(f"wrote {args.out} ({args.out.stat().st_size / 1024:.0f} KB)\n")
    print(f"BENFORD (statewide): {b['figures_tested']:,} figures, MAD {b['mad']}, "
          f"{b['nigrini_band']}")
    print("  per-district Benford: REFUSED — "
          f"perfect data scores '{payload['benford_per_district_refused']['null'][0]['band_it_would_be_assigned']}' "
          f"at n={payload['benford_per_district_refused']['null'][0]['sample_size']}")
    print("\nRECONCILIATION:")
    for i in rc["identities"]:
        print(f"  {i['identity'][:46]:48}{i['reconciles_within_0_1pct']:>7.2f}% clean, "
              f"{i['gaps_over_1pct']} gaps")
    s = rc["summary"]
    print(f"  {s['district_years_with_a_gap']} district-years across "
          f"{s['distinct_districts']} districts, years {s['years_affected']}, "
          f"${s['unassigned_total']:,} unassigned")
    u = db["no_voter_approved_bond_on_record"]
    print(f"\nDEBT WITHOUT A BALLOT: {u['districts']} non-charter districts, "
          f"{u['students']:,} students, ${u['debt_service_paid']/1e6:,.0f}M paid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
