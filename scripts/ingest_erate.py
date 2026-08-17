"""Ingest Texas E-Rate funding first-party from USAC's open-data portal.

E-Rate is the federal program that discounts school internet and telecom —
roughly a quarter of a billion dollars a year flowing to Texas districts,
and no other layer on this site sees it: PEIMS shows federal revenue as one
line, and E-Rate discounts largely never touch a district's books at all
(USAC pays the vendor). This is money for connectivity that exists in no
TEA file.

Two datasets, both Socrata, both the administrator's own record:

  qdmp-ygft  FRN Status (FCC Form 471) — one row per funding request:
             year, applicant (BEN), status, service type, the committed
             amount and the authorized disbursements against it.
  7i5i-83qf  Supplemental Entity Information — one row per entity (BEN):
             name, type, county, parent, and the state/NCES codes an
             applicant chose to enter.

THE RULE THAT MAKES THE NUMBERS HONEST — learned by nearly publishing a
false $373M finding during scoping: `funding_commitment_request` on a
PENDING or CANCELLED FRN is the amount the applicant ASKED for, not a
commitment (FY2018 still carries $356M of "Pending" requests eight years
later). Only status "Funded" rows are commitments. Summing all statuses
gives $657M for FY2018 against $284M disbursed — a scandal-shaped 43%
utilization that is actually a category error. Funded-only is $301M
against $284M: 94% drawn, a non-story. This script keeps every status in
the raw file and lets the builder enforce Funded-only, so the refusal is
testable.

THE JOIN — a BEN is USAC's id, not TEA's, and the entity file's code
columns are self-reported and sparse (Dallas ISD's own row carries no code
at all). Resolution order, most trustworthy first, recorded per BEN:

  1. state_lea_code — six digits, must exist in the district crosswalk.
  2. children — the 6-digit prefix of the BEN's child schools'
     state_school_code (a Texas campus code IS district+campus), required
     to be UNANIMOUS across coded children.
  3. name+county — scripts/district_match.py against the crosswalk, the
     bond layer's resolver, county from the entity's physical_county.
     USAC spells districts "Dallas Indep School District", so a USAC
     suffix normaliser runs first.
  4. unmatched — counted and named, never guessed.

Where two roads disagree, the BEN is refused outright (disagreement means
somebody's data entry is wrong, and guessing which is how wrong-district
claims ship).

Outputs (data/, gitignored — the artifact builder reads these):
  data/usac_erate_frns.csv     every TX FRN row, selected columns
  data/usac_entities_tx.csv    every TX entity row, selected columns
  data/erate_district_match.csv  BEN -> TEA number, with the method

Usage:
  python scripts/ingest_erate.py            # fetch + match
  python scripts/ingest_erate.py --no-fetch # re-match from existing CSVs
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from district_match import Resolver  # noqa: E402

DATA = ROOT / "data"
FRN_CSV = DATA / "usac_erate_frns.csv"
ENT_CSV = DATA / "usac_entities_tx.csv"
MATCH_CSV = DATA / "erate_district_match.csv"
CROSSWALK = DATA / "district_crosswalk.csv"

BASE = "https://opendata.usac.org/resource"
FRN_DS, ENT_DS = "qdmp-ygft", "7i5i-83qf"
PAGE = 50_000

FRN_COLS = ["funding_year", "ben", "organization_name",
            "organization_entity_type_name", "form_471_frn_status_name",
            "form_471_service_type_name", "funding_commitment_request",
            "total_authorized_disbursement", "dis_pct",
            "last_date_to_invoice", "funding_request_number",
            "application_number"]
ENT_COLS = ["entity_number", "entity_name", "entity_type",
            "parent_entity_number", "physical_county", "physical_state",
            "state_lea_code", "state_school_code",
            "nces_public_district_code", "public_school_district",
            "charter_school_district"]

# USAC applicants type their own names. These suffixes all mean "ISD"/"CISD"
# and defeat the resolver's stemmer, which knows TEA's vocabulary, not EPC's.
# Seen in the wild: "Indep School District", "Ind Sch Dist", "Independent S D",
# "Consol Indep School Dist", "School District".
_USAC_SUFFIX = re.compile(
    r"\b(cons(ol(idated)?)?\s+)?(ind(ep(endent)?)?\s+)?"
    r"(sch(ool)?\s+dist(rict)?|s\.?\s?d\.?)\b\.?",
    re.IGNORECASE)
# Spelling differences between EPC data entry and TEA's district list, applied
# ONLY here — the shared stemmer stays untouched because the bond layer's
# audited matches depend on it.
_USAC_FIXUPS = [(re.compile(p, re.IGNORECASE), r) for p, r in (
    (r"\bFort\b", "Ft"),          # TEA writes "FT SAM HOUSTON ISD"
    (r"\bBr\b", "Branch"),        # Carrollton-Farmers Br
    (r"\bSpgs\b", "Springs"),
    (r"\bMt\b", "Mount"),
)]


def usac_name(name: str) -> str:
    """'Dallas Indep School District' -> 'Dallas ISD' (CISD when the name
    carries a Consolidated marker), so the shared stemmer can do its job."""
    s = name or ""
    m = _USAC_SUFFIX.search(s)
    if m:
        kind = "CISD" if m.group(1) else "ISD"
        s = _USAC_SUFFIX.sub(kind, s).strip()
    return s


def usac_name_fixed(name: str) -> str:
    """The spelling fixups, as a RETRY only. TEA itself is inconsistent —
    'FT SAM HOUSTON ISD' but 'FORT BEND ISD' — so applying Fort->Ft
    unconditionally broke Fort Bend while fixing Ft Sam Houston. A fixup may
    add a match on the second attempt; it must never take away a first-attempt
    match."""
    s = usac_name(name)
    for pat, rep in _USAC_FIXUPS:
        s = pat.sub(rep, s)
    return s


def fetch(dataset: str, cols: list[str], where: str, out: Path,
          order: str) -> int:
    n, offset = 0, 0
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        while True:
            soql = (f"SELECT {', '.join(cols)} WHERE {where} "
                    f"ORDER BY {order} LIMIT {PAGE} OFFSET {offset}")
            url = f"{BASE}/{dataset}.json?$query=" + urllib.parse.quote(soql)
            with urllib.request.urlopen(url, timeout=120) as r:
                rows = json.loads(r.read())
            for row in rows:
                w.writerow({c: row.get(c, "") for c in cols})
            n += len(rows)
            print(f"  {dataset}: {n} rows", flush=True)
            if len(rows) < PAGE:
                return n
            offset += PAGE


def build_match() -> dict:
    xw_rows = list(csv.DictReader(CROSSWALK.open()))
    xw_numbers = {r["district_number"] for r in xw_rows}
    xw_charter = {r["district_number"]: r.get("is_charter") == "True"
                  for r in xw_rows}
    resolver = Resolver.from_crosswalk(CROSSWALK)

    ents = list(csv.DictReader(ENT_CSV.open()))
    by_num = {e["entity_number"]: e for e in ents}
    kids = defaultdict(set)
    for e in ents:
        if e["entity_type"] == "School" and e["parent_entity_number"]:
            code = (e["state_school_code"] or "").strip()
            if re.fullmatch(r"\d{9}", code):
                kids[e["parent_entity_number"]].add(code[:6])

    # The BENs that actually carry money as district applicants.
    bens = sorted({r["ben"] for r in csv.DictReader(FRN_CSV.open())
                   if r["organization_entity_type_name"] == "School District"})

    rows, tally = [], defaultdict(int)
    for ben in bens:
        e = by_num.get(ben, {})
        name = e.get("entity_name", "")
        roads: dict[str, str] = {}

        lea = (e.get("state_lea_code") or "").strip()
        if re.fullmatch(r"\d{6}", lea) and lea in xw_numbers:
            roads["lea_code"] = lea

        prefixes = {p for p in kids.get(ben, set()) if p in xw_numbers}
        if len(prefixes) == 1:
            roads["children"] = next(iter(prefixes))
            # A single coded child is thin evidence — one EPC typo attributed
            # Orenda's money to Inspire Academies through one school row.
            # Alone, the children road needs at least two coded schools
            # agreeing; with another road agreeing, one is corroboration.
            single_child = sum(
                1 for k in ents
                if k["entity_type"] == "School"
                and k["parent_entity_number"] == ben
                and re.fullmatch(r"\d{9}", (k["state_school_code"] or "").strip())
            ) < 2
            if single_child:
                roads["children_weak"] = roads.pop("children")

        # The resolver's prefix road exists for RENAMES ("KIPP Austin Public
        # Schools Inc" -> KIPP Texas). Unqualified it also matched "Houston
        # Gateway Academy" (a charter) to Houston ISD — so a prefix match is
        # accepted only when the charter flags agree: a charter organisation
        # can never be a traditional ISD, and vice versa.
        def name_road(nm: str) -> str | None:
            num, how = resolver.resolve(nm, e.get("physical_county", ""))
            if not num:
                return None
            if how in ("name+county", "name"):
                return num
            if how == "prefix+county":
                is_charter_entity = e.get("charter_school_district") == "Yes"
                if xw_charter.get(num) == is_charter_entity:
                    return num
            return None

        got = name_road(usac_name(name)) or name_road(usac_name_fixed(name))
        if got:
            roads["name"] = got
        # A weak children road only counts when something else agrees.
        if "children_weak" in roads:
            others = {v for k, v in roads.items() if k != "children_weak"}
            if roads["children_weak"] in others:
                roads["children"] = roads.pop("children_weak")
            else:
                roads.pop("children_weak")

        distinct = set(roads.values())
        if len(distinct) == 1:
            method = "+".join(sorted(roads))
            rows.append({"ben": ben, "district_number": distinct.pop(),
                         "method": method, "entity_name": name})
            tally[method] += 1
        elif len(distinct) > 1:
            # Two roads, two answers: refuse. Guessing between them is how
            # a wrong-district claim ships.
            rows.append({"ben": ben, "district_number": "",
                         "method": "CONFLICT:" + json.dumps(roads, sort_keys=True),
                         "entity_name": name})
            tally["conflict"] += 1
        else:
            rows.append({"ben": ben, "district_number": "",
                         "method": "unmatched", "entity_name": name})
            tally["unmatched"] += 1

    with MATCH_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["ben", "district_number",
                                           "method", "entity_name"])
        w.writeheader()
        w.writerows(rows)

    matched = sum(1 for r in rows if r["district_number"])
    assert matched + tally["conflict"] + tally["unmatched"] == len(bens), \
        "match accounting does not balance"
    print(f"\nBEN->TEA: {matched}/{len(bens)} matched "
          f"({tally['conflict']} conflicts refused, "
          f"{tally['unmatched']} unmatched)")
    for k in sorted(tally):
        print(f"  {k}: {tally[k]}")
    return {"bens": len(bens), "matched": matched, **tally}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-fetch", action="store_true",
                    help="skip the network; rebuild the match from local CSVs")
    args = ap.parse_args(argv)
    if not args.no_fetch:
        print("fetching FRN rows (state=TX) ...")
        fetch(FRN_DS, FRN_COLS, "state='TX'", FRN_CSV,
              "funding_request_number")
        print("fetching entity rows (physical_state=TX) ...")
        fetch(ENT_DS, ENT_COLS, "physical_state='TX'", ENT_CSV,
              "entity_number")
    build_match()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
