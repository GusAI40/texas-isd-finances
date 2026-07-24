"""
Graph analytics over the district network. Three deterministic products:

1. static/map_data.json — 2D similarity-map coordinates for every district
   (PCA projection of the same z-scored exogenous feature space the k-NN
   graph uses: log enrollment, 5-yr growth, revenue/student, local-tax
   share). PCA rather than force-layout: positions are reproducible and
   axes are interpretable (PC1 ≈ scale+wealth, PC2 ≈ trajectory).

2. Flag co-occurrence analysis — which anomaly types travel together
   across district-years (lift over independence), printed for
   docs/GRAPH_INSIGHTS.md.

3. Temporal drift — districts whose structural position moved farthest
   between fiscal 2015 and 2025 (features z-scored within each year so
   drift means movement relative to the state, not inflation).

Run: python scripts/graph_insights.py   (after prepare_data.py)
"""
import json
import sys

import numpy as np
import pandas as pd

FEATS = ["log_enroll", "growth5", "rev_per_student", "local_share"]


def features_for_year(df, year):
    cur = df[df.year == year].copy()
    cur = cur[(cur.fall_survey_enrollment > 0)
              & cur.all_funds_total_operating_revenue.notna()].copy()
    past = df[df.year == year - 5][["district_number", "fall_survey_enrollment"]] \
        .rename(columns={"fall_survey_enrollment": "enroll_past"})
    cur = cur.merge(past, on="district_number", how="left")
    cur["growth5"] = ((cur.fall_survey_enrollment - cur.enroll_past) / cur.enroll_past) \
        .clip(-0.5, 0.5).fillna(0.0)
    cur["log_enroll"] = np.log10(cur.fall_survey_enrollment)
    cur["rev_per_student"] = cur.all_funds_total_operating_revenue / cur.fall_survey_enrollment
    cur["local_share"] = (cur.all_funds_local_tax_revenue_from_m_o.fillna(0)
                          / cur.all_funds_total_operating_revenue).clip(0, 1)
    X = cur[FEATS].to_numpy(dtype=float)
    X[:, 2] = np.clip(X[:, 2], *np.percentile(X[:, 2], [1, 99]))
    Xz = (X - X.mean(axis=0)) / X.std(axis=0)
    return cur, Xz


def build_map(df, latest):
    cur, Xz = features_for_year(df, latest)
    # PCA
    cov = np.cov(Xz.T)
    vals, vecs = np.linalg.eigh(cov)
    order = np.argsort(vals)[::-1]
    W = vecs[:, order[:2]]  # loadings: features x 2

    # Canonicalize axis orientation so the map reads the same every rebuild:
    # PC1 positive direction = larger districts; PC2 positive = growing.
    if W[FEATS.index("log_enroll"), 0] < 0:
        W[:, 0] *= -1
    if W[FEATS.index("growth5"), 1] < 0:
        W[:, 1] *= -1
    P = Xz @ W

    # Human-readable BIPOLAR axis labels: each PC is a spectrum between two
    # poles. Name each pole from the single strongest loading on that side,
    # so both ends always read clearly ("bigger ↔ smaller", never "—").
    POLE = {  # (positive-direction word, negative-direction word)
        "log_enroll": ("bigger", "smaller"),
        "growth5": ("growing", "shrinking"),
        "rev_per_student": ("better-funded", "leaner-funded"),
        "local_share": ("property-tax-funded", "state-funded"),
    }
    def axis_label(k):
        pos = max(range(len(FEATS)), key=lambda i: W[i, k])
        neg = min(range(len(FEATS)), key=lambda i: W[i, k])
        return f"{POLE[FEATS[neg]][1]} ← → {POLE[FEATS[pos]][0]}"

    # Neighbor indices (top 6 by rank) from the committed edge list, so the
    # map can draw each district's ego network.
    edges = pd.read_csv("docs/similarity_edges.csv",
                        dtype={"district_number": str, "peer_number": str})
    idx = {d: i for i, d in enumerate(cur.district_number)}
    nbrs = [[] for _ in range(len(cur))]
    for r in edges[edges["rank"] <= 6].itertuples():
        if r.district_number in idx and r.peer_number in idx:
            nbrs[idx[r.district_number]].append(idx[r.peer_number])

    # Recently-flagged layer: revenue drop or enrollment decline in the
    # last two data years (same definition as the usage simulation).
    recent = df[df.year >= latest - 2].sort_values(["district_number", "year"]).copy()
    g = recent.groupby("district_number")
    rev_prev = g["all_funds_total_operating_revenue"].shift(1)
    enr_prev = g["fall_survey_enrollment"].shift(1)
    flagged = set(recent[
        ((recent.all_funds_total_operating_revenue - rev_prev) / rev_prev < -0.15)
        | ((recent.fall_survey_enrollment - enr_prev) / enr_prev < -0.10)
    ]["district_number"])

    spend = (cur.all_funds_total_disbursements / cur.fall_survey_enrollment).round(0)
    nodes = [{
        "d": r.district_number,
        "n": r.district_name,
        "x": round(float(P[i, 0]), 3),
        "y": round(float(P[i, 1]), 3),
        "e": int(r.fall_survey_enrollment),
        "s": None if np.isnan(spend.iloc[i]) else int(spend.iloc[i]),
        "k": nbrs[i],
        "f": 1 if r.district_number in flagged else 0,
    } for i, r in enumerate(cur.itertuples())]
    var = vals[order[:2]] / vals.sum()
    meta = {"year": latest, "pc_variance": [round(float(v), 3) for v in var],
            "features": FEATS,
            "x_label": axis_label(0), "y_label": axis_label(1),
            "flagged_count": len(flagged)}
    json.dump({"meta": meta, "nodes": nodes}, open("static/map_data.json", "w"))
    print(f"map: {len(nodes)} nodes, PC1+PC2 explain {var.sum():.0%} of variance")
    print(f"  x → {meta['x_label']}")
    print(f"  y → {meta['y_label']}")
    print(f"  recently flagged: {len(flagged)} districts")


