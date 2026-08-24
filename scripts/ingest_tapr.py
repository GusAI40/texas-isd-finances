#!/usr/bin/env python3
"""Pull TAPR data files straight from TEA's SAS broker.

`CLAUDE.md` recorded this download as blocked: "TEA SAS broker CGI form POST,
no login — old DownloadData.html is gone; needs a session to map form params".
This maps them. There is no login and no session — the broker is a stateless
four-step wizard, and every step's inputs are in the previous step's HTML.

    step 1  tapr_dd_download.html?year=YYYY   ccyy + tapr (which universe)
    step 2  prgopt=.../dd_tapr_step_6.sas     dsname (which dataset)
    step 3  prgopt=.../dd_tapr_step_7.sas     key[] + var_type[] + datafmt
    ->      a CSV

**`var_type` is the part that costs an afternoon.** STAAR datasets carry a
third checkbox group — N/D/R, numerator, denominator and rate — that the staff
datasets do not. Omit it and the broker returns HTTP 200 with a perfectly
well-formed CSV containing nothing but campus names and district names. No
error, no warning, no clue: just four columns where 949 were expected. The
field groups are therefore always read from the live form rather than
hard-coded, and the download REFUSES a file that came back with no measures.

Datasets worth knowing about (`--list` prints what the year actually offers):
    REF     reference: enrolment, demographics
    STAF    staff: teacher FTE, experience, tenure, degrees, salary
    STAAR_ALL   all grades, every subject and student group
    STAAR_GR3..GR8, STAAR_GR38, STAAR_EOC   by grade / end-of-course

Usage:
    python scripts/ingest_tapr.py --download
    python scripts/ingest_tapr.py --list
    python scripts/ingest_tapr.py --download --dataset STAAR_GR4 --level d
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BROKER = "https://rptsvr1.tea.texas.gov/cgi/sas/broker"
UA = {"User-Agent": "txisd-ingest/1.0 (+https://txisd.dev)",
      "Content-Type": "application/x-www-form-urlencoded"}
YEAR = 2025

# The default pull: what the published layers actually read.
WANTED = [
    ("c", "STAAR_ALL", "data/tapr_campus_staar_2025.csv"),
    ("d", "STAAR_ALL", "data/tapr_district_staar_2025.csv"),
    ("c", "STAF", "data/tapr_campus_staff_2025.csv"),
]


def _post(url: str, fields: dict, timeout: int = 300) -> bytes:
    body = urllib.parse.urlencode(fields, doseq=True).encode()
    req = urllib.request.Request(url, data=body, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _base(level: str, year: int) -> dict:
    return {"_service": "marykay", "_program": "perfrept.perfmast.sas",
            "_debug": "0", "tapr": f"all_{level}", "ccyy": str(year),
            "sumlev": "C" if level == "c" else "D",
            "level": "Campus" if level == "c" else "District", "id": ""}


def datasets(level: str, year: int) -> list[str]:
    """What this year actually offers, read from the form rather than assumed.

    The dataset radios are on the FIRST page (prgopt=dd_tapr.sas), not on the
    step-6 page — asking step 6 for them returns the literal SAS macro
    `&dsname.` unresolved, which is a reminder that this is a template engine
    answering questions it was not asked.
    """
    f = _base(level, year) | {"prgopt": "reports/tapr/dd/dd_tapr.sas"}
    html = _post(BROKER, f, timeout=180).decode("iso-8859-1")
    found = re.findall(r"""name=['"]dsname['"]\s+value=['"]([A-Z0-9_]+)['"]""", html)
    return list(dict.fromkeys(found))


def field_groups(level: str, dataset: str, year: int) -> tuple[list[str], list[str]]:
    """The checkbox groups for one dataset: (key[], var_type[]).

    Read live every time. Hard-coding these would break silently the year TEA
    adds a field group, in the same shape as the var_type bug: a 200 and a
    short file.
    """
    f = _base(level, year) | {
        "step": "3", "bylev": "All Campuses" if level == "c" else "All Districts",
        "prgopt": "reports/tapr/dd/dd_tapr_step_6.sas", "dsname": dataset}
    html = _post(BROKER, f, timeout=180).decode("iso-8859-1")
    return (re.findall(r'name="key"[^>]*value="([^"]+)"', html),
            re.findall(r'name="var_type"[^>]*value="([^"]+)"', html))


def fetch(level: str, dataset: str, year: int) -> bytes:
    keys, var_types = field_groups(level, dataset, year)
    if not keys:
        raise RuntimeError(
            f"{dataset} at level {level}: the form offered no field groups. "
            f"Either the dataset name is wrong for {year}, or TEA changed the "
            f"wizard — check tapr_dd_download.html?year={year} by hand.")
    f = _base(level, year) | {
        "prgopt": "reports/tapr/dd/dd_tapr_step_7.sas",
        "dsname": dataset, "datafmt": "csv", "key": keys}
    if var_types:
        f["var_type"] = var_types
    data = _post(BROKER + "/", f)

    # The failure this guard exists for: omitting var_type returns 200 and a
    # valid CSV holding only the identifier columns. A short file must never be
    # mistaken for a dataset that happens to be thin.
    header = data.split(b"\n", 1)[0].decode("iso-8859-1")
    columns = header.count('","') + 1
    if columns <= 6:
        raise RuntimeError(
            f"{dataset} at level {level} came back with only {columns} columns "
            f"({header[:120]}). That is the identifier block and no measures — "
            f"the request was accepted and returned nothing. {len(keys)} key "
            f"groups and {len(var_types)} var_types were sent.")
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dataset")
    ap.add_argument("--level", choices=["c", "d"], default="c")
    ap.add_argument("--year", type=int, default=YEAR)
    ap.add_argument("--out")
    args = ap.parse_args()

    if args.list:
        for lev in ("c", "d"):
            print(f"{'campus' if lev == 'c' else 'district'} datasets for "
                  f"{args.year}: {', '.join(datasets(lev, args.year))}")
        return 0

    if args.dataset:
        jobs = [(args.level, args.dataset,
                 args.out or f"data/tapr_{args.level}_{args.dataset.lower()}_"
                             f"{args.year}.csv")]
    elif args.download:
        jobs = WANTED
    else:
        ap.error("pass --download, --list, or --dataset")
        return 2

    for level, dataset, out in jobs:
        path = ROOT / out
        try:
            data = fetch(level, dataset, args.year)
        except Exception as e:  # noqa: BLE001 — reported, never swallowed
            print(f"  FAILED {dataset} ({level}): {e}", file=sys.stderr)
            return 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        cols = data.split(b"\n", 1)[0].count(b'","') + 1
        print(f"  wrote {out} — {len(data):,} bytes, {data.count(chr(10).encode()):,} "
              f"rows, {cols} columns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
