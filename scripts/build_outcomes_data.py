"""Precompute the per-district outcomes payload the portal serves.

Joins TEA Snapshot (students, teachers, tax base, results) to our PEIMS
spending, scores every district against what its student population predicts,
and compares each measure to the SAME structural peers the rest of the site
uses — read from static/map_data.json, which is the k-NN similarity graph
built on exogenous features only (size, growth, funding capacity). So "vs
peers" means the same thing here as everywhere else on the site.

Output: static/outcomes_data.json, served by GET /district/{id}/outcomes.
Precomputed rather than queried because none of it changes between annual TEA
releases, and a static file costs no database round trip.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import numpy as np
import pandas as pd

NEED = ["pct_econ_disadv", "pct_emergent_bilingual", "pct_special_ed"]

# measure -> (label, higher_is_better, unit)
MEASURES = {
    "teacher_turnover_pct":  ("Teacher turnover", False, "%"),
    "teacher_avg_experience": ("Average teacher experience", True, " yrs"),
    "avg_teacher_salary":    ("Average teacher salary", True, "$"),
    "students_per_teacher":  ("Students per teacher", False, ""),
    "attendance_rate":       ("Attendance rate", True, "%"),
    "grad_rate_4yr":         ("4-year graduation rate", True, "%"),
    "test_all_approaches":   ("STAAR at/above grade level", True, "%"),
}


def med(vals):
    vals = [v for v in vals if v is not None and not pd.isna(v)]
    return round(float(statistics.median(vals)), 1) if len(vals) >= 4 else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--finance", required=True)
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--graph", default="static/map_data.json")
    ap.add_argument("--out", default="static/outcomes_data.json")
    args = ap.parse_args()

    snap = pd.read_csv(args.snapshot, dtype={"district_number": str}, low_memory=False)
    fin = pd.read_csv(args.finance, dtype={"district_number": str}, low_memory=False)
    snap["district_number"] = snap["district_number"].str.zfill(6)
    fin["district_number"] = fin["district_number"].str.zfill(6)

    spend_col = "all_funds_total_operate_expend_by_function"
    fin = fin[["district_number", "year", spend_col, "fall_survey_enrollment"]].rename(
        columns={spend_col: "operating_spend", "fall_survey_enrollment": "enrollment"})
    df = snap.merge(fin, on=["district_number", "year"], how="left")
    df = df[df["enrollment"].fillna(0) > 0].copy()
    df["spend_per_student"] = df["operating_spend"] / df["enrollment"]

    year = int(df[df["test_all_approaches"].notna()]["year"].max())
    cur = df[df["year"] == year].set_index("district_number")
    print(f"Latest year with results: {year}  ({len(cur):,} districts)")

    # --- expectation model: what does this student population predict? ---
    fit = cur.dropna(subset=NEED + ["test_all_approaches"])
    X = np.column_stack([np.ones(len(fit)), fit[NEED].to_numpy(float)])
    y = fit["test_all_approaches"].to_numpy(float)
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ coef
    r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    expected = pd.Series(pred, index=fit.index)
    print(f"Need model explains {r2*100:.1f}% of the STAAR spread")

    # --- statewide medians, for the "what's normal" question ---
    state = {m: med(cur[m].tolist()) for m in MEASURES if m in cur}
    state["spend_per_student"] = med(cur["spend_per_student"].tolist())

    # --- peers from the same similarity graph the rest of the site uses ---
    graph = json.loads(Path(args.graph).read_text())
    nodes = graph["nodes"]
    by_num = {n["d"]: n for n in nodes}

    out, with_peers = {}, 0
    for num, row in cur.iterrows():
        node = by_num.get(num)
        peer_nums = [nodes[i]["d"] for i in (node.get("k") or [])] if node else []
        peers = cur.loc[[p for p in peer_nums if p in cur.index]] if peer_nums else cur.iloc[0:0]
        if len(peers) >= 4:
            with_peers += 1

        def val(m):
            v = row.get(m)
            return None if v is None or pd.isna(v) else round(float(v), 1)

        # Compact: [own value, peer median]. Labels/units/state medians live
        # once in meta — repeating them 1,205 times tripled the payload.
        measures = {}
        for m in MEASURES:
            mine = val(m)
            if mine is None:
                continue
            measures[m] = [mine, med(peers[m].tolist()) if len(peers) else None]

        exp = expected.get(num)
        rec = {
            "district_number": num,
            "district_name": row.get("district_name"),
            "year": year,
            "students": int(row["students"]) if not pd.isna(row.get("students")) else None,
            "peer_count": int(len(peers)),
            "need": {k: val(k) for k in NEED},
            "measures": measures,
            "spend_per_student": val("spend_per_student"),
            "spend_peer_median": med(peers["spend_per_student"].tolist()) if len(peers) else None,
            "spend_state_median": state["spend_per_student"],
        }
        if exp is not None and not pd.isna(exp) and val("test_all_approaches") is not None:
            rec["expectation"] = {
                "expected": round(float(exp), 1),
                "actual": val("test_all_approaches"),
                "gap": round(val("test_all_approaches") - float(exp), 1),
                "model_r2": round(float(r2), 4),
            }
        out[num] = rec

    payload = {
        "meta": {
            "year": year,
            "districts": len(out),
            "with_peers": with_peers,
            "model_r2": round(float(r2), 4),
            "need_predictors": NEED,
            "need_state_medians": {k: med(cur[k].tolist()) for k in NEED},
            "measures": {m: {"label": lbl, "unit": u, "higher_is_better": hb,
                             "state_median": state.get(m)}
                         for m, (lbl, hb, u) in MEASURES.items()},
            "state_medians": state,
            "source": "TEA Snapshot District & Charter Detail + TEA Summarized PEIMS",
            # measured in scripts/analyze_outcomes.py over 13,212 district-years
            "lever_strength": {
                "teacher_turnover_pct": 10.12,
                "pct_teachers_new": 7.97,
                "teacher_avg_experience": 6.79,
                "pct_spend_instruction": 2.13,
                "students_per_teacher": 1.70,
                "avg_teacher_salary": 0.86,
                "spend_per_student": 0.01,
            },
        },
        "districts": out,
    }
    p = Path(args.out)
    p.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"Wrote {len(out):,} districts ({with_peers:,} with >=4 peers) to {p} "
          f"[{p.stat().st_size/1024:.0f} KB]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
