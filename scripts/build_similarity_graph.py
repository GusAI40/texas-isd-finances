"""
Build the district similarity graph (k-nearest neighbors).

Graph-engineering rationale
---------------------------
"Peer districts" is a graph problem: nodes = districts, edges = structural
similarity. Crucially, similarity must be computed on features EXOGENOUS to
the metrics being benchmarked — if peers were chosen for similar
*spending*, then comparing spending among them would be circular. So edges
use only size, trajectory, and funding-capacity features:

  - log(enrollment)                  (scale)
  - 5-year enrollment growth rate    (trajectory)
  - revenue per student              (funding capacity)
  - local-tax share of revenue       (wealth/funding structure)

Features are z-scored; distance is Euclidean in that space; each district
gets its k=12 nearest neighbors. Deterministic (no randomness).

Output: docs/similarity_edges.csv (district_number, peer_number, rank,
distance) — ~14k edges for ~1,200 districts — ready to load into the
`district_similarity` table (see sql/create_similarity_table.sql).

Run: python scripts/build_similarity_graph.py
"""
import sys

import numpy as np
import pandas as pd

K = 12


def build(csv_path="data/texas_finance_clean.csv", out_path="docs/similarity_edges.csv"):
    df = pd.read_csv(csv_path, dtype={"district_number": str})
    latest_year = int(df.year.max())

    cur = df[df.year == latest_year].copy()
    cur = cur[(cur.fall_survey_enrollment > 0)
              & cur.all_funds_total_operating_revenue.notna()].copy()

    # 5-year enrollment growth
    past = df[df.year == latest_year - 5][["district_number", "fall_survey_enrollment"]] \
        .rename(columns={"fall_survey_enrollment": "enroll_past"})
    cur = cur.merge(past, on="district_number", how="left")
    cur["growth5"] = (cur.fall_survey_enrollment - cur.enroll_past) / cur.enroll_past
    cur["growth5"] = cur.growth5.clip(-0.5, 0.5).fillna(0.0)

    cur["log_enroll"] = np.log10(cur.fall_survey_enrollment)
    cur["rev_per_student"] = cur.all_funds_total_operating_revenue / cur.fall_survey_enrollment
    cur["local_share"] = (
        cur.all_funds_local_tax_revenue_from_m_o.fillna(0)
        / cur.all_funds_total_operating_revenue
    ).clip(0, 1)

    feats = ["log_enroll", "growth5", "rev_per_student", "local_share"]
    X = cur[feats].to_numpy(dtype=float)
    # winsorize rev_per_student (tiny districts produce extreme values)
    X[:, 2] = np.clip(X[:, 2], *np.percentile(X[:, 2], [1, 99]))
    X = (X - X.mean(axis=0)) / X.std(axis=0)
    # scale: size dominates peer intuition; weight it up slightly
    X[:, 0] *= 2.0

    ids = cur.district_number.to_numpy()
    n = len(ids)
    edges = []
    for i in range(n):
        d = np.sqrt(((X - X[i]) ** 2).sum(axis=1))
        d[i] = np.inf
        nn = np.argsort(d)[:K]
        for rank, j in enumerate(nn, start=1):
            edges.append((ids[i], ids[j], rank, round(float(d[j]), 4)))

    out = pd.DataFrame(edges, columns=["district_number", "peer_number", "rank", "distance"])
    out.to_csv(out_path, index=False)
    print(f"Graph built: {n} nodes, {len(out)} edges (k={K}), year {latest_year}")
    print(f"Features (exogenous only): {feats}")
    print(f"Saved: {out_path}")
    return out


if __name__ == "__main__":
    build(*sys.argv[1:])
