"""What Texas school districts still OWE, from the board that counts it.

The gap this fills
------------------
Every debt figure on this site until now came from TEA's PEIMS file, and PEIMS
reports debt SERVICE — the cash a district paid out in a year. That is a flow.
It answers "what did debt cost you last year" and cannot answer "how much is
still owed", "over how long", or "how much of what is owed is interest that
nobody has paid yet". The stock was missing entirely.

The Texas Bond Review Board keeps the stock. It publishes, per issuer and per
fiscal year, principal and interest still outstanding, split by the two kinds of
bond a district can sell:

    CIB   current interest bond — interest is paid twice a year, as you would
          expect debt to work.
    CAB   capital appreciation bond — NOTHING is paid until maturity. Interest
          compounds silently for the whole life of the bond and the entire
          amount lands at the end.

Why the CAB split is the point
------------------------------
A CAB lets a district build now and put every dollar of cost past the term of
everyone who approved it. The arithmetic is unforgiving: deferring all interest
for decades routinely produces repayment of four to ten times the amount
borrowed. Texas restricted the practice in 2015 — House Bill 114 capped the
ratio at 4:1 and the term at 25 years — but bonds sold before that are still
outstanding, and the deferred interest on them is still owed.

That number does not appear in PEIMS, on a tax bill, or in the operating budget.
It appears here, and nowhere else on this site until now.

First-party, deliberately
-------------------------
This data is also carried by a commercial aggregator, which is how it was found.
It is not ingested from there. The whole provenance chain in this repo is
"publisher file -> hashed local copy -> committed fixture -> diffed artefact ->
tested page", and a re-publisher breaks it at the first link. Both endpoints
used here belong to the Board:

    https://data.brb.texas.gov/main_search.json            the issuer index
    https://data.brb.texas.gov/charts/local/isd/{id}/cab_cib_debtoutstanding_longitudinal.csv

Joining to TEA numbers
----------------------
The Board identifies issuers by its own id and a name; TEA uses a six-digit
number. The Board's index carries no county, and Texas has thirteen colliding
district names, so name alone would silently mis-attribute debt to the wrong
district — the exact failure `scripts/district_match.py` was written for. The
county comes from the Board's own bond-election file, which lists both, so the
join stays inside one publisher. Anything still ambiguous is refused and
counted, never guessed.

    python scripts/ingest_brb_debt.py
    python scripts/ingest_brb_debt.py --limit 25      # a quick sample

Exits non-zero if too few issuers resolve, so a silent collapse of the join
cannot be mistaken for a small debt load.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from district_match import Resolver  # noqa: E402

BASE = "https://data.brb.texas.gov"
INDEX = f"{BASE}/main_search.json"
SERIES = BASE + "/charts/local/isd/{brb_id}/cab_cib_debtoutstanding_longitudinal.csv"
UA = "txisd-brb-ingest/1.0 (+https://txisd.dev/sources)"
TIMEOUT = 45
WORKERS = 8            # polite against a small agency's static host
RETRIES = 3

OUT = ROOT / "data/brb_debt_outstanding.csv"
COLUMNS = ["brb_id", "issuer_name", "district_number", "match_method", "fiscal_year",
           "cib_principal_outstanding", "cib_interest_outstanding",
           "cab_principal_outstanding", "cab_interest_outstanding"]

# The Board listed 1,038 school districts when this was written. A large drop
# means the index moved or the fetch failed, and writing it would look like
# districts had paid off their debt.
MIN_ISSUERS = 900
MIN_RESOLVED_PCT = 90.0
# A missing series reads as "this district carries no Board-tracked debt", so a
# host-wide failure returning 403 for everything would publish as Texas having
# paid off its schools. 178 of 1,038 issuers genuinely had no series when this
# was written; well above that means the endpoint moved, not that debt vanished.
MAX_ABSENT_PCT = 35.0

_ctx = ssl.create_default_context()


def get(url: str, binary: bool = False):
    last = None
    for attempt in range(RETRIES):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ctx) as r:
                raw = r.read()
                return raw if binary else raw.decode("utf-8-sig", "replace")
        except urllib.error.HTTPError as e:
            # This host is object storage behind a CDN: a key that does not
            # exist comes back 403, not 404 (requesting a directory does the
            # same). Verified by hand — Allison ISD's own issuer page carries
            # no CSV reference at all, and twenty rapid requests for a key that
            # does exist all returned 200, so 403 is absence and not throttling.
            # Conflating "forbidden" with "absent" is normally a bad idea, so
            # MAX_ABSENT_PCT below refuses the whole run if it starts happening
            # at scale.
            if e.code in (403, 404):
                return None
            last = e
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"{url}: {type(last).__name__}: {last}")


# The Board disambiguates its thirteen colliding district names with a
# parenthesised or bracketed hint: "Highland Park ISD (Dallas)",
# "Highland Park ISD [Potter]". That hint is the county we otherwise lack, so
# it is pulled out rather than thrown away with the rest of the punctuation.
_HINT = re.compile(r"[(\[]([^)\]]+)[)\]]\s*$")


def split_hint(name: str) -> tuple[str, str]:
    """'Highland Park ISD (Dallas)' -> ('Highland Park ISD', 'Dallas')."""
    m = _HINT.search(name)
    return (_HINT.sub("", name).strip(), m.group(1).strip()) if m else (name, "")


def issuers() -> dict[str, list[str]]:
    """brb_id -> every name the Board lists it under.

    Keyed by ID, not by name, and this is not a stylistic preference. The
    Board's index carries brb_id 1746 TWICE, once as "Highland Park ISD
    (Dallas)" and once as "Highland Park ISD [Amarillo]", serving byte-identical
    data both times — and those two labels name different counties, so one of
    them is simply wrong upstream (1747 is the Amarillo/Potter district).
    Treating names as identities would have fetched the same series twice and
    added $406.5m of one district's debt to the statewide total a second time.

    The id is the identity. The names are just labels, and all of them are kept
    because between them they usually contain the county hint that resolves the
    district.
    """
    doc = json.loads(get(INDEX))
    rows = doc if isinstance(doc, list) else next(iter(doc.values()))
    out: dict[str, list[str]] = {}
    for r in rows:
        if r.get("government_type") != "ISD":
            continue
        # "/local/isd/577.html" -> "577". The number in the page URL is the same
        # id the chart-data paths use.
        stem = str(r.get("url", "")).rsplit("/", 1)[-1].split(".")[0]
        name = str(r.get("issuer_name") or "").strip()
        if stem.isdigit() and name and name not in out.setdefault(stem, []):
            out[stem].append(name)
    return dict(sorted(out.items(), key=lambda kv: int(kv[0])))


def series(brb_id: str) -> list[dict]:
    body = get(SERIES.format(brb_id=brb_id))
    if not body:
        return []
    return list(csv.DictReader(io.StringIO(body)))


def county_by_name(bonds: Path) -> dict[str, str]:
    """Issuer name -> county, taken from the Board's own election file.

    Staying inside one publisher matters here: a county borrowed from a third
    file could disagree with the Board about which Wylie ISD is which, and the
    join would be wrong in a way nothing downstream could detect.
    """
    if not bonds.exists():
        return {}
    with bonds.open(encoding="utf-8-sig", newline="") as fh:
        return {(r.get("Issuer") or "").strip().upper(): (r.get("County") or "").strip()
                for r in csv.DictReader(fh) if (r.get("Issuer") or "").strip()}


def resolve_issuer(labels: list[str], resolver, counties: dict[str, str]):
    """Settle one Board id to one TEA district number, or refuse.

    An id can carry several labels, and each label can offer a county three
    ways: a bracketed hint the Board wrote, the county its bond elections were
    held in, or nothing. Every combination is tried, most trustworthy first,
    and the DISTINCT districts they land on are collected.

    One distinct answer is the answer, however many routes reached it. More
    than one means the Board's own labels disagree about which district this
    is, and a debt figure attached to the wrong district is the worst error
    this project can make — so that refuses rather than picking a winner.
    """
    hits: dict[str, str] = {}                    # district_number -> method used
    for label in labels:
        clean, hint = split_hint(label)
        # Most trustworthy first. Candidates with no county are dropped here
        # and only the final fallback keeps one, because a lookup with an empty
        # county still "succeeds" against a statewide-unique name — which would
        # short-circuit the loop and record the weaker `name` method even when
        # a county was available. That is not a wrong answer, but it is a worse
        # recorded provenance, and this file publishes how each row was matched.
        candidates = [c for c in (
            (clean, hint),                              # the Board's own disambiguator
            (clean, counties.get(clean.upper(), "")),   # county of its bond elections
            (label, counties.get(label.upper(), "")),
        ) if c[1]]
        candidates.append((clean, ""))                  # unique statewide, or nothing
        for name, county in candidates:
            num_, method = resolver.resolve(name, county)
            if num_:
                hits.setdefault(num_, method)
                break
    if not hits:
        return None, "unmatched", labels[0]
    if len(hits) > 1:
        return None, "ambiguous", labels[0]
    number, method = next(iter(hits.items()))
    return number, method, split_hint(labels[0])[0]


def num(v) -> float:
    try:
        return float(str(v).replace(",", "").replace("$", "") or 0)
    except ValueError:
        return 0.0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--finance", type=Path, default=ROOT / "data/texas_finance_clean.csv")
    ap.add_argument("--snapshot", type=Path, default=ROOT / "data/snapshot_all.csv")
    ap.add_argument("--bonds", type=Path, default=ROOT / "data/texas_bond_elections.csv")
    ap.add_argument("--limit", type=int, default=0, help="sample N issuers (testing)")
    args = ap.parse_args()

    print(f"reading the Bond Review Board issuer index\n  {INDEX}")
    idx = issuers()
    aliased = {k: v for k, v in idx.items() if len(v) > 1}
    print(f"  {len(idx):,} distinct school-district issuers")
    if aliased:
        print(f"  {len(aliased)} listed under more than one name — deduplicated by id, "
              f"which is what stops the same debt being counted twice:")
        for k, v in aliased.items():
            print(f"      {k}: {' / '.join(v)}")
    if not args.limit and len(idx) < MIN_ISSUERS:
        raise SystemExit(f"refusing: only {len(idx)} issuers, expected >= {MIN_ISSUERS}")
    if args.limit:
        idx = dict(list(idx.items())[:args.limit])

    # The resolver is built exactly as the bond layer builds it, so a district
    # resolves the same way here as it does there.
    import pandas as pd  # local: this script is the only place pandas is needed
    from build_bond_data import county_of_code
    fin = pd.read_csv(args.finance, dtype={"district_number": str}, low_memory=False)
    names = fin.drop_duplicates("district_number")[["district_number", "district_name"]]
    resolver = Resolver.from_tea(list(zip(names.district_number, names.district_name)),
                                 county_of_code(args.snapshot))
    counties = county_by_name(args.bonds)

    ids = list(idx)
    print(f"fetching {len(ids):,} longitudinal debt series, {WORKERS} at a time")
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        fetched = list(pool.map(series, ids))

    rows, methods, unresolved, no_series = [], Counter(), [], []
    for brb_id, recs in zip(ids, fetched):
        labels = idx[brb_id]
        if not recs:
            no_series.append(labels[0])
            continue
        number, method, name = resolve_issuer(labels, resolver, counties)
        methods[method] += 1
        if number is None:
            unresolved.append(f"{labels[0]} [{method}]")
        for r in recs:
            rows.append({
                "brb_id": brb_id, "issuer_name": name,
                "district_number": number or "", "match_method": method,
                "fiscal_year": str(r.get("FiscalYear") or "").strip(),
                "cib_principal_outstanding": num(r.get("CIBPrincipalOutstanding")),
                "cib_interest_outstanding": num(r.get("CIBInterestOutstanding")),
                "cab_principal_outstanding": num(r.get("CABPrincipalOutstanding")),
                "cab_interest_outstanding": num(r.get("CABInterestOutstanding")),
            })

    with_series = len(idx) - len(no_series)
    resolved_pct = 100 * (with_series - len(unresolved)) / with_series if with_series else 0
    print(f"\n  issuers with a series      {with_series:,} of {len(idx):,}")
    print(f"  observations               {len(rows):,}")
    print(f"  resolved to a TEA number   {with_series - len(unresolved):,} ({resolved_pct:.1f}%)")
    for m, c in methods.most_common():
        print(f"      {m:<16}{c:>6,}")
    if unresolved:
        print(f"  UNRESOLVED ({len(unresolved)}): {', '.join(sorted(unresolved)[:12])}"
              + (" ..." if len(unresolved) > 12 else ""))
    if no_series:
        print(f"  no debt series published ({len(no_series)}) — these carry no BRB-tracked debt")

    absent_pct = 100 * len(no_series) / len(idx) if idx else 0
    if not args.limit and absent_pct > MAX_ABSENT_PCT:
        raise SystemExit(
            f"refusing to write: {absent_pct:.1f}% of issuers returned no series "
            f"(limit {MAX_ABSENT_PCT}%). That is an endpoint failure reading as "
            f"debt-free districts, not a finding.")
    if not args.limit and resolved_pct < MIN_RESOLVED_PCT:
        raise SystemExit(
            f"refusing to write: only {resolved_pct:.1f}% resolved to a TEA number "
            f"(need {MIN_RESOLVED_PCT}%). A collapsed join would read as low debt.")

    rows.sort(key=lambda r: (r["issuer_name"], r["fiscal_year"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {args.out.relative_to(ROOT)}  ({args.out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
