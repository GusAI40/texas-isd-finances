"""`.vercelignore` is a silent third environment, and this is its guard.

The repo checkout, CI, and the deployed site do not hold the same files. A
module under `src/` that opens something outside `src/`, `static/` or `api/`
works perfectly in every test and 500s in production, and nothing in a green
suite says so. That has now happened three times:

  1. `scripts/isd_intel` — the daily-intelligence cron ImportError'd in
     production and the feed silently froze on its committed snapshot.
  2. `scripts/freshness_vintages.json` — `src/sources.py` reads it at request
     time, so the deployed lineage panel answered "we do not know" for every
     freshness question and dropped every verdict to UNVERIFIED.
  3. `data/district_crosswalk.csv` — `src/outreach_map.py` reads it to name
     each district, so `/ops/outreach-data` raised FileNotFoundError and
     answered 500 from the day it shipped (2026-08-14) until 2026-08-19.

Each was fixed with a one-off re-include. This file replaces that pattern with
a rule: find what `src/` actually reads, and fail the build if the deploy would
not carry it. The next instance is caught before it ships rather than after.

The rules are evaluated with real gitignore semantics — `.vercelignore` follows
them — by handing the file to `git check-ignore` in a throwaway repo, rather
than asserting that certain lines appear. Line-presence tests pass while the
rule is inert: `data/` plus `!data/district_crosswalk.csv` looks correct and
excludes the file anyway, because gitignore cannot re-include through an
excluded parent directory.
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
VERCELIGNORE = ROOT / ".vercelignore"

# Paths under these roots ship by definition — they are the service itself.
SHIPPED_ROOTS = ("src", "static", "api")

# Contact data. These hold named superintendents' email addresses and must
# NEVER reach the deploy, which is served from a public CDN. The mailing list
# is gitignored and never committed; the sent log likewise. Any change that
# starts shipping one of these is a privacy incident, not a build tweak.
NEVER_SHIP = (
    "data/outreach_merge.csv",
    "data/outreach_sent.csv",
    "data/outreach_recipients.csv",
    "data/outreach_optout.txt",
    "data/outreach_kpi_report.csv",
)


def _ignored(paths: list[str]) -> dict[str, bool]:
    """path -> would .vercelignore exclude it, by real gitignore semantics."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
        shutil.copyfile(VERCELIGNORE, tmp / ".gitignore")
        for p in paths:
            f = tmp / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.touch()
        out = {}
        for p in paths:
            r = subprocess.run(["git", "check-ignore", "-q", p], cwd=tmp)
            out[p] = r.returncode == 0        # 0 == matched an ignore rule
        return out


# Files src/ reads that are DELIBERATELY absent in production. Each one must
# be guarded at the read site so its absence degrades the answer instead of
# raising — and that guard is itself asserted below, because "optional" with an
# unguarded open is just the 500 this whole file exists to prevent.
#
#   data/outreach_merge.csv — the mailing list, holding named superintendents'
#     email addresses. Gitignored, never committed, and must never be uploaded
#     to a public-CDN deploy. /ops/outreach-data reads it only to mark which
#     districts are IN the campaign; without it every district reads as
#     not-in-list, so the private map under-reports coverage rather than
#     failing. Sourcing that set from the database instead would remove the
#     degradation; until then this is the honest trade.
OPTIONAL_READS = {"data/outreach_merge.csv"}


def _reads_outside_src() -> set[str]:
    """Every repo-relative file path that a module under src/ opens.

    Matches the two shapes this codebase uses for a repo-root anchor:
        ROOT = Path(__file__).resolve().parent.parent   ->  ROOT / "a" / "b"
        X = Path(__file__).resolve().parent.parent / "a" / "b"
    """
    anchored = re.compile(
        r'(?:ROOT|ROOT_DIR|BASE|parent\.parent)\s*((?:/\s*"[^"]+"\s*)+)')
    found: set[str] = set()
    for py in sorted((ROOT / "src").glob("*.py")):
        for m in anchored.finditer(py.read_text(encoding="utf-8")):
            parts = re.findall(r'"([^"]+)"', m.group(1))
            rel = "/".join(parts)
            if rel and not rel.startswith(SHIPPED_ROOTS):
                found.add(rel)
    return found


@pytest.mark.skipif(shutil.which("git") is None, reason="git required")
def test_everything_src_reads_is_actually_deployed():
    """The general rule. A file src/ opens at request time must survive
    .vercelignore, or the endpoint that needs it fails in production only."""
    reads = _reads_outside_src()
    assert reads, "the scanner found nothing — it has stopped matching"
    required = sorted(reads - OPTIONAL_READS)
    verdict = _ignored(required)
    excluded = sorted(p for p, ig in verdict.items() if ig)
    assert not excluded, (
        "src/ reads these at request time but .vercelignore drops them from "
        f"the deploy, so they exist in every test and 404 in production: "
        f"{excluded}. Re-include each one (after any later broad rule such as "
        f"*.csv), or add it to OPTIONAL_READS and guard the read.")


def test_every_optional_read_is_actually_guarded():
    """OPTIONAL_READS is a promise that absence was handled, not a way to
    silence the rule above. An unguarded open of a file that production does
    not have is the exact 500 this file exists to prevent — so the guard is
    checked, not trusted.

    src/outreach_map.py._names() is the cautionary case: it opened the
    crosswalk with no `.exists()` anywhere near it, which is why the endpoint
    returned 500 instead of a map with unnamed districts.
    """
    for py in sorted((ROOT / "src").glob("*.py")):
        lines = py.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            for rel in OPTIONAL_READS:
                tail = rel.split("/")[-1]
                if f'"{tail}"' not in line:
                    continue
                window = "\n".join(lines[max(0, i - 3):i + 6])
                assert ".exists()" in window, (
                    f"{py.name}:{i + 1} builds a path to {rel}, which "
                    f"production does not have, with no .exists() guard "
                    f"within a few lines — its absence would raise, not "
                    f"degrade")


@pytest.mark.skipif(shutil.which("git") is None, reason="git required")
def test_the_crosswalk_ships_because_the_outreach_map_needs_it():
    """The 2026-08-19 regression, pinned directly.

    src/outreach_map.py._names() opens this with no fallback, so its absence
    is a 500 rather than a degraded map."""
    assert _ignored(["data/district_crosswalk.csv"])["data/district_crosswalk.csv"] is False


@pytest.mark.skipif(shutil.which("git") is None, reason="git required")
def test_contact_data_never_reaches_the_deploy():
    """The counterweight to the rule above. Fixing a missing-file 500 by
    shipping data/ wholesale would push named superintendents' email addresses
    onto a public CDN. Every re-include must be one specific file."""
    verdict = _ignored(list(NEVER_SHIP))
    leaked = sorted(p for p, ig in verdict.items() if not ig)
    assert not leaked, (
        f"these hold real contact data and would be uploaded to the deploy: "
        f"{leaked}. Never re-include them; source that data from the database "
        f"instead.")


@pytest.mark.skipif(shutil.which("git") is None, reason="git required")
def test_the_big_source_csvs_still_stay_out():
    """The reason data/ is excluded at all: ~19 MB of source CSVs made every
    deploy slow enough to time out. A re-include must not undo that."""
    heavy = ["data/texas_finance_clean.csv", "data/staar_district_2026.csv"]
    verdict = _ignored(heavy)
    shipped = sorted(p for p, ig in verdict.items() if not ig)
    assert not shipped, f"large source data would be uploaded again: {shipped}"
