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


def match_districts(d: pd.DataFrame, finance: Path) -> pd.DataFrame:
    fin = pd.read_csv(finance, dtype={"district_number": str}, low_memory=False)
    names = fin.drop_duplicates("district_number")[["district_number", "district_name"]]
    key = lambda s: s.astype(str).str.upper().str.replace(r"[^A-Z]", "", regex=True)  # noqa: E731
    names["_k"] = key(names.district_name)
    d["_k"] = key(d.Issuer)
    # keep the first match per key; district names are unique in TEA's file
    return d.merge(names.drop_duplicates("_k"), on="_k", how="left")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bonds", type=Path, default=Path("data/texas_bond_elections.csv"))
    ap.add_argument("--finance", type=Path, default=Path("data/texas_finance_clean.csv"))
    ap.add_argument("--out", type=Path, default=Path("static/bond_data.json"))
    args = ap.parse_args()
    if not args.bonds.exists():
        print(f"missing {args.bonds}", file=sys.stderr)
        return 1

    d = match_districts(load(args.bonds), args.finance)
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
        districts[num] = {
            "district_number": num,
            "district_name": str(g.district_name.iloc[0]),
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
            "matched_pct": round(float(matched.mean()) * 100, 1),
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
    print(f"  athletics alone {bundling['athletics_alone']['pass_rate']}% vs bundled "
          f"{bundling['athletics_with_buildings']['pass_rate']}% "
          f"(median ask ${bundling['athletics_alone']['median_ask']/1e6:,.0f}M -> "
          f"${bundling['athletics_with_buildings']['median_ask']/1e6:,.0f}M)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
