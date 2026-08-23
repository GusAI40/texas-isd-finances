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


def finance_frames_from_api(numbers: list[str], base: str = SITE) -> dict[str, dict]:
    """The same per-district figures, from the live site's public API.

    Why this exists: the CSV below is gitignored and derived from an ~18MB TEA
    workbook, so rebuilding the mailing list on a fresh machine meant a manual
    download before anything else could run — and rebuilding it is now the
    step between "the outreach machine is armed" and "a wave can be queued".
    /district/{n}/summary is public, needs no credential, and serves the same
    four numbers this function has always used.

    It must be the API and not static/economics_data.json, which is committed
    and looks like it would do: that artefact's `total_per_student` is
    operating + debt and EXCLUDES construction, so it disagrees with all-funds
    by design (Ricardo ISD: $13,582 vs $18,290). The hook's whole job is to
    chain the all-funds figure to the operating one wherever construction is a
    material share — computing that from a figure with construction removed
    would invert the sentence it exists to make honest.
    """
    import urllib.request

    out: dict[str, dict] = {}
    failed: list[str] = []
    for i, num in enumerate(numbers, 1):
        rows = None
        # One retry: across ~1,000 sequential calls a single dropped
        # connection is ordinary, and it must not be mistaken for a district
        # the state has no figures for. What survives a retry is reported.
        for attempt in (1, 2):
            try:
                req = urllib.request.Request(
                    f"{base}/district/{num}/summary",
                    headers={"User-Agent":
                             "txisd-outreach/1.0 (+https://txisd.dev)"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    rows = json.load(r)
                break
            except Exception:  # noqa: BLE001 — retried, then reported
                if attempt == 2:
                    failed.append(num)
        if not rows:
            continue
        # By year, not by position: `rows[-1]` silently prices every hook from
        # fiscal 2009 the day the endpoint starts serving newest-first.
        rec = (max(rows, key=lambda r: r.get("year") or 0)
               if isinstance(rows, list) else rows)
        e, tot, ops = (rec.get("enrollment"), rec.get("total_spend"),
                       rec.get("operating_spend"))
        per = rec.get("spend_per_student")
        # A district the PAGE cannot price is one the email must not price
        # either — recomputing here is what reintroduces the one-dollar
        # disagreement this function exists to avoid.
        if per is None or not e or e <= 0 or not tot or not ops:
            continue
        out[num] = {
            "year": int(rec["year"]), "enrollment": int(e),
            "all_funds_per_student": round(per),
            "operating_per_student": round(ops / e),
            "construction_debt_share_pct": round(100 * (1 - ops / tot)),
        }
        if i % 100 == 0:
            print(f"  {i}/{len(numbers)} districts priced from the API")
    if failed:
        # Refuse rather than write a mailing list quietly short of hooks: a
        # missing hook that came from a dropped connection is indistinguishable
        # in the output from a district the state genuinely has no figures for,
        # and this file is the input to mass email.
        raise RuntimeError(
            f"{len(failed)} districts could not be priced after a retry "
            f"({', '.join(failed[:8])}{'…' if len(failed) > 8 else ''}). "
            f"Re-run — a merge file short of hooks cannot be told apart from "
            f"one whose districts genuinely have no figures.")
    return out


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


def load_insights() -> tuple[dict, dict, dict, dict]:
    """The committed artefacts the site itself serves — bonds, debt, trends —
    plus the statewide trend line to compare against. Same files, same
    numbers: an email insight can never disagree with the page it links to."""
    bonds = json.loads((ROOT / "static/bond_data.json").read_text())
    debt = json.loads((ROOT / "static/debt_data.json").read_text())
    trends = json.loads((ROOT / "static/trend_data.json").read_text())
    return (bonds["districts"], debt["districts"], trends["districts"],
            trends["statewide"]["change"])


def insight_bonds(num: str, name: str, bonds: dict) -> str:
    """The ballot record, from the Bond Review Board's own file."""
    d = bonds.get(num)
    if not d or not d.get("elections"):
        return (f"The Bond Review Board's statewide record (1958–2026) shows "
                f"no school bond election for {name} — itself worth knowing.")
    t = d["totals"]
    last = d["elections"][-1]
    verdict = "passed" if last["passed"] else "was defeated"
    return (f"Voters in {name} have decided {t['props']} bond propositions "
            f"since {t['first_year']} and approved {t['passed']} of them. The "
            f"most recent — {fmt.big(last['amount'])} on {last['date']} — "
            f"{verdict}.")


def insight_debt(num: str, name: str, debt: dict) -> str:
    """The stock, not the flow — and it says so."""
    d = debt.get(num)
    if not d:
        return (f"The Bond Review Board's issuer record shows no outstanding "
                f"bond debt for {name}.")
    return (f"As of fiscal 2025, {name} owes {fmt.big(d['total'])} on bonds "
            f"already sold — {fmt.usd(d['per_student'])} per student enrolled "
            f"today, {d['interest_share_pct']}% of it interest not yet paid. "
            f"On current schedules it clears in {d['clears_in']}.")


def insight_trend(num: str, name: str, trends: dict, sw_change: dict) -> str:
    """Instruction's share of the operating dollar, district vs the state's
    own line — the site's headline trend, personalised."""
    d = trends.get(num)
    ch = (d or {}).get("change", {}).get("instruction_share")
    sw = sw_change["instruction_share"]
    if not ch or ch.get("first") is None or ch.get("last") is None:
        return ""
    direction = "rose" if ch["change"] > 0 else ("fell" if ch["change"] < 0
                                                 else "held")
    return (f"Instruction's share of {name}'s operating dollar {direction} "
            f"from {ch['first']}% ({ch['first_year']}) to {ch['last']}% "
            f"({ch['last_year']}). Statewide it fell {sw['first']}% → "
            f"{sw['last']}% over the same years.")


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
    ap.add_argument("--finance-from-api", action="store_true",
                    help="price districts from the live public API instead of "
                         "the gitignored TEA CSV — no download, no credential; "
                         "the default when the CSV is absent")
    ap.add_argument("--include-charters", action="store_true",
                    help="charters have superintendents too; off by default "
                         "because the draft email speaks to taxing ISDs")
    args = ap.parse_args()

    print("fetching TEA's directory (AskTED) from data.texas.gov/d/hzek-udky")
    directory = fetch_askted()
    print(f"  {len(directory):,} districts in the directory")

    crosswalk = {r["district_number"]: r for r in csv.DictReader(
        (ROOT / "data/district_crosswalk.csv").open(encoding="utf-8", newline=""))}
    # The CSV stays the default where it exists (offline, and no 1,000 HTTP
    # calls); the API is the fallback that makes a fresh machine work at all.
    csv_present = (ROOT / "data/texas_finance_clean.csv").exists()
    if not csv_present and not args.finance_from_api:
        # Explicit, not automatic: silently changing where the money figures
        # come from is how someone queues a wave believing they are on the
        # CSV path. The flag is one word and makes the choice visible in the
        # command that ran.
        print("data/texas_finance_clean.csv is absent. Either restore it, or "
              "pass --finance-from-api to price districts from the live "
              "public API (no download, no credential).", file=sys.stderr)
        return 1
    if args.finance_from_api:
        wanted = [n for n, x in sorted(crosswalk.items())
                  if args.include_charters or x["is_charter"].lower() != "true"]
        frames = finance_frames_from_api(wanted)
    else:
        frames = finance_frames()
    print(f"  priced {len(frames):,} districts")
    bonds, debt, trends, sw_change = load_insights()

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
            "insight_bonds": insight_bonds(num, name, bonds),
            "insight_debt": insight_debt(num, name, debt),
            "insight_trend": insight_trend(num, name, trends, sw_change),
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