def flag_cooccurrence(df):
    d = df.sort_values(["district_number", "year"]).copy()
    g = d.groupby("district_number")
    rev, spend = "all_funds_total_operating_revenue", "all_funds_total_disbursements"
    enr = "fall_survey_enrollment"
    d["prev_rev"], d["prev_spend"], d["prev_enr"] = g[rev].shift(1), g[spend].shift(1), g[enr].shift(1)
    d["sps"] = d[spend] / d[enr]
    d["prev_sps"] = g["sps"].shift(1) if "sps" in d else None
    d["prev_sps"] = d.groupby("district_number")["sps"].shift(1)
    F = pd.DataFrame({
        "revenue_drop": (d[rev] - d.prev_rev) / d.prev_rev < -0.15,
        "spend_spike": ((d[spend] - d.prev_spend) / d.prev_spend > 0.20)
                       & ((d[enr] - d.prev_enr).abs() < 10),
        "per_student_spike": (d.sps - d.prev_sps) / d.prev_sps > 0.15,
        "enrollment_decline": (d[enr] - d.prev_enr) / d.prev_enr < -0.10,
    }).fillna(False)
    n = len(F)
    print(f"\nflag co-occurrence over {n} district-years:")
    out = []
    cols = list(F.columns)
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            a, b = cols[i], cols[j]
            pa, pb = F[a].mean(), F[b].mean()
            pab = (F[a] & F[b]).mean()
            lift = pab / (pa * pb) if pa * pb else 0
            out.append((a, b, int((F[a] & F[b]).sum()), round(lift, 1)))
    for a, b, c, lift in sorted(out, key=lambda t: -t[3]):
        print(f"  {a} + {b}: {c} joint events, lift {lift}x")
    return out


def drift(df, y0, y1):
    c0, X0 = features_for_year(df, y0)
    c1, X1 = features_for_year(df, y1)
    m0 = dict(zip(c0.district_number, X0.tolist()))
    both = [d for d in c1.district_number if d in m0]
    idx = {d: i for i, d in enumerate(c1.district_number)}
    rows = []
    for d in both:
        a, b = np.array(m0[d]), X1[idx[d]]
        rows.append((d, c1.iloc[idx[d]].district_name, float(np.linalg.norm(b - a)),
                     round(float(b[1] - a[1]), 2), round(float(b[3] - a[3]), 2)))
    top = sorted(rows, key=lambda t: -t[2])[:10]
    print(f"\ntop structural drifters {y0}→{y1} (movement in state-relative feature space):")
    for d, n, dist, dg, dl in top:
        print(f"  {n} ({d}): drift {dist:.2f} | growth-z {dg:+} | local-share-z {dl:+}")
    return top


def main(csv_path="data/texas_finance_clean.csv"):
    df = pd.read_csv(csv_path, dtype={"district_number": str})
    latest = int(df.year.max())
    build_map(df, latest)
    flag_cooccurrence(df)
    drift(df, latest - 10, latest)


if __name__ == "__main__":
    main(*sys.argv[1:])
