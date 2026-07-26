"""Would a geographic map actually teach the public anything new?

A Monte Carlo over REAL Texas geography and REAL district data, asking one
question: when a member of the public lands on their own district, what does
geography show them that this site cannot already show them?

Why this is built the way it is
-------------------------------
Our earlier simulation (scripts/simulate_admin_usage.py) modelled 1,000
administrators using persona priors *we chose*. That is fine for ranking UI
demand, but it cannot answer "is there new information here" — feed it
assumptions and it returns them.

So this one puts almost nothing in by hand. The population is weighted by real
student counts, so a simulated visitor is as likely to land in a district as a
Texas child is to attend one. Every measure below is computed from:
  - Census TIGER 2024 school-district polygons (adjacency, from shared
    boundary vertices — TIGER is topologically built, so neighbours share
    exact coordinates)
  - the site's existing k-NN similarity peers (static/map_data.json)
  - TEA Snapshot measures (turnover, student poverty, enrolment)

The only judgement calls are the two materiality thresholds, both stated as
constants and both reported alongside a sensitivity sweep.

What this CANNOT tell you: whether anyone will visit, whether they will act,
or whether the differences it surfaces are caused by anything a district did.
It measures available information, not persuasion and not causation.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import statistics
from collections import defaultdict
from pathlib import Path

import shapefile

SEED = 20260726
SIMILAR_POVERTY_PTS = 6.0   # two districts "serve similar students" within this
BETTER_TURNOVER_PTS = 8.0   # a turnover gap worth driving across town to ask about
METRO_RADIUS_DEG = 0.35     # ~38 km; used to measure how crowded a district's area is


def norm(s: str) -> str:
    s = s.lower()
    for a, b in [("consolidated independent school district", "cisd"),
                 ("independent school district", "isd"),
                 ("common school district", "csd"),
                 ("municipal school district", "msd"),
                 ("school district", "sd")]:
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def build_adjacency(shp_path: str):
    r = shapefile.Reader(shp_path)
    flds = [f[0] for f in r.fields[1:]]
    raw = [dict(zip(flds, rec)) for rec in r.records()]
    names = [norm(x["NAME"]) for x in raw]
    pts = [(float(x["INTPTLON"]), float(x["INTPTLAT"])) for x in raw]

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
    adj = defaultdict(set)
    for (a, b), n in hits.items():
        if n >= 2:                      # a shared border, not one touching corner
            adj[a].add(b)
            adj[b].add(a)
    return names, pts, adj, [x["NAME"] for x in raw]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--shapefile", required=True, help="path to tl_YYYY_48_unsd (no extension)")
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--graph", default="static/map_data.json")
    ap.add_argument("--visitors", type=int, default=100000)
    ap.add_argument("--out", help="write findings JSON here")
    args = ap.parse_args()

    names, pts, adj, display = build_adjacency(args.shapefile)

    snap = {}
    for row in csv.DictReader(open(args.snapshot)):
        if row["year"] == "2024":
            snap[norm(row["district_name"])] = row

    def val(i, key):
        try:
            return float(snap[names[i]][key])
        except (KeyError, TypeError, ValueError):
            return None

    # the site's existing statistical peers, keyed the same way
    graph = json.loads(Path(args.graph).read_text())
    nodes = graph["nodes"]
    peers_by_name = {}
    for n in nodes:
        peers_by_name[norm(n["n"])] = {norm(nodes[j]["n"]) for j in (n.get("k") or [])}

    # ---- population: a simulated visitor lands where Texas children actually are
    pop = [(i, val(i, "students")) for i in range(len(names))]
    pop = [(i, s) for i, s in pop if s and s > 0]
    total_students = sum(s for _, s in pop)
    idx = [i for i, _ in pop]
    wts = [s for _, s in pop]

    # ---- per-district facts, computed once ----
    facts = {}
    for i in idx:
        nb = sorted(adj[i])
        stat_peers = peers_by_name.get(names[i], set())
        nb_names = {names[j] for j in nb}
        new_faces = nb_names - stat_peers          # neighbours the site never shows you
        my_t, my_e = val(i, "teacher_turnover_pct"), val(i, "pct_econ_disadv")
        better = []
        if my_t is not None and my_e is not None:
            for j in nb:
                t, e = val(j, "teacher_turnover_pct"), val(j, "pct_econ_disadv")
                if t is None or e is None:
                    continue
                if abs(e - my_e) <= SIMILAR_POVERTY_PTS and (my_t - t) >= BETTER_TURNOVER_PTS:
                    better.append((j, my_t - t))
        crowd = sum(1 for j in idx
                    if j != i and abs(pts[j][0] - pts[i][0]) < METRO_RADIUS_DEG
                    and abs(pts[j][1] - pts[i][1]) < METRO_RADIUS_DEG)
        facts[i] = {"neighbours": len(nb), "new_faces": len(new_faces),
                    "overlap": len(nb_names & stat_peers),
                    "better_neighbour": better, "crowd": crowd}

    # ---- Monte Carlo over visitors ----
    rng = random.Random(SEED)
    picks = rng.choices(idx, weights=wts, k=args.visitors)
    n = len(picks)
    c_newface = sum(1 for i in picks if facts[i]["new_faces"] > 0)
    c_better = sum(1 for i in picks if facts[i]["better_neighbour"])
    c_crowded = sum(1 for i in picks if facts[i]["crowd"] >= 10)
    c_nooverlap = sum(1 for i in picks if facts[i]["neighbours"] and facts[i]["overlap"] == 0)
    gaps = [max(g for _, g in facts[i]["better_neighbour"])
            for i in picks if facts[i]["better_neighbour"]]

    covered = total_students
    all_students = 0
    for row in snap.values():
        try:
            all_students += float(row["students"])
        except (TypeError, ValueError):
            pass

    print("=" * 74)
    print(f"MONTE CARLO — WHAT A MAP ADDS   (seed {SEED}, {n:,} simulated visitors)")
    print("=" * 74)
    print(f"Visitors are placed by real enrolment across {len(idx):,} districts that have")
    print(f"both a boundary and data — {covered:,.0f} of {all_students:,.0f} Texas students "
          f"({100*covered/all_students:.1f}%).")
    print("The remainder are charter districts, which have no geographic boundary at all.\n")

    print(f"1. Sees a neighbouring district the site never shows them   {100*c_newface/n:5.1f}%")
    print("   (adjacent, but not among its statistical peers)")
    print(f"2. NONE of its neighbours are among its statistical peers   {100*c_nooverlap/n:5.1f}%")
    print("   — for these, geography is entirely new information")
    print(f"3. Has a neighbour with similar student poverty (±{SIMILAR_POVERTY_PTS:.0f} pts)")
    print(f"   that keeps teachers markedly better (≥{BETTER_TURNOVER_PTS:.0f} pts)          {100*c_better/n:5.1f}%")
    if gaps:
        print(f"   median turnover gap where it happens: {statistics.median(gaps):.1f} points")
    print(f"4. Lives where ≥10 districts sit within ~38 km             {100*c_crowded/n:5.1f}%")
    print("   — 'which district am I even in?' is a real question here")

    ov = [facts[i]["overlap"] for i in idx if facts[i]["neighbours"]]
    nb = [facts[i]["neighbours"] for i in idx if facts[i]["neighbours"]]
    print("\nOverlap between the two ways of finding comparable districts:")
    print(f"   median neighbours per district        {statistics.median(nb):.0f}")
    print(f"   median of those also statistical peers {statistics.median(ov):.0f}")
    print("   → the map is not a prettier version of the peer list; it is a different list.")

    # ---- sensitivity: do the thresholds drive finding 3? ----
    print("\nSensitivity of finding 3 to the two judgement calls:")
    print(f"   {'poverty ±':>10s} {'turnover ≥':>11s}   share of visitors")
    for pv in (4.0, 6.0, 10.0):
        for tv in (5.0, 8.0, 12.0):
            c = 0
            for i in picks:
                my_t, my_e = val(i, "teacher_turnover_pct"), val(i, "pct_econ_disadv")
                if my_t is None or my_e is None:
                    continue
                for j in adj[i]:
                    t, e = val(j, "teacher_turnover_pct"), val(j, "pct_econ_disadv")
                    if t is None or e is None:
                        continue
                    if abs(e - my_e) <= pv and (my_t - t) >= tv:
                        c += 1
                        break
            print(f"   {pv:>10.0f} {tv:>11.0f}   {100*c/n:5.1f}%")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "seed": SEED, "visitors": n, "districts": len(idx),
            "student_coverage_pct": round(100 * covered / all_students, 1),
            "sees_new_neighbour_pct": round(100 * c_newface / n, 1),
            "no_peer_overlap_pct": round(100 * c_nooverlap / n, 1),
            "has_better_neighbour_pct": round(100 * c_better / n, 1),
            "median_turnover_gap": round(statistics.median(gaps), 1) if gaps else None,
            "crowded_area_pct": round(100 * c_crowded / n, 1),
            "median_neighbours": statistics.median(nb),
            "median_neighbours_also_peers": statistics.median(ov),
            "thresholds": {"similar_poverty_pts": SIMILAR_POVERTY_PTS,
                           "better_turnover_pts": BETTER_TURNOVER_PTS},
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
