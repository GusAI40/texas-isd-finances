"""One row per Texas school district, holding everything needed to recognise it.

Why this exists
---------------
Five files in this project identify districts five different ways, and the work
of reconciling them was being done from scratch on every single run and then
thrown away:

    TEA           a six-digit number (057905) and a SHOUTED name
    Bond Review   its own integer id, and names with county hints in brackets
    Census TIGER  a boundary, or nothing at all if the district is a charter
    the ballot    an issuer name plus a county, and no number anywhere
    everyone      a name, which is not an identifier — twelve are shared

`scripts/district_match.py` re-derives county resolution on every run, and
`scripts/ingest_brb_debt.py` re-resolves 1,035 issuer names against it each
time. (Its 1,035 fetches are for the debt series themselves and are needed
regardless — it is the RESOLUTION that was repeated, not the download.) The
knowledge that actually cost effort — that "Sanford ISD" and
"Sanford-Fritch ISD" are one district, that Bond Review id 1746 is the DALLAS
Highland Park and not the Amarillo one, that an ampersand is a word — lived
only in the memory of a running process. Next TEA release it is rediscovered,
or quietly lost.

This is that knowledge, written down, committed, and diffable. If a mapping
ever changes, git shows it in review instead of a number moving on a page.

Why NOT a UUID
--------------
The obvious alternative is to mint our own identifier per district. It was
considered and rejected, and the reasons are worth keeping next to the code:

- The TEA number already does the one job an identifier has. 103 districts
  changed their NAME in this window and kept their number; none was ever reused
  for a different entity. Aransas County ISD became Rockport-Fulton ISD and
  stayed 004901.
- It would not touch the hard step. The Bond Review Board sends a name, not an
  id, so name+county resolution is needed either way — a new identifier just
  adds a third thing to keep in sync.
- It would break the promise the whole site rests on. A reader can take 057905
  to TEA and confirm Dallas ISD. A minted id is checkable against nobody but
  us, which makes us the authority instead of the state.
- 057905 means something: the first three digits are the county code, and that
  is precisely what fixed the bond join and caught a double-counted district.

So this is a lookup table keyed on the state's identifier, not a new namespace.

    python scripts/build_district_crosswalk.py

Committed to data/district_crosswalk.csv (whitelisted in .gitignore — it is a
small curated artefact, not a bulk download).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

COLUMNS = ["district_number", "district_name", "county", "county_code",
           "is_charter", "first_year", "last_year", "brb_id", "has_boundary",
           "former_names", "aliases"]

# The Bond Review Board disambiguates a shared name with a bracketed hint.
_HINT = re.compile(r"[(\[][^)\]]+[)\]]\s*$")


def _clean(name: str) -> str:
    return _HINT.sub("", str(name or "")).strip()


def tea(finance: Path) -> pd.DataFrame:
    """Names and the years each number is present. The name kept is the most
    recent one — a district that renamed is called what it is called now, and
    the old names are preserved separately rather than dropped."""
    f = pd.read_csv(finance, dtype={"district_number": str}, low_memory=False)
    f = f.dropna(subset=["district_number"])
    rows = []
    for num, g in f.groupby("district_number"):
        g = g.sort_values("year")
        names = [n for n in g.district_name.dropna().unique()]
        rows.append({
            "district_number": num,
            "district_name": names[-1] if names else num,
            # A rename is history, not noise: 103 districts have one, and a
            # reader searching the old name should still find the district.
            "former_names": names[:-1],
            "first_year": int(g.year.min()),
            "last_year": int(g.year.max()),
            # TEA encodes district type in the fourth digit; 8 is an
            # open-enrolment charter, which levies no tax and holds no bond
            # election. Half this project's absence logic turns on it.
            "is_charter": len(num) == 6 and num[3] == "8",
        })
    return pd.DataFrame(rows)


def counties(snapshot: Path) -> dict[str, tuple[str, str]]:
    """county_code -> (code, name). TEA writes '234 VAN ZANDT' in one column."""
    s = pd.read_csv(snapshot, dtype={"district_number": str},
                    usecols=["district_number", "county"], low_memory=False)
    out: dict[str, tuple[str, str]] = {}
    for num, county in zip(s.district_number, s.county):
        c = str(county or "").strip()
        if not c or pd.isna(county) or not isinstance(num, str):
            continue
        parts = c.split(None, 1)
        code, name = (parts[0], parts[1]) if len(parts) == 2 else (num[:3], c)
        out.setdefault(num, (code, name.title()))
    return out


def brb_ids(debt: Path) -> tuple[dict[str, str], dict[str, set]]:
    """TEA number -> Bond Review Board id, plus the names the Board uses.

    The Board's id is stable and its names are not: the same id appears as
    "Highland Park ISD (Dallas)" and "Highland Park ISD [Amarillo]". Recording
    both means the next run starts from a resolution a human has reviewed
    rather than one recomputed in silence.
    """
    ids: dict[str, str] = {}
    names: dict[str, set] = defaultdict(set)
    if not debt.exists():
        return ids, names
    with debt.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            num = (r.get("district_number") or "").strip()
            if not num:
                continue
            ids.setdefault(num, (r.get("brb_id") or "").strip())
            names[num].add(_clean(r.get("issuer_name")))
    return ids, names


def ballot_names(bonds: Path) -> dict[str, set]:
    """Issuer names as they appear on the ballot record, resolved the same way
    the bond layer resolves them — so an alias here is an alias the published
    join actually used."""
    out: dict[str, set] = defaultdict(set)
    if not bonds.exists():
        return out
    from build_bond_data import county_of_code
    from district_match import Resolver
    fin = pd.read_csv(ROOT / "data/texas_finance_clean.csv",
                      dtype={"district_number": str}, low_memory=False)
    n = fin.drop_duplicates("district_number")[["district_number", "district_name"]]
    res = Resolver.from_tea(list(zip(n.district_number, n.district_name)),
                            county_of_code(ROOT / "data/snapshot_all.csv"))
    with bonds.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            name = (r.get("Issuer") or "").strip()
            if not name:
                continue
            num, _ = res.resolve(name, (r.get("County") or "").strip())
            if num:
                out[num].add(name)
    return out


def build(finance: Path, snapshot: Path, debt: Path, bonds: Path,
          geo: Path, out: Path) -> pd.DataFrame:
    d = tea(finance)
    cty = counties(snapshot)
    ids, brb_names = brb_ids(debt)
    ballot = ballot_names(bonds)
    boundaries = set()
    if geo.exists():
        boundaries = set(json.loads(geo.read_text()).get("d", {}))

    rows = []
    for r in d.itertuples():
        num = r.district_number
        code, county = cty.get(num, (num[:3], ""))
        # An alias is any name a source used for this district that is not what
        # TEA calls it now. Recorded so the next join starts from what the last
        # one learned instead of rediscovering it.
        seen = {str(r.district_name).upper()}
        alias = sorted({a for a in (brb_names.get(num, set()) | ballot.get(num, set()))
                        if a and a.upper() not in seen})
        rows.append({
            "district_number": num,
            "district_name": r.district_name,
            "county": county,
            "county_code": code,
            "is_charter": r.is_charter,
            "first_year": r.first_year,
            "last_year": r.last_year,
            "brb_id": ids.get(num, ""),
            "has_boundary": num in boundaries,
            "former_names": " | ".join(r.former_names),
            "aliases": " | ".join(alias),
        })
    df = pd.DataFrame(rows, columns=COLUMNS).sort_values("district_number")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return df


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--finance", type=Path, default=ROOT / "data/texas_finance_clean.csv")
    ap.add_argument("--snapshot", type=Path, default=ROOT / "data/snapshot_all.csv")
    ap.add_argument("--debt", type=Path, default=ROOT / "data/brb_debt_outstanding.csv")
    ap.add_argument("--bonds", type=Path, default=ROOT / "data/texas_bond_elections.csv")
    ap.add_argument("--geo", type=Path, default=ROOT / "static/district_geo.json")
    ap.add_argument("--out", type=Path, default=ROOT / "data/district_crosswalk.csv")
    args = ap.parse_args()

    df = build(args.finance, args.snapshot, args.debt, args.bonds, args.geo, args.out)
    print(f"wrote {args.out.relative_to(ROOT)} — {len(df):,} districts, "
          f"{args.out.stat().st_size:,} bytes\n")
    print(f"  with a county           {(df.county != '').sum():>6,}")
    print(f"  with a Bond Review id   {(df.brb_id != '').sum():>6,}")
    print(f"  with a Census boundary  {df.has_boundary.sum():>6,}")
    print(f"  charters (no tax, no bond election, no boundary)  {df.is_charter.sum():>6,}")
    print(f"  carrying a former name  {(df.former_names != '').sum():>6,}")
    print(f"  carrying an alias       {(df.aliases != '').sum():>6,}")
    shared = df[df.district_name.duplicated(keep=False)]
    print(f"\n  names shared by more than one district: "
          f"{shared.district_name.nunique()} across {len(shared)} districts")
    for name, g in list(shared.groupby("district_name"))[:4]:
        print(f"    {name:<24} " +
              " / ".join(f"{t.district_number} ({t.county})" for t in g.itertuples()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
