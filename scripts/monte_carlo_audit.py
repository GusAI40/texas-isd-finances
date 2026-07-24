"""
Monte Carlo robustness audit — quantitative patterns / gaps / blindspots.

Four independent simulations, each seeded and reproducible:

1. ARCHETYPE STABILITY — bootstrap-resample districts B times, re-cluster,
   and measure how often each district keeps its archetype. Low stability =
   boundary districts whose "type" is an artifact of the sample.

2. ANOMALY THRESHOLD SENSITIVITY — Monte Carlo the flag thresholds
   (15/20/10%) by ±5pp and measure how much the flagged-district count
   swings. Knife-edge thresholds = fragile findings.

3. LIVE API COVERAGE — sample random real districts and exercise every
   data endpoint against production, recording errors, empties, latency.
   Surfaces coverage gaps and reliability blindspots.

4. DATA COMPLETENESS — null coverage of the fields the product depends on,
   by year. Reveals where the dashboard silently shows "—".

Run: python scripts/monte_carlo_audit.py
Writes docs/monte_carlo_audit.json and prints a summary.
"""
import json
import sys
import time
import urllib.request

import numpy as np
import pandas as pd

SEED = 20260724
BASE = "https://texas-isd-finances.vercel.app"
FEATS = ["log_enroll", "growth5", "rev_per_student", "local_share"]


def _featmat(df, year):
    cur = df[df.year == year].copy()
    cur = cur[(cur.fall_survey_enrollment > 0)
              & cur.all_funds_total_operating_revenue.notna()].copy()
    past = df[df.year == year - 5][["district_number", "fall_survey_enrollment"]] \
        .rename(columns={"fall_survey_enrollment": "ep"})
    cur = cur.merge(past, on="district_number", how="left")
    cur["growth5"] = ((cur.fall_survey_enrollment - cur.ep) / cur.ep).clip(-.5, .5).fillna(0)
    cur["log_enroll"] = np.log10(cur.fall_survey_enrollment)
    cur["rev_per_student"] = cur.all_funds_total_operating_revenue / cur.fall_survey_enrollment
    cur["local_share"] = (cur.all_funds_local_tax_revenue_from_m_o.fillna(0)
                          / cur.all_funds_total_operating_revenue).clip(0, 1)
    X = cur[FEATS].to_numpy(float)
    X[:, 2] = np.clip(X[:, 2], *np.percentile(X[:, 2], [1, 99]))
    return cur.district_number.to_numpy(), (X - X.mean(0)) / X.std(0)


def _kmeans(Xz, k, rng, iters=60):
    n = len(Xz)
    centers = [int(rng.integers(n))]
    for _ in range(k - 1):
        d2 = np.min([((Xz - Xz[c]) ** 2).sum(1) for c in centers], axis=0)
        centers.append(int(rng.choice(n, p=d2 / d2.sum())))
    C = Xz[centers].copy()
    lab = np.zeros(n, int)
    for _ in range(iters):
        lab = np.argmin(((Xz[:, None] - C[None]) ** 2).sum(2), axis=1)
        newC = np.array([Xz[lab == j].mean(0) if (lab == j).any() else C[j] for j in range(k)])
        if np.allclose(newC, C):
            break
        C = newC
    return lab, C


def archetype_stability(df, latest, B=40):
    rng = np.random.default_rng(SEED)
    ids, Xz = _featmat(df, latest)
    base_lab, base_C = _kmeans(Xz, 6, np.random.default_rng(0))
    n = len(ids)
    # for each bootstrap, cluster the resample, then assign ALL points to the
    # nearest resample-centroid, and match clusters to base by centroid.
    agree = np.zeros(n)
    for _ in range(B):
        samp = rng.integers(0, n, n)
        lab_s, C_s = _kmeans(Xz[samp], 6, rng)
        # map resample clusters -> base clusters by nearest base centroid
        remap = {j: int(np.argmin(((base_C - C_s[j]) ** 2).sum(1))) for j in range(6)}
        assign = np.argmin(((Xz[:, None] - C_s[None]) ** 2).sum(2), axis=1)
        mapped = np.array([remap[a] for a in assign])
        agree += (mapped == base_lab)
    stab = agree / B
    return {
        "bootstraps": B,
        "mean_stability": round(float(stab.mean()), 3),
        "median_stability": round(float(np.median(stab)), 3),
        "pct_below_0.6": round(float((stab < 0.6).mean() * 100), 1),
        "n_unstable": int((stab < 0.6).sum()),
        "least_stable": [ids[i] for i in np.argsort(stab)[:8]],
    }


