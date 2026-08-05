#!/usr/bin/env python3
"""Build the committed ISD briefing snapshot (static/isd_briefing.json).

The snapshot is what /briefing and /feed serve at Tier 1 (no database), so it
must carry the same shape a live daily run produces — including the house-voice
`hook`, `beat`, and `receipts` fields. Regenerate it whenever the pipeline or
the sample set changes:

    python scripts/build_isd_briefing.py

The TEA items are REAL first-hand press releases from tea.texas.gov (tier 1):
the Beaumont / Fort Worth / Lake Worth / Connally board-of-managers
appointments and the Houston board changes. The Fort Worth bond item and its
extracted-facts row are illustrative — a live run replaces all of it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import isd_intel as I  # noqa: E402

RUN_DATE = "2026-01-10"

# The real TEA newsroom releases (tier 1) plus one illustrative bond item.
SAMPLE = [
    I.NewsItem(
        "Fort Worth ISD calls bond election for new schools",
        "Trustees for Fort Worth Independent School District placed a bond on the ballot.",
        "https://www.star-telegram.com/", "Star-Telegram", RUN_DATE, source_tier=2),
    I.NewsItem(
        "Texas Education Agency Appoints Board of Managers and New Superintendent for Connally ISD",
        "", "https://tea.texas.gov/about-tea/newsroom/2026/tea-appoints-board-of-managers-connally-isd",
        "Texas Education Agency", RUN_DATE, source_tier=1),
    I.NewsItem(
        "Texas Education Agency Appoints Beaumont ISD Board of Managers and Superintendent",
        "", "https://tea.texas.gov/about-tea/newsroom/2026/tea-appoints-beaumont-isd-board-of-managers",
        "Texas Education Agency", RUN_DATE, source_tier=1),
    I.NewsItem(
        "Texas Education Agency Appoints Board of Managers and Names New Superintendent for Lake Worth ISD",
        "", "https://tea.texas.gov/about-tea/newsroom/2026/tea-appoints-lake-worth-isd-board-of-managers",
        "Texas Education Agency", RUN_DATE, source_tier=1),
    I.NewsItem(
        "Texas Education Agency appoints Board of Managers and Names New Superintendent to Lead Fort Worth ISD",
        "", "https://tea.texas.gov/about-tea/newsroom/2026/tea-appoints-fort-worth-isd-board-of-managers",
        "Texas Education Agency", RUN_DATE, source_tier=1),
    I.NewsItem(
        "TEA Announces Houston ISD School Board Changes",
        "", "https://tea.texas.gov/about-tea/newsroom/2026/tea-houston-isd-board-changes",
        "Texas Education Agency", RUN_DATE, source_tier=1),
]


def main() -> int:
    districts = I.load_districts()
    ref = I.load_reference()
    findings = I.analyze(SAMPLE, districts, ref)

    # Illustrative enrichment on the bond item, so the "extracted facts" row has
    # something to show at Tier 1. A live run's LLM path produces this for real.
    for f in findings:
        if f.beat == "bond":
            f.enrichment = {
                "event_type": "bond_election", "status": "proposed",
                "bond_amount_usd": 1_200_000_000, "effective_date": None,
                "financial_amount_usd": None, "enrollment_stated": None,
                "person_named": None, "needs_verification": True,
            }

    briefing = I.build_briefing(findings, RUN_DATE)
    briefing["meta"]["note"] = (
        "SAMPLE briefing, committed so /briefing, /intel and /feed work with no "
        "database. The TEA items are REAL first-hand press releases from "
        "tea.texas.gov (tier 1); the bond item and its extracted-facts row are "
        "illustrative. A live daily run replaces all of it. Headlines in the "
        "house voice are generated from this repo's own TEA data — every number "
        "shown is sourced, and no individual is named or characterized."
    )
    out = ROOT / "static" / "isd_briefing.json"
    out.write_text(json.dumps(briefing, indent=2))
    print(f"wrote {out}  ({len(findings)} findings, "
          f"{sum(1 for f in findings if f.hook)} with hooks)")
    for f in briefing["top_findings"]:
        print(f"  [{f['beat']}] {f['hook']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
