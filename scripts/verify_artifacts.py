"""Rebuild every artifact and prove the committed one is what the source says.

The hole this closes
--------------------
The committed JSON files under static/ are what the site serves. Nothing until
now checked that they still match what the build scripts produce from the
current source data. Two ways that goes wrong, both silent:

- **Stale artifact.** Someone edits a builder, forgets to re-run it, and the
  site keeps serving the old numbers. Every test passes, because the tests read
  the artifact.
- **Upstream drift.** TEA restates a year. The source CSV changes, the artifact
  does not, and the site now disagrees with the state while claiming to quote
  it.

This rebuilds each artifact into a temporary directory and compares byte for
byte against what is committed. The builders are deterministic — same input,
same output — so any difference is real.

    python scripts/verify_artifacts.py            # report
    python scripts/verify_artifacts.py --update   # rebuild in place

Exits non-zero on any mismatch, so CI can hold the line.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# artifact -> (builder, extra args). Order matters: forensic and trend read the
# artifacts the earlier ones write, which is also the documented rebuild order.
CHAIN = [
    # economics_data.json was missing from this chain for months. It is the
    # artefact the forensic and trend layers read, and since it now carries the
    # per-district lineage a reader can click, a builder edited and never re-run
    # would leave that evidence describing arithmetic the site no longer does.
    # It rebuilds byte-identically, so there is no reason for it to be exempt.
    ("economics_data.json", "build_economics_data.py", []),
    ("bond_data.json", "build_bond_data.py", []),
    ("forensic_data.json", "build_forensic_data.py", []),
    ("trend_data.json", "build_trend_data.py", []),
    ("national_data.json", "build_national_data.py", []),
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def summarise(p: Path) -> dict:
    """A few figures to print when a hash differs, so the diff is legible
    rather than 'the bytes changed'."""
    try:
        d = json.loads(p.read_text())
    except Exception:
        return {}
    m = d.get("meta", {})
    out = {k: m[k] for k in ("districts", "propositions", "matched_pct",
                             "first_year", "last_year", "years") if k in m}
    if "districts" in d and isinstance(d["districts"], dict):
        out["district_records"] = len(d["districts"])
    sw = d.get("statewide")
    if isinstance(sw, dict):
        for k in ("debt_total", "debt_median", "recapture_payers"):
            if k in sw:
                out[k] = sw[k]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update", action="store_true",
                    help="rebuild in place instead of only reporting")
    args = ap.parse_args()

    static = ROOT / "static"
    if args.update:
        for name, builder, extra in CHAIN:
            print(f"rebuilding {name} ...", flush=True)
            r = subprocess.run([sys.executable, f"scripts/{builder}", *extra],
                               cwd=ROOT, capture_output=True, text=True)
            if r.returncode:
                print(r.stderr, file=sys.stderr)
                return 1
        print("rebuilt in place")
        return 0

    drift = []
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        # The chain reads earlier artifacts, so build into the temp dir but let
        # each step read the ones already built there.
        for name, builder, extra in CHAIN:
            committed = static / name
            if not committed.exists():
                drift.append((name, "missing", "artifact is not committed"))
                continue
            target = tmpdir / name
            cmd = [sys.executable, f"scripts/{builder}", "--out", str(target), *extra]
            # Point the chained builders at what we have already rebuilt. A
            # builder left reading static/ instead reads the COMMITTED input, so
            # a genuine upstream change would only surface on a second run —
            # which is a drift check that reports clean on the run where the
            # drift appears.
            if builder == "build_forensic_data.py":
                cmd += ["--bonds", str(tmpdir / "bond_data.json"),
                        "--economics", str(tmpdir / "economics_data.json")]
            if builder == "build_trend_data.py":
                cmd += ["--economics", str(tmpdir / "economics_data.json")]
            if builder == "build_national_data.py":
                # Coverage counts are measured against the economics artifact,
                # so measure against the freshly rebuilt one, not the committed.
                cmd += ["--economics", str(tmpdir / "economics_data.json")]
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            if r.returncode:
                drift.append((name, "build failed", r.stderr.strip()[-300:]))
                continue
            if sha(target) == sha(committed):
                print(f"  OK        {name}")
                continue
            a, b = summarise(committed), summarise(target)
            changed = {k: (a.get(k), b.get(k)) for k in set(a) | set(b)
                       if a.get(k) != b.get(k)}
            drift.append((name, "differs", changed or "content differs, headline figures identical"))
            shutil.copy(target, tmpdir / f"rebuilt-{name}")

    if not drift:
        print("\nevery committed artifact matches a fresh build from source.")
        return 0

    print("\nDRIFT — a committed artifact is not what the source produces:")
    for name, kind, detail in drift:
        print(f"  {name}: {kind}")
        if isinstance(detail, dict):
            for k, (was, now) in detail.items():
                print(f"      {k}: committed {was}  ->  rebuilt {now}")
        else:
            print(f"      {detail}")
    print("\nRun `python scripts/verify_artifacts.py --update` and commit the result.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
