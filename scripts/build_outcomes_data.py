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

# Optional: bordering districts. A statistical peer can be 400 miles away; the
# district across the county line shares the labour market, the economy and the
# weather, which is what makes its numbers hard to explain away.
try:
    import shapefile as _shp
except ImportError:  # pragma: no cover - only needed when --shapefile is used
    _shp = None


def _norm_name(s: str) -> str:
    import re as _re
    s = s.lower()
    for a, b in [("consolidated independent school district", "cisd"),
                 ("independent school district", "isd"),
                 ("common school district", "csd"),
                 ("municipal school district", "msd"),
                 ("school district", "sd")]:
        s = s.replace(a, b)
    return _re.sub(r"\s+", " ", _re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def borders_by_name(path):
    """{normalised district name: [normalised neighbour names]} from TIGER."""
    from collections import defaultdict
    r = _shp.Reader(path)
    flds = [f[0] for f in r.fields[1:]]
    names = [_norm_name(dict(zip(flds, rec))["NAME"]) for rec in r.records()]
    vert = defaultdict(set)
    for i, shp in enumerate(r.shapes()):
        for x, y in shp.points:
            vert[(round(x, 6), round(y, 6))].add(i)
    hits = defaultdict(int)
    for ds in vert.values():
        if 1 < len(ds) <= 12:
            ds = sorted(ds)
            for a in range(len(ds)):
                for b in range(a + 1, len(ds)):
                    hits[(ds[a], ds[b])] += 1
    out = defaultdict(list)
    for (a, b), n in hits.items():
        if n >= 2:
            out[names[a]].append(names[b])
            out[names[b]].append(names[a])
    return out

NEED = ["pct_econ_disadv", "pct_emergent_bilingual", "pct_special_ed"]

# measure -> (label, higher_is_better, unit)
MEASURES = {
    "teacher_turnover_pct":  ("Teacher turnover", False, "%"),
    "teacher_avg_experience": ("Average teacher experience", True, " yrs"),
    "avg_teacher_salary":    ("Average teacher salary", True, "$"),
    "students_per_teacher":  ("Students per teacher", False, ""),
    "attendance_rate":       ("Attendance rate", True, "%"),
    "grad_rate_4yr":         ("4-year graduation rate", True, "%"),
    "test_all_meets":        ("STAAR at grade level (Meets)", True, "%"),
    "test_all_approaches":   ("STAAR at/above the lowest bar (Approaches)", True, "%"),
    "test_all_masters":      ("STAAR mastering grade level (Masters)", True, "%"),
}


def med(vals):
    vals = [v for v in vals if v is not None and not pd.isna(v)]
    return round(float(statistics.median(vals)), 1) if len(vals) >= 4 else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--finance", required=True)
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--graph", default="static/map_data.json")
    ap.add_argument("--shapefile", help="tl_YYYY_48_unsd — enables the bordering-district lookup")
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

    year = int(df[df["test_all_meets"].notna()]["year"].max())
    cur = df[df["year"] == year].set_index("district_number")
    print(f"Latest year with results: {year}  ({len(cur):,} districts)")

    # --- expectation model: what does this student population predict? ---
    fit = cur.dropna(subset=NEED + ["test_all_meets"])
    X = np.column_stack([np.ones(len(fit)), fit[NEED].to_numpy(float)])
    y = fit["test_all_meets"].to_numpy(float)
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

    borders = {}
    if args.shapefile:
        if _shp is None:
            raise SystemExit("pyshp is required for --shapefile (pip install pyshp)")
        borders = borders_by_name(args.shapefile)
        print(f"borders loaded    : {len(borders):,} districts")
    by_name = {_norm_name(str(r.get("district_name", ""))): num for num, r in cur.iterrows()} \
        if False else {_norm_name(str(cur.loc[n, "district_name"])): n for n in cur.index}

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

        # The bordering district that serves similar students and keeps its
        # teachers best. Not a ranking — a phone call worth making.
        nb_best = None
        my_t, my_p = val("teacher_turnover_pct"), val("pct_econ_disadv")
        if borders and my_t is not None and my_p is not None:
            for nb_name in borders.get(_norm_name(str(row.get("district_name", ""))), []):
                onum = by_name.get(nb_name)
                if onum is None or onum == num or onum not in cur.index:
                    continue
                o = cur.loc[onum]
                ot, op = o.get("teacher_turnover_pct"), o.get("pct_econ_disadv")
                if pd.isna(ot) or pd.isna(op):
                    continue
                if abs(float(op) - my_p) <= 8 and (my_t - float(ot)) >= 4:
                    if nb_best is None or float(ot) < nb_best["turnover"]:
                        nb_best = {"district_number": onum, "name": o.get("district_name"),
                                   "turnover": round(float(ot), 1),
                                   "pct_econ_disadv": round(float(op), 1)}

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
            "border_keeps_teachers_better": nb_best,
        }
        if exp is not None and not pd.isna(exp) and val("test_all_meets") is not None:
            rec["expectation"] = {
                "expected": round(float(exp), 1),
                "actual": val("test_all_meets"),
                "gap": round(val("test_all_meets") - float(exp), 1),
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
