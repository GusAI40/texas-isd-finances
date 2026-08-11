"""Build the bond-election story: what your district asked you for, and how you voted.

TEA's financial data can say how much a district spends servicing debt. It
cannot say what the debt was FOR — TEA does not itemise facilities, so a
stadium is not separable from a roof. The ballot can. Every dollar of school
debt in Texas passed through an election with a stated purpose and a recorded
vote, and that is the only public record that names what the money bought.

This turns 4,588 decided propositions (1958-2024) into one narrative payload.

The story it has to carry, in four beats
----------------------------------------
1. YOURS      Every bond your district ever put on a ballot, and how it went.
              The personal hook: these are decisions with dates, not a model.
2. FOR WHAT   Pass rate by purpose. Voters back classrooms about three times in
              four; stadiums, fewer than half. This is the answer to "where did
              the debt come from" that TEA's own data cannot give.
3. THE SHIFT  Asks by era against approval rate. Districts asked for more in
              2020-24 than in the whole of the 2010s while approval fell to a
              66-year low — the demand side of the I&S rate rise the economics
              layer already measures.
4. WHAT PASSES  Athletics alone vs athletics bundled with classrooms. Bundling
              lifts the pass rate and quadruples the median ask, which is the
              single most useful thing a voter can know before the next
              election.

Honest limits, carried in the payload
-------------------------------------
- Propositions bundle. A proposition reading "School Building & Gymnasium"
  counts in athletics, so athletics dollars are an UPPER bound. Athletics-only
  is reported separately and both numbers ship; quoting the flattering one
  would be a lie of selection.
- Purpose is free text written by 1,000-odd districts over 66 years, so the
  classifier is keyword-based and its rules are published in the payload
  rather than hidden here.
- Amounts are as-asked, in the dollars of their year, NOT inflation-adjusted —
  a 1958 dollar and a 2024 dollar are both "asked" but are not comparable.
  Era totals are therefore shown as counts and pass rates first.

Source: user-supplied export of Texas ISD bond election results (Municipal
Advisory Council-style issuer/election/result records), matched to TEA district
numbers by normalised name at 97%.

NOTE: two companion files exist carrying a vendor's CRM — named sales reps,
per-district revenue, commission percentages. They are deliberately NOT read
here and must never enter this repo.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from district_match import Resolver  # noqa: E402

# Keyword rules, published in the payload so a reader can audit the labels.
RULES = [
    ("athletics", r"stadium|athletic|gymnas|natatorium|field ?house|tennis|track|sports"),
    ("arts venues", r"performing art|auditorium|fine art|theat"),
    ("technology", r"technolog|computer"),
    ("security", r"secur"),
    ("buses", r"bus\b|buses|transport"),
    ("refinancing", r"refund"),
]
MIN_PLAUSIBLE_VOTES = 20
# Higher is weaker evidence. Used to label a district by its shakiest match.
METHOD_RANK = {"name+county": 0, "name": 1, "prefix+county": 2}
BUILDINGS = r"school building|building|classroom|campus|elementary|high school|renovat"


def classify(desc: str) -> str:
    s = str(desc).lower()
    for name, pat in RULES:
        if re.search(pat, s):
            return name
    return "buildings & other"


def load(path: Path) -> pd.DataFrame:
    d = pd.read_csv(path, encoding="utf-8-sig")
    d.columns = [c.strip() for c in d.columns]
    # Dates arrive as Excel serials; 1899-12-30 is the origin Excel actually uses.
    d["date"] = pd.to_datetime(d["Elect. Date"], unit="D", origin="1899-12-30", errors="coerce")
    d["amount"] = pd.to_numeric(d["$ Amount"], errors="coerce")
    d["year"] = d.date.dt.year
    for c in ("Votes For", "Votes Against"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    # 21.5% of records carry a vote total under 20 — a $40M bond recorded as
    # "1 for, 0 against". These are placeholders, not turnout, and printing them
    # as real counts would put an obviously false number in front of a reader.
    # Treat them as unreported; the RESULT is still trustworthy, only the tally
    # is not.
    total_votes = d["Votes For"].fillna(0) + d["Votes Against"].fillna(0)
    d["votes_reported"] = total_votes >= MIN_PLAUSIBLE_VOTES
    d.loc[~d.votes_reported, ["Votes For", "Votes Against"]] = pd.NA
    d = d[d.Result.isin(["Carried", "Defeated"])].copy()
    d["passed"] = d.Result.eq("Carried")
    d["category"] = d["Purpose Description"].map(classify)
    desc = d["Purpose Description"].astype(str).str.lower()
    d["has_athletics"] = desc.str.contains(RULES[0][1], regex=True)
    d["has_buildings"] = desc.str.contains(BUILDINGS, regex=True)
    return d.dropna(subset=["year"])


def county_of_code(snapshot: Path) -> dict[str, str]:
    """3-digit TEA county code -> county name, read from TEA's own Snapshot
    file, which writes the two together as '057 DALLAS'."""
    if not snapshot.exists():
        return {}
    sn = pd.read_csv(snapshot, dtype={"district_number": str}, low_memory=False)
    if "county" not in sn.columns:
        return {}
    sn = sn.dropna(subset=["county", "district_number"])
    return {num[:3]: str(c).split(" ", 1)[-1]
            for num, c in zip(sn.district_number, sn.county)}


def match_districts(d: pd.DataFrame, finance: Path, snapshot: Path) -> pd.DataFrame:
    """Attach a TEA district number to every proposition, or refuse to.

    Matching on name alone both dropped and mis-attributed elections; see
    scripts/district_match.py for what went wrong and why county settles it.
    The method used is kept on the row so the audit can report it.
    """
    fin = pd.read_csv(finance, dtype={"district_number": str}, low_memory=False)
    names = fin.drop_duplicates("district_number")[["district_number", "district_name"]]
    tea_name = dict(zip(names.district_number, names.district_name))

    # Prefer the crosswalk, which knows every name a district has ever carried.
    # Building from the finance file alone learns only the EARLIEST name — 64 of
    # the 103 districts that renamed were unresolvable by the name they go by
    # today, so a source using a current name would be silently dropped. Falls
    # back to the old path so this script still runs before the crosswalk is
    # built (setup order matters: the crosswalk is built from the bond file).
    crosswalk = Path(__file__).resolve().parent.parent / "data/district_crosswalk.csv"
    if crosswalk.exists():
        resolver = Resolver.from_crosswalk(crosswalk)
    else:
        resolver = Resolver.from_tea(
            list(zip(names.district_number, names.district_name)),
            county_of_code(snapshot))

    resolved = [resolver.resolve(iss, cty)
                for iss, cty in zip(d.Issuer, d.get("County", pd.Series([""] * len(d))))]
    d = d.copy()
    d["district_number"] = [num for num, _ in resolved]
    d["match_method"] = [meth for _, meth in resolved]
    d["district_name"] = [tea_name.get(num) for num, _ in resolved]
    return d


def bond_outcome_test(d: pd.DataFrame, snapshot: Path) -> dict | None:
    """Did passing the bond change results?

    The claim on every bond campaign is that the buildings will help children
    learn. It is testable: compare each district with ITSELF — the residual
    against what its student need predicts, 2-4 years after the vote, against
    the 3 years before — and then compare districts whose bond PASSED with
    districts whose bond was DEFEATED. Both groups went to the ballot, so both
    had a board that thought it needed the money; only one got it.

    A bond in a growing district buys SEATS, not scores, and safety and roofs
    are real goods STAAR cannot see. This measures test results, which is one
    thing a building might buy and not the only one.
    """
    import numpy as np
    if not snapshot.exists():
        return None
    sn = pd.read_csv(snapshot, dtype={"district_number": str}, low_memory=False)
    need = ["pct_econ_disadv", "pct_emergent_bilingual", "pct_special_ed"]
    out = "test_all_meets"
    if out not in sn.columns:
        return None
    res = {}
    for yr, g in sn.dropna(subset=[out] + need).groupby("year"):
        X = np.column_stack([np.ones(len(g)), g[need].to_numpy(float)])
        beta = np.linalg.lstsq(X, g[out].to_numpy(float), rcond=None)[0]
        res[yr] = pd.Series(g[out].to_numpy(float) - X @ beta, index=g.district_number.values)
    R = pd.DataFrame(res)
    if R.empty:
        return None

    rows = []
    for r in d[d.district_number.notna()].itertuples():
        num, y = r.district_number, int(r.year)
        if num not in R.index or pd.isna(r.amount):
            continue
        pre = [R.loc[num, c] for c in R.columns if y - 3 <= c < y and pd.notna(R.loc[num, c])]
        post = [R.loc[num, c] for c in R.columns if y + 2 <= c <= y + 4 and pd.notna(R.loc[num, c])]
        if len(pre) < 2 or len(post) < 2:
            continue
        rows.append({"passed": bool(r.passed), "delta": float(np.mean(post) - np.mean(pre)),
                     "district": num})
    if len(rows) < 100:
        return None
    f = pd.DataFrame(rows)
    a, b = f[f.passed].delta, f[~f.passed].delta
    # Welch's t, since the two groups differ in size and spread
    se = float(np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)))
    t = float((a.mean() - b.mean()) / se) if se else 0.0
    from math import erfc, sqrt
    pval = float(erfc(abs(t) / sqrt(2)))       # normal approximation, n is large
    return {
        "bonds_tested": int(len(f)), "districts": int(f.district.nunique()),
        "passed_n": int(len(a)), "passed_change": round(float(a.mean()), 2),
        "defeated_n": int(len(b)), "defeated_change": round(float(b.mean()), 2),
        "difference": round(float(a.mean() - b.mean()), 2),
        "ci_low": round(float(a.mean() - b.mean() - 1.96 * se), 2),
        "ci_high": round(float(a.mean() - b.mean() + 1.96 * se), 2),
        "p_value": round(pval, 3),
        "distinguishable_from_zero": bool(pval < 0.05),
        # This result sat at p=0.061 until the district match was corrected and
        # 147 previously-dropped propositions came back. It crossed 0.05 on a
        # 3% change in sample, which is exactly what a borderline result does.
        # Publishing it as settled would be overclaiming, so the flag travels
        # with the number and the page reads it.
        "fragile": bool(0.01 < pval < 0.05),
        "window": "results 2-4 years after the vote against the 3 years before, "
                  "each district compared with itself",
        "caveat": "A bond in a growing district buys seats, not scores, and safety "
                  "and roofs are real goods a test cannot see. This measures test "
                  "results only.",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bonds", type=Path, default=Path("data/texas_bond_elections.csv"))
    ap.add_argument("--finance", type=Path, default=Path("data/texas_finance_clean.csv"))
    ap.add_argument("--snapshot", type=Path, default=Path("data/snapshot_all.csv"))
    ap.add_argument("--out", type=Path, default=Path("static/bond_data.json"))
    args = ap.parse_args()
    if not args.bonds.exists():
        print(f"missing {args.bonds}", file=sys.stderr)
        return 1

    d = match_districts(load(args.bonds), args.finance, args.snapshot)
    matched = d.district_number.notna()

    # ---- beat 2: what voters back, by purpose ----
    by_cat = []
    for cat, g in d.groupby("category"):
        by_cat.append({
            "category": cat, "props": int(len(g)),
            "pass_rate": round(float(g.passed.mean()) * 100, 1),
            "asked": float(g.amount.sum()), "approved": float(g[g.passed].amount.sum()),
        })
    by_cat.sort(key=lambda r: -r["asked"])

    # ---- beat 3: the shift, era by era ----
    eras = [(1958, 1999), (2000, 2009), (2010, 2019), (2020, 2024)]
    by_era = []
    for a, b in eras:
        g = d[(d.year >= a) & (d.year <= b)]
        if not len(g):
            continue
        ath = g[g.has_athletics]
        by_era.append({
            "era": f"{a}–{b}", "start": a, "end": b, "props": int(len(g)),
            "pass_rate": round(float(g.passed.mean()) * 100, 1),
            "asked": float(g.amount.sum()),
            "athletics_pass_rate": round(float(ath.passed.mean()) * 100, 1) if len(ath) else None,
        })

    # ---- beat 4: does bundling a stadium with classrooms get it passed? ----
    pure = d[d.has_athletics & ~d.has_buildings]
    bundled = d[d.has_athletics & d.has_buildings]
    schools = d[~d.has_athletics & d.has_buildings]
    bundling = {
        grp: {"props": int(len(g)), "pass_rate": round(float(g.passed.mean()) * 100, 1),
              "median_ask": float(g.amount.median()), "asked": float(g.amount.sum())}
        for grp, g in (("athletics_alone", pure), ("athletics_with_buildings", bundled),
                       ("buildings_alone", schools))
    }
    stadium = d[d["Purpose Description"].astype(str).str.contains("stadium", case=False, na=False)]

    # ---- beat 1: every district's own ballot history ----
    districts = {}
    for num, g in d[matched].groupby("district_number"):
        g = g.sort_values("date")
        # itertuples cannot expose columns whose names contain spaces, so index
        # the frame directly rather than renaming every source column.
        elections = [{
            "date": r["date"].strftime("%Y-%m-%d"), "year": int(r["year"]),
            "amount": None if pd.isna(r["amount"]) else float(r["amount"]),
            "purpose": str(r["Purpose Description"]), "category": r["category"],
            "passed": bool(r["passed"]),
            "for": None if pd.isna(r["Votes For"]) else int(r["Votes For"]),
            "against": None if pd.isna(r["Votes Against"]) else int(r["Votes Against"]),
            "votes_reported": bool(r["votes_reported"]),
        } for _, r in g.iterrows()]
        asked, approved = float(g.amount.sum()), float(g[g.passed].amount.sum())
        # If any of a district's elections needed the weakest method, say so
        # for the whole file rather than per row — the reader is judging
        # whether to trust the history, not one line of it.
        method = max(g.match_method, key=lambda m: METHOD_RANK.get(m, 9))
        districts[num] = {
            "district_number": num,
            "district_name": str(g.district_name.iloc[0]),
            "match": {"method": method, "exact": method == "name+county",
                      "source_names": sorted(set(g.Issuer.astype(str)))},
            "elections": elections,
            "totals": {
                "props": int(len(g)), "passed": int(g.passed.sum()),
                "pass_rate": round(float(g.passed.mean()) * 100, 1),
                "asked": asked, "approved": approved,
                "approved_share": round(approved / asked, 3) if asked else None,
                "first_year": int(g.year.min()), "last_year": int(g.year.max()),
                "athletics_asked": float(g[g.has_athletics].amount.sum()),
            },
        }

    payload = {
        "meta": {
            "propositions": int(len(d)),
            "districts_with_history": len(districts),
            # Never round UP to 100. One unresolved issuer out of 4,992 is
            # 99.98%, and printing that as "100.0% matched" claims a complete
            # join that does not exist. Floor it below the last tenth instead,
            # so the only way to display 100 is to actually match everything.
            "matched_pct": (100.0 if bool(matched.all())
                            else min(round(float(matched.mean()) * 100, 1), 99.9)),
            "unmatched": int((~matched).sum()),
            "match_methods": {k: int(v) for k, v in
                              d.match_method.value_counts().items()},
            "unmatched_issuers": sorted(
                {str(x) for x in d.loc[~matched, "Issuer"]}),
            "first_year": int(d.year.min()), "last_year": int(d.year.max()),
            "votes_reported_pct": round(float(d.votes_reported.mean()) * 100, 1),
            "total_asked": float(d.amount.sum()),
            "total_approved": float(d[d.passed].amount.sum()),
            "classifier_rules": {name: pat for name, pat in RULES},
            "limits": [
                "Propositions bundle purposes. A proposition reading 'School Building "
                "& Gymnasium' is counted under athletics, so athletics dollars are an "
                "upper bound; the athletics-only figure is reported separately.",
                "Amounts are as asked, in the dollars of their year, and are not "
                "inflation-adjusted — counts and pass rates are the comparable measures "
                "across eras.",
                "Purpose is free text written by hundreds of districts over 66 years; "
                "the keyword rules used to classify it are published above.",
                f"About a fifth of records carry a vote tally under {MIN_PLAUSIBLE_VOTES} "
                "(a multi-million-dollar bond recorded as '1 for, 0 against'). Those are "
                "placeholders rather than turnout, so the tally is shown as unreported. "
                "The carried/defeated result itself is unaffected.",
            ],
        },
        "by_purpose": by_cat,
        "by_era": by_era,
        "bundling": bundling,
        "stadium": {
            "props": int(len(stadium)),
            "pass_rate": round(float(stadium.passed.mean()) * 100, 1),
            "asked": float(stadium.amount.sum()),
            "approved": float(stadium[stadium.passed].amount.sum()),
        },
        "did_it_work": bond_outcome_test(d, args.snapshot),
        "districts": districts,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, separators=(",", ":")))
    m = payload["meta"]
    print(f"wrote {args.out} — {m['propositions']:,} propositions, "
          f"{m['districts_with_history']:,} districts, {args.out.stat().st_size/1024:,.0f} KB")
    print(f"  matched to TEA districts: {m['matched_pct']}%")
    print(f"  stadiums named specifically: {payload['stadium']['props']} props, "
          f"{payload['stadium']['pass_rate']}% pass")
    w = payload["did_it_work"]
    if w:
        print(f"  did the bond change results? passed {w['passed_change']:+.2f} vs "
              f"defeated {w['defeated_change']:+.2f} = {w['difference']:+.2f} "
              f"(p={w['p_value']}, "
              f"{'significant' if w['distinguishable_from_zero'] else 'not distinguishable from zero'})")
    print(f"  athletics alone {bundling['athletics_alone']['pass_rate']}% vs bundled "
          f"{bundling['athletics_with_buildings']['pass_rate']}% "
          f"(median ask ${bundling['athletics_alone']['median_ask']/1e6:,.0f}M -> "
          f"${bundling['athletics_with_buildings']['median_ask']/1e6:,.0f}M)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
