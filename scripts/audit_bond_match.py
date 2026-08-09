"""Audit every bond-election-to-district match before anything is published.

The bond file is the only layer in this project joined on a NAME rather than a
TEA district number, which makes it the only layer where a published claim can
end up on the wrong district. This prints the whole join so a human can check
it, and exits non-zero if anything is left in a state that should not ship.

Read the three sections in this order:

  COLLISIONS   Names two TEA districts share. These are the ones that could go
               wrong. Each is listed with the county that separates them.
  UNMATCHED    Elections with no district. Every one of these is a district
               page silently missing its own ballot history, so the list should
               be short and each entry should have a reason.
  WEAK         Matches made by the prefix rule, i.e. a district that renamed
               itself. Few enough to read individually, and you should.

Usage:  python scripts/audit_bond_match.py [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_bond_data import county_of_code, load, match_districts  # noqa: E402
from district_match import stem  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bonds", type=Path, default=Path("data/texas_bond_elections.csv"))
    ap.add_argument("--finance", type=Path, default=Path("data/texas_finance_clean.csv"))
    ap.add_argument("--snapshot", type=Path, default=Path("data/snapshot_all.csv"))
    ap.add_argument("--json", type=Path, default=None, help="also write the report as JSON")
    args = ap.parse_args()
    for p in (args.bonds, args.finance):
        if not p.exists():
            print(f"missing {p}", file=sys.stderr)
            return 1

    fin = pd.read_csv(args.finance, dtype={"district_number": str}, low_memory=False)
    names = fin.drop_duplicates("district_number")[["district_number", "district_name"]]
    counties = county_of_code(args.snapshot)
    names = names.assign(
        name_stem=[stem(n) for n in names.district_name],
        county_name=[counties.get(n[:3], "?") for n in names.district_number])

    d = match_districts(load(args.bonds), args.finance, args.snapshot)
    matched = d.district_number.notna()

    # --- 1. names that cannot identify a district on their own --------------
    coll = names[names.name_stem.duplicated(keep=False)].sort_values(["name_stem", "district_number"])
    print(f"COLLISIONS — {coll.name_stem.nunique()} names shared by "
          f"{len(coll)} TEA districts\n")
    print(f"{'name':34}{'number':9}{'county':16}{'props resolved':>14}")
    per_district = d[matched].district_number.value_counts()
    for r in coll.itertuples():
        print(f"{r.district_name[:33]:34}{r.district_number:9}"
              f"{str(r.county_name)[:15]:16}{int(per_district.get(r.district_number, 0)):>14}")

    # A collision is only dangerous if a proposition actually landed on one of
    # them without the county being what decided it.
    risky = d[matched & d.district_number.isin(set(coll.district_number))
              & d.match_method.ne("name+county")]
    print(f"\n  propositions on a shared name NOT settled by county: {len(risky)}")
    for _, r in risky.iterrows():
        print(f"    {r['Issuer']} ({r.get('County')}) -> {r['district_number']} "
              f"via {r['match_method']}")

    # --- 2. elections with no district --------------------------------------
    un = d[~matched]
    print(f"\nUNMATCHED — {len(un)} of {len(d)} propositions "
          f"({len(un) / len(d) * 100:.1f}%), {un.Issuer.nunique()} issuers\n")
    if len(un):
        print(f"{'issuer':36}{'county':16}{'props':>6}")
        for (iss, cty), g in un.groupby(["Issuer", "County"], dropna=False):
            print(f"{str(iss)[:35]:36}{str(cty)[:15]:16}{len(g):>6}")

    # --- 3. matches that needed the weakest rule ----------------------------
    weak = d[d.match_method.eq("prefix+county")]
    print(f"\nWEAK — {len(weak)} propositions matched by rename/prefix, "
          f"{weak.Issuer.nunique()} issuers\n")
    tea_name = dict(zip(names.district_number, names.district_name))
    for (iss, num), g in weak.groupby(["Issuer", "district_number"]):
        print(f"    {iss} -> {num} {tea_name.get(num, '?')}  ({len(g)} props)")

    methods = Counter(d.match_method)
    print(f"\nSUMMARY  {len(d):,} propositions: " + ", ".join(
        f"{k} {v:,}" for k, v in methods.most_common()))
    print(f"         matched {matched.sum():,} ({matched.mean() * 100:.1f}%), "
          f"{d[matched].district_number.nunique():,} districts")

    report = {
        "propositions": int(len(d)),
        "matched": int(matched.sum()),
        "matched_pct": round(float(matched.mean()) * 100, 1),
        "methods": dict(methods),
        "colliding_names": sorted(set(coll.name_stem)),
        "risky_matches": int(len(risky)),
        "unmatched_issuers": sorted({str(x) for x in un.Issuer}),
        "weak_matches": sorted({f"{i} -> {n}" for i, n in
                                zip(weak.Issuer, weak.district_number)}),
    }
    if args.json:
        args.json.write_text(json.dumps(report, indent=1))
        print(f"\nwrote {args.json}")

    # A proposition on a shared name that county did not settle is a claim
    # that could be on the wrong district. Nothing ships in that state.
    if len(risky):
        print("\nFAIL: a shared name was resolved without the county agreeing.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
