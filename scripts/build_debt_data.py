"""What Texas school districts still owe — the stock, not the yearly payment.

Every other debt number on this site is a FLOW: PEIMS reports what a district
paid out in debt service during a year. That answers "what did it cost you last
year" and cannot answer "how much is left", "for how long", or "how much of
what is left is interest nobody has paid yet". Those are the three questions
anybody actually asks about a mortgage, and until now the site could not answer
any of them about $236 billion of public borrowing.

The Texas Bond Review Board publishes the stock, per district per fiscal year,
split into the two instruments a district can sell:

    CIB   current interest bond — interest is paid twice a year, as normal.
    CAB   capital appreciation bond — nothing is paid until maturity. Interest
          compounds for the life of the bond and the whole amount lands at the
          end, typically after everyone who voted for it has moved away.

The file also runs FORWARD. Rows up to the current fiscal year are what was
actually outstanding; rows beyond it are the amortisation schedule for debt
already sold. That is how this can say when the borrowing clears — 2061 — and
it is the only forward-looking series in the repo, so it is labelled as a
schedule everywhere it surfaces.

The ratio that had to be thrown away
------------------------------------
The obvious CAB headline is "dollars repaid per dollar borrowed", computed as
(principal + interest) / principal. Computed on what is OUTSTANDING it is
garbage, and dangerously plausible garbage. As CAB principal is retired the
denominator shrinks while accreted interest does not, so the ratio climbs on its
own: Leander ISD reads 4.5x in 2014, 20.1x in 2025, 396x in 2030 and 698x in
2040 — describing no change in any deal, only the passage of time. Publishing
the current-year number would have put a fabricated 20x on a named district.

So the ratio is reported at each district's own PEAK — the year its CAB
obligation was largest, which is the commitment it actually signed. Leander's
peak is 2014: $596.3m of principal against $2,072.4m of deferred interest, 4.5x,
which is what was reported at the time. The current-year figure that survives is
an absolute one — deferred interest still owed — because a stock of dollars
cannot be inflated by its own denominator.

    python scripts/build_debt_data.py

Source: scripts/ingest_brb_debt.py (data.brb.texas.gov, first-party).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

# The Board's most recent completed fiscal year. Anything after this in the
# file is schedule, not history, and the two must never be added together.
CURRENT_FY = 2025

# Reported at peak, never on the residual — see the module docstring. The floor
# is what stops the artifact reappearing at the bottom of the range: a ratio
# computed against a few hundred thousand dollars of principal that is nearly
# retired measures rounding, not terms. La Joya ISD is the worked example —
# its CABs were sold before this record begins, so its series opens at 90.5x in
# 2005 and never shows the deal; "peak" would have published 22.6x for it.
# Above this floor a district's rise and fall is visible inside the window.
CAB_MIN_PRINCIPAL = 5_000_000
TOP_N = 25


def load(path: Path) -> pd.DataFrame:
    d = pd.read_csv(path, dtype={"district_number": str, "brb_id": str})
    d = d[d.district_number.notna() & (d.district_number != "")].copy()
    d["fiscal_year"] = pd.to_numeric(d.fiscal_year, errors="coerce")
    d = d.dropna(subset=["fiscal_year"])
    d["fiscal_year"] = d.fiscal_year.astype(int)
    d["principal"] = d.cib_principal_outstanding + d.cab_principal_outstanding
    d["interest"] = d.cib_interest_outstanding + d.cab_interest_outstanding
    d["total"] = d.principal + d.interest
    return d


def enrolment(finance: Path) -> dict[str, float]:
    f = pd.read_csv(finance, dtype={"district_number": str}, low_memory=False)
    f = f[f.fall_survey_enrollment > 0].sort_values("year")
    last = f.drop_duplicates("district_number", keep="last")
    return dict(zip(last.district_number, last.fall_survey_enrollment))


def names(finance: Path) -> dict[str, str]:
    f = pd.read_csv(finance, dtype={"district_number": str}, low_memory=False)
    n = f.drop_duplicates("district_number")
    return dict(zip(n.district_number, n.district_name))


def cab_peak(g: pd.DataFrame) -> dict | None:
    """The year this district's CAB obligation was largest, and its terms then.

    Peak rather than latest, because the latest is an artifact of amortisation.
    Only history is considered: a scheduled future year cannot be a commitment
    anyone made.

    Two guards, both about whether the record can see the deal at all:

    A GAP in the reported years disqualifies the district. Ysleta ISD reports
    CAB balances for 2005-2012 and again from 2020, with nothing between. Its
    largest reported total is 2020, and reading that as a peak gives 11.3x —
    for a year AFTER Texas capped new capital appreciation bonds at 4:1, which
    means no such deal could have been signed then. The real peak is inside the
    missing years. When the series is discontinuous the peak is unknowable, so
    none is published.

    A peak in the FIRST year of record is likewise no peak: the bond was sold
    before this data begins and the balance was already eroding when we picked
    it up. La Joya ISD opens at 90.5x in 2005 for exactly this reason.
    """
    hist = g[g.fiscal_year <= CURRENT_FY]
    active = sorted(hist[(hist.cab_principal_outstanding > 0) |
                         (hist.cab_interest_outstanding > 0)].fiscal_year)
    if not active:
        return None
    if active != list(range(active[0], active[-1] + 1)):
        return None                      # discontinuous — the peak may be in the gap
    h = hist[(hist.cab_principal_outstanding >= CAB_MIN_PRINCIPAL)]
    if h.empty:
        return None
    r = h.loc[(h.cab_principal_outstanding + h.cab_interest_outstanding).idxmax()]
    if int(r.fiscal_year) == active[0] and active[0] > int(g.fiscal_year.min()):
        return None                      # already declining when the record starts
    p = float(r.cab_principal_outstanding)
    i = float(r.cab_interest_outstanding)
    return {"year": int(r.fiscal_year), "principal": round(p), "deferred_interest": round(i),
            "repaid_per_dollar_borrowed": round((p + i) / p, 2)}


def build(debt: Path, finance: Path, out: Path) -> dict:
    d = load(debt)
    students, nm = enrolment(finance), names(finance)
    cur = d[d.fiscal_year == CURRENT_FY]

    tot = {k: float(cur[k].sum()) for k in
           ("principal", "interest", "total", "cib_principal_outstanding",
            "cib_interest_outstanding", "cab_principal_outstanding",
            "cab_interest_outstanding")}
    enrolled = sum(students.get(n, 0) for n in cur.district_number)

    # The schedule: what remains owed in each future year on debt already sold.
    sched = (d[d.fiscal_year > CURRENT_FY].groupby("fiscal_year").total.sum())
    sched = sched[sched > 0]

    districts: dict[str, dict] = {}
    cab_rows = []
    for num, g in d.groupby("district_number"):
        c = g[g.fiscal_year == CURRENT_FY]
        if c.empty:
            continue
        c = c.iloc[0]
        st = students.get(num)
        fut = g[(g.fiscal_year > CURRENT_FY) & (g.total > 0)]
        peak = cab_peak(g)
        rec = {
            "district_name": nm.get(num, str(num)),
            "students": int(st) if st else None,
            "principal": round(float(c.principal)),
            "interest": round(float(c.interest)),
            "total": round(float(c.total)),
            "per_student": round(float(c.total) / st) if st else None,
            "interest_share_pct": (round(100 * float(c.interest) / float(c.total), 1)
                                   if c.total else None),
            "clears_in": int(fut.fiscal_year.max()) if len(fut) else CURRENT_FY,
            # history only — the site must never plot a schedule as if it happened
            "history": [[int(r.fiscal_year), round(float(r.total))]
                        for r in g[g.fiscal_year <= CURRENT_FY]
                        .sort_values("fiscal_year").itertuples()],
        }
        if float(c.cab_principal_outstanding) or float(c.cab_interest_outstanding):
            rec["cab"] = {
                "principal_outstanding": round(float(c.cab_principal_outstanding)),
                "deferred_interest": round(float(c.cab_interest_outstanding)),
                "peak": peak,
            }
            cab_rows.append({"district_number": num, "district_name": rec["district_name"],
                             "students": rec["students"],
                             "deferred_interest": rec["cab"]["deferred_interest"],
                             "principal_outstanding": rec["cab"]["principal_outstanding"],
                             "peak": peak})
        districts[num] = rec

    cab_rows.sort(key=lambda r: -r["deferred_interest"])
    per_student = [(r["per_student"], k) for k, r in districts.items() if r["per_student"]]
    per_student.sort(reverse=True)

    payload = {
        "meta": {
            "source": "bond_review_board_debt",
            "publisher": "Texas Bond Review Board",
            "url": "https://data.brb.texas.gov/",
            "fiscal_year": CURRENT_FY,
            "districts": len(districts),
            "what_this_is": "Debt still owed — principal not yet repaid plus "
                            "interest not yet paid — as the Bond Review Board "
                            "reports it. Every other debt figure on this site is "
                            "what was paid in one year.",
            "what_this_is_not": "None of this is evidence of wrongdoing. Borrowing "
                                "to build schools is lawful, ordinary, and usually "
                                "approved at a ballot box. Capital appreciation "
                                "bonds were legal when sold and remain legal within "
                                "the limits set in 2015.",
            "limits": [
                f"Figures are as of fiscal {CURRENT_FY}, the Board's most recent "
                f"completed year. Years after it are the amortisation schedule for "
                f"debt already sold, not a forecast of future borrowing — districts "
                f"will issue more, so the schedule is a floor.",
                "Excludes obligations maturing in under a year, commercial paper, "
                "and special obligations that do not require Attorney General "
                "approval, per the Board's own scope note.",
                "Dollars repaid per dollar borrowed is reported at each district's "
                "PEAK year, not the current one. On outstanding balances the ratio "
                "rises on its own as principal is retired and is not a measure of "
                "anything.",
                f"No ratio is reported where CAB principal never reached "
                f"${CAB_MIN_PRINCIPAL / 1e6:,.0f}m in any year on record. Below that the "
                f"figure is dominated by a nearly-retired balance, and for districts "
                f"whose bonds were sold before 2005, or whose reported years have a "
                f"gap, the record never shows the deal at all. Their deferred "
                f"interest is still reported — it is the ratio, not the debt, that "
                f"is unknowable here.",
                "Debt outstanding is not comparable to a district's operating "
                "budget: it is a stock owed over decades, and it sits outside TEA's "
                "operating total entirely.",
                "68 of the Board's 1,035 listed school districts publish no series "
                "and carry no Board-tracked debt.",
            ],
        },
        "texas": {
            "districts_reporting": int(len(cur)),
            "students_covered": int(enrolled),
            "principal": round(tot["principal"]),
            "interest": round(tot["interest"]),
            "total": round(tot["total"]),
            "interest_share_pct": round(100 * tot["interest"] / tot["total"], 1),
            "per_student": round(tot["total"] / enrolled) if enrolled else None,
            "cib": {"principal": round(tot["cib_principal_outstanding"]),
                    "interest": round(tot["cib_interest_outstanding"])},
            "cab": {
                "districts": len(cab_rows),
                "principal_outstanding": round(tot["cab_principal_outstanding"]),
                "deferred_interest": round(tot["cab_interest_outstanding"]),
                "what_it_is": "Interest that has been accruing since the bond was "
                              "sold and on which nothing has been paid. It falls "
                              "due in a lump at maturity.",
                "largest": cab_rows[:TOP_N],
            },
            "clears_in": int(sched.index.max()) if len(sched) else CURRENT_FY,
            "schedule": [[int(y), round(float(v))] for y, v in sched.items()],
            "heaviest_per_student": [
                {"district_number": k, "district_name": districts[k]["district_name"],
                 "students": districts[k]["students"],
                 "per_student": districts[k]["per_student"],
                 "total": districts[k]["total"],
                 "interest_share_pct": districts[k]["interest_share_pct"]}
                for _, k in per_student[:TOP_N]],
        },
        "districts": districts,
    }

    out.write_text(json.dumps(payload, separators=(",", ":")))
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--debt", type=Path, default=ROOT / "data/brb_debt_outstanding.csv")
    ap.add_argument("--finance", type=Path, default=ROOT / "data/texas_finance_clean.csv")
    ap.add_argument("--out", type=Path, default=ROOT / "static/debt_data.json")
    args = ap.parse_args()

    p = build(args.debt, args.finance, args.out)
    t = p["texas"]
    kb = args.out.stat().st_size / 1024
    print(f"wrote {args.out.relative_to(ROOT)} — {p['meta']['districts']} districts, {kb:,.0f} KB\n")
    print(f"  still owed, fiscal {CURRENT_FY}:  ${t['total'] / 1e9:,.1f}B")
    print(f"    principal                   ${t['principal'] / 1e9:,.1f}B")
    print(f"    interest not yet paid       ${t['interest'] / 1e9:,.1f}B  "
          f"({t['interest_share_pct']}% of the total)")
    print(f"    per student                 ${t['per_student']:,}")
    print(f"  clears in                      {t['clears_in']}")
    c = t["cab"]
    print(f"\n  capital appreciation bonds: {c['districts']} districts still carry them")
    print(f"    principal outstanding       ${c['principal_outstanding'] / 1e6:,.0f}m")
    print(f"    interest deferred to maturity ${c['deferred_interest'] / 1e9:,.2f}B")
    for r in c["largest"][:5]:
        pk = r["peak"]
        at = (f"peak {pk['year']}: {pk['repaid_per_dollar_borrowed']}x on "
              f"${pk['principal'] / 1e6:,.0f}m" if pk else "no peak year on record")
        print(f"      {r['district_name'][:26]:<28} ${r['deferred_interest'] / 1e6:>7,.0f}m deferred   {at}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