def threshold_sensitivity(df, trials=200):
    rng = np.random.default_rng(SEED + 1)
    d = df.sort_values(["district_number", "year"]).copy()
    g = d.groupby("district_number")
    d["pr"] = g["all_funds_total_operating_revenue"].shift(1)
    d["pe"] = g["fall_survey_enrollment"].shift(1)
    rev_chg = (d.all_funds_total_operating_revenue - d.pr) / d.pr
    enr_chg = (d.fall_survey_enrollment - d.pe) / d.pe
    base = int(((rev_chg < -0.15) | (enr_chg < -0.10)).sum())
    counts = []
    for _ in range(trials):
        rt = -0.15 + rng.uniform(-0.05, 0.05)
        et = -0.10 + rng.uniform(-0.05, 0.05)
        counts.append(int(((rev_chg < rt) | (enr_chg < et)).sum()))
    counts = np.array(counts)
    return {
        "trials": trials,
        "base_flag_events": base,
        "mean_under_jitter": round(float(counts.mean()), 1),
        "std_under_jitter": round(float(counts.std()), 1),
        "swing_pct": round(float(counts.std() / counts.mean() * 100), 1),
        "range": [int(counts.min()), int(counts.max())],
    }


def live_coverage(df, latest, sample=50):
    rng = np.random.default_rng(SEED + 2)
    ids = df[df.year == latest].district_number.unique()
    pick = rng.choice(ids, size=min(sample, len(ids)), replace=False)
    endpoints = ["summary", "peers", "breakdown", "turnarounds"]
    results = {e: {"ok": 0, "err": 0, "empty": 0, "ms": []} for e in endpoints}
    results["anomalies"] = {"ok": 0, "err": 0, "empty": 0, "ms": []}
    for dnum in pick:
        for e in endpoints:
            url = f"{BASE}/district/{dnum}/{e}"
            _probe(url, results[e])
        _probe(f"{BASE}/anomalies?district_number={dnum}&limit=50", results["anomalies"])
    out = {}
    for e, r in results.items():
        ms = r["ms"]
        out[e] = {"ok": r["ok"], "err": r["err"], "empty": r["empty"],
                  "p50_ms": int(np.median(ms)) if ms else None,
                  "p95_ms": int(np.percentile(ms, 95)) if ms else None}
    out["_sample"] = int(len(pick))
    return out


def _probe(url, acc):
    t = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            body = r.read()
        acc["ms"].append((time.monotonic() - t) * 1000)
        try:
            j = json.loads(body)
            empty = (isinstance(j, list) and not j) or \
                    (isinstance(j, dict) and not j.get("peers", j.get("turnarounds", j)))
            acc["empty" if empty else "ok"] += 1
        except Exception:
            acc["ok"] += 1
    except Exception:
        acc["err"] += 1


def data_completeness(df, latest):
    cur = df[df.year == latest]
    fields = {
        "enrollment": "fall_survey_enrollment",
        "revenue": "all_funds_total_operating_revenue",
        "spending": "all_funds_total_disbursements",
        "instruction": "all_funds_instruction_transfer_expend_fct11_95",
        "local_tax": "all_funds_local_tax_revenue_from_m_o",
    }
    out = {}
    for name, col in fields.items():
        if col in cur:
            miss = cur[col].isna().sum() + (cur[col] == 0).sum()
            out[name] = {"missing_or_zero": int(miss),
                         "pct": round(float(miss / len(cur) * 100), 1)}
    out["_districts"] = int(len(cur))
    return out


def main(csv_path="data/texas_finance_clean.csv"):
    df = pd.read_csv(csv_path, dtype={"district_number": str})
    latest = int(df.year.max())
    print(f"Monte Carlo audit — {len(df)} rows, latest year {latest}, seed {SEED}\n")

    print("1/4 archetype stability (bootstrap re-clustering)…")
    a = archetype_stability(df, latest)
    print(f"    mean stability {a['mean_stability']}, {a['pct_below_0.6']}% of districts unstable (<0.6)")

    print("2/4 anomaly threshold sensitivity…")
    t = threshold_sensitivity(df)
    print(f"    base {t['base_flag_events']} events; ±5pp jitter swings {t['swing_pct']}% (range {t['range']})")

    print("3/4 live API coverage (production)…")
    try:
        c = live_coverage(df, latest)
        for e in ["summary", "peers", "breakdown", "turnarounds", "anomalies"]:
            r = c[e]
            print(f"    /{e}: ok={r['ok']} empty={r['empty']} err={r['err']} p50={r['p50_ms']}ms p95={r['p95_ms']}ms")
    except Exception as exc:
        c = {"error": str(exc)}
        print(f"    live probe failed: {exc}")

    print("4/4 data completeness (latest year)…")
    dc = data_completeness(df, latest)
    for k, v in dc.items():
        if k != "_districts":
            print(f"    {k}: {v['pct']}% missing/zero")

    result = {"seed": SEED, "latest_year": latest,
              "archetype_stability": a, "threshold_sensitivity": t,
              "live_coverage": c, "data_completeness": dc}
    json.dump(result, open("docs/monte_carlo_audit.json", "w"), indent=2)
    print("\nSaved docs/monte_carlo_audit.json")
    return result


if __name__ == "__main__":
    main(*sys.argv[1:])
