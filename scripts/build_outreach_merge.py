"""One row per district: superintendent, official email, and a link to THEIR page.

Feeds a mail merge (Gmail/Outlook/YAMM all take a CSV) so each superintendent
opens txisd.dev/?d=<their district> — their own name in the headline, their own
numbers — rather than a generic homepage.

Where the contacts come from
----------------------------
TEA's own directory. AskTED is the agency's official record of districts and
their administrators, republished by TEA on the state open-data portal
(data.texas.gov/d/hzek-udky, attribution "Research and Analysis Division at
Texas Education Agency"). Superintendent names and district email addresses
here are public records of public officials, from the publisher itself — the
same first-party standard as every other source in this repo.

The output is written to data/ and data/*.csv is gitignored ON PURPOSE. A
contact list has no business being committed to a public repository, even one
assembled from public records. The script is the artefact; the list is
generated fresh when needed, which also means it picks up TEA's directory
updates instead of freezing a stale copy.

Frame honesty travels into the email
------------------------------------
Each row carries a `hook` sentence built under the same rules as the site
(tests/test_framing.py): where construction and debt are a fifth or more of a
district's outlay, the all-funds figure is never given without the operating
figure — "spends $31,704 per student, $10,357 of it running schools and the
rest building them." Argyle's superintendent should recognise their district in
the email, not brace at it.

`greeting` is a BEST-EFFORT surname ("Dr. Satterwhite") extracted from the
as-published name. Names resist parsing — suffixes, hyphens, compound
surnames — so the as-published form ships alongside and the merge should be
spot-checked before sending. When in doubt the template's safe fallback is
"Dear Superintendent,".

    python scripts/build_outreach_merge.py
    python scripts/build_outreach_merge.py --include-charters
"""
from __future__ import annotations

import argparse
import csv
import json
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src import format as fmt  # noqa: E402

ASKTED = "https://data.texas.gov/resource/hzek-udky.json"
SITE = "https://txisd.dev"
UA = "txisd-outreach-merge/1.0 (+https://txisd.dev/sources)"
PAGE = 5000

# Honorifics kept for the greeting; suffixes that are not a surname.
_HONORIFICS = {"DR", "MR", "MRS", "MS"}
_SUFFIXES = {"JR", "SR", "II", "III", "IV", "V", "PHD", "EDD"}


