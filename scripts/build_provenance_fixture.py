"""Freeze the statewide aggregates the provenance tests need, from source.

Why a fixture rather than the CSV
---------------------------------
`data/texas_finance_clean.csv` is 18 MB (6.2 MB gzipped) and is deliberately
not committed — it is also excluded from the Vercel bundle. That means the
provenance tests, which recompute every published headline from source,
**silently skip in CI**. A guarantee that only holds on one laptop is not a
guarantee.

This writes the per-year statewide sums those tests need — 17 rows, a few
kilobytes — straight from the CSV, alongside a SHA-256 of the source file it
came from. CI then re-derives every headline from the fixture, and locally the
tests additionally check that the fixture still matches the real CSV.

The chain of custody is therefore: TEA file -> CSV (hashed here) -> fixture
(committed) -> published artifact -> page. Every link is checked by something.

    python scripts/build_provenance_fixture.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
FIRST, LAST = 2009, 2025

# Every column any published headline depends on. Named explicitly so a
# renamed column upstream fails here, loudly, rather than in a chart.
SUMS = {
    "instruction": "all_funds_instruction_transfer_expend_fct11_95",
    "operating": "all_funds_total_operating_expenditures_by_obj",
    "operating_revenue": "all_funds_total_operating_revenue",
    "other_revenue": "all_funds_other_revenue",
    "debt_service": "all_funds_total_debt_service_expend_by_obj",
    "capital": "all_funds_total_capital_projects_expend_by_obj",
    "security": "all_funds_security_monitoring_service_expend_fct52",
    "federal_revenue": "all_funds_federal_revenue",
    "state_revenue": "all_funds_state_revenue",
    "local_mo_tax": "all_funds_local_tax_revenue_from_m_o",
    "payroll": "all_funds_total_payroll_expenditures",
    "enrollment": "fall_survey_enrollment",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=ROOT / "data/texas_finance_clean.csv")
    ap.add_argument("--out", type=Path, default=ROOT / "tests/fixtures/provenance.json")
    args = ap.parse_args()
    if not args.source.exists():
        print(f"missing {args.source}")
        return 1

    raw = args.source.read_bytes()
    d = pd.read_csv(args.source, dtype={"district_number": str}, low_memory=False)
    num = lambda c: pd.to_numeric(d[c], errors="coerce")  # noqa: E731

    frame = pd.DataFrame({"year": pd.to_numeric(d.year, errors="coerce"),
                          "num": d.district_number,
                          **{k: num(c) for k, c in SUMS.items()}})
    frame = frame[(frame.year >= FIRST) & (frame.year <= LAST)]
    reporting = frame[frame.enrollment > 0]

    years = []
    for y, g in reporting.groupby("year"):
        short = g.operating > g.operating_revenue
        years.append({
            "year": int(y),
            "districts": int(len(g)),
            **{k: float(g[k].fillna(0).sum()) for k in SUMS},
            "districts_in_operating_deficit": int(short.sum()),
            "students_in_operating_deficit": float(g.loc[short, "enrollment"].sum()),
        })

    # The function taxonomy, needed by the reclassification check.
    fcols = [c for c in d.columns if c.startswith("all_funds_") and "fct" in c]
    fframe = pd.DataFrame({"year": pd.to_numeric(d.year, errors="coerce"),
                           **{c: num(c).fillna(0) for c in fcols}})
    fframe = fframe[(fframe.year >= FIRST) & (fframe.year <= LAST)]
    functions = {int(y): {c.replace("all_funds_", ""): float(v)
                          for c, v in g.drop(columns="year").sum().items()}
                 for y, g in fframe.groupby("year")}

    # Districts present in both end years — the balanced panel.
    both = (set(reporting[reporting.year == FIRST].num)
            & set(reporting[reporting.year == LAST].num))
    panel = reporting[reporting.num.isin(both)]
    panel_years = [{"year": int(y),
                    "instruction": float(g.instruction.sum()),
                    "operating": float(g.operating.sum())}
                   for y, g in panel.groupby("year")]

    payload = {
        "meta": {
            "source": str(args.source.relative_to(ROOT)),
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "source_bytes": len(raw),
            "rows": int(len(d)),
            "districts": int(d.district_number.nunique()),
            "first_year": FIRST, "last_year": LAST,
            "columns": SUMS,
            "note": "Statewide sums per year, straight from the source CSV. The "
                    "provenance tests re-derive every published headline from "
                    "this, so the guarantee holds in CI where the 18 MB source "
                    "is not available.",
        },
        "years": years,
        "functions": functions,
        "balanced_panel": {"districts": len(both), "years": panel_years},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=1))
    print(f"wrote {args.out} — {len(years)} years, {len(fcols)} functions, "
          f"{args.out.stat().st_size / 1024:.0f} KB")
    print(f"  source sha256 {payload['meta']['source_sha256'][:16]}... "
          f"({len(raw) / 1048576:.1f} MB, {len(d):,} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