def fetch_askted() -> dict[str, dict]:
    """district_number -> directory row, deduped from AskTED's campus rows.

    AskTED repeats the district block on every campus row, and prefixes numeric
    codes with an apostrophe so spreadsheets keep leading zeros. Both quirks
    are theirs to keep and ours to strip.
    """
    ctx = ssl.create_default_context()
    out: dict[str, dict] = {}
    offset = 0
    while True:
        q = urllib.parse.urlencode({
            "$select": ("district_number,district_name,county_name,district_type,"
                        "district_superintendent,district_email_address,"
                        "district_web_page_address,esc_region_served"),
            "$limit": PAGE, "$offset": offset})
        req = urllib.request.Request(f"{ASKTED}?{q}", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
            page = json.load(r)
        for row in page:
            num = str(row.get("district_number", "")).lstrip("'").strip()
            if len(num) == 6 and num.isdigit():
                out.setdefault(num, row)
        if len(page) < PAGE:
            return out
        offset += PAGE


_HONORIFIC_STYLE = {"DR": "Dr.", "MR": "Mr.", "MRS": "Mrs.", "MS": "Ms."}


def greeting_from(name: str) -> str:
    """'DR JOE E SATTERWHITE III' -> 'Dr. Satterwhite'. Best effort, reviewed
    by a human before anything is sent — see the module docstring.

    Only an honorific TEA actually published is used; a name without one gets
    "Superintendent Briggs", never a guessed "Mr./Ms." — the directory doesn't
    say and neither should we. A bare surname ("Dear Briggs,") is not a
    greeting, which is what the first draft produced.
    """
    words = [w for w in str(name or "").replace(".", "").split() if w]
    if not words:
        return "Superintendent"
    hon = _HONORIFIC_STYLE.get(words[0].upper(), "")
    core = [w for w in words if w.upper() not in _HONORIFICS | _SUFFIXES]
    if not core:
        return "Superintendent"
    surname = fmt.district_name(core[-1]) or core[-1].title()
    return f"{hon} {surname}".strip() if hon else f"Superintendent {surname}"


def finance_frames() -> dict[str, dict]:
    """Per-district figures with the frame attached, from the raw state file —
    the same columns the Argyle audit used."""
    import pandas as pd
    f = pd.read_csv(ROOT / "data/texas_finance_clean.csv",
                    dtype={"district_number": str}, low_memory=False)
    f = f[(f.year == f.year.max()) & (f.fall_survey_enrollment > 0)]
    out = {}
    for r in f.itertuples():
        e = r.fall_survey_enrollment
        tot = r.all_funds_total_disbursements
        ops = r.all_funds_total_operating_expenditures_by_obj
        if not (e and tot and ops):
            continue
        share = 1 - ops / tot
        out[r.district_number] = {
            "year": int(r.year), "enrollment": int(e),
            "all_funds_per_student": round(tot / e),
            "operating_per_student": round(ops / e),
            "construction_debt_share_pct": round(100 * share),
        }
    return out


def hook(name: str, fr: dict | None) -> str:
    """One frame-honest sentence for the email body. Never an all-funds figure
    without the operating figure where the gap is material."""
    if not fr:
        return (f"Seventeen years of {name}'s finances, results, bonds and debt "
                f"are on the page — every number linked to the state file it "
                f"came from.")
    a, o = fr["all_funds_per_student"], fr["operating_per_student"]
    if fr["construction_debt_share_pct"] >= 20:
        return (f"In fiscal {fr['year']}, {name} spent {fmt.usd(a)} per student "
                f"all-funds — {fmt.usd(o)} of it running schools and the rest "
                f"building them, which the page says plainly rather than "
                f"calling it overspending.")
    return (f"In fiscal {fr['year']}, {name} spent {fmt.usd(o)} per student on "
            f"operations, with every line traceable to TEA's own file.")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "data/outreach_merge.csv")
    ap.add_argument("--include-charters", action="store_true",
                    help="charters have superintendents too; off by default "
                         "because the draft email speaks to taxing ISDs")
    args = ap.parse_args()

    print("fetching TEA's directory (AskTED) from data.texas.gov/d/hzek-udky")
    directory = fetch_askted()
    print(f"  {len(directory):,} districts in the directory")

    crosswalk = {r["district_number"]: r for r in csv.DictReader(
        (ROOT / "data/district_crosswalk.csv").open(encoding="utf-8", newline=""))}
    frames = finance_frames()

    rows, skipped_charter, missing_contact = [], 0, []
    for num, x in sorted(crosswalk.items()):
        is_charter = x["is_charter"].lower() == "true"
        if is_charter and not args.include_charters:
            skipped_charter += 1
            continue
        d = directory.get(num)
        name = fmt.district_name(x["district_name"])
        if not d or not (d.get("district_email_address") or "").strip():
            missing_contact.append(name)
            continue
        fr = frames.get(num)
        rows.append({
            "district_number": num,
            "district_name": name,
            "county": x["county"],
            "esc_region": str(d.get("esc_region_served", "")).lstrip("'"),
            "superintendent_as_published": d.get("district_superintendent", ""),
            "greeting": greeting_from(d.get("district_superintendent", "")),
            "email": d.get("district_email_address", "").strip().lower(),
            "district_website": d.get("district_web_page_address", ""),
            "deep_link": f"{SITE}/?d={num}",
            "enrollment": fr["enrollment"] if fr else "",
            "operating_per_student": fr["operating_per_student"] if fr else "",
            "all_funds_per_student": fr["all_funds_per_student"] if fr else "",
            "construction_debt_share_pct":
                fr["construction_debt_share_pct"] if fr else "",
            "hook": hook(name, fr),
            "subject": (f"Every number Texas publishes about {name} — "
                        f"in one place, with receipts"),
        })

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print(f"\nwrote {args.out.relative_to(ROOT)} — {len(rows):,} districts "
          f"({args.out.stat().st_size:,} bytes; gitignored, as a contact list "
          f"should be)")
    if skipped_charter:
        print(f"  charters skipped: {skipped_charter} (rerun with "
              f"--include-charters to add them)")
    if missing_contact:
        print(f"  no directory contact for {len(missing_contact)}: "
              f"{', '.join(missing_contact[:5])}"
              + (" ..." if len(missing_contact) > 5 else ""))
    print("\nsample:")
    for r in rows[:3]:
        print(f"  {r['greeting']:<22} {r['email']:<38} {r['deep_link']}")
        print(f"    {r['hook'][:110]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
