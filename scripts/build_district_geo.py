"""Turn Census TIGER school-district polygons into a web-sized map payload.

Census publishes Texas district boundaries as a 27 MB shapefile keyed by NCES
codes. This site is keyed by TEA district numbers. So this script joins the two
by normalised name, simplifies the geometry hard enough to ship to a phone, and
writes static/district_geo.json.

No Mapbox, no tile server, no API key: the polygons are ours, the renderer is
our own canvas code, and "which district am I in?" is answered by
point-in-polygon in the browser, so a user's location never leaves their device.

Source: https://www2.census.gov/geo/tiger/TIGER2024/UNSD/tl_2024_48_unsd.zip
(public domain). Charter districts are absent by nature — they are not
geographic entities — which is why the payload records its own coverage.

Encoding
--------
Coordinates are quantised to 1e-4 degrees (~11 m, far finer than a state map
can show) and delta-encoded along each ring, which is what keeps a thousand
polygons inside a couple of megabytes. The client rebuilds them with a running
sum; see decodeRings() in static/geomap.html.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
from pathlib import Path

import shapefile

# Census spelling -> TEA spelling. Every one checked by hand against the TEA
# district list; nothing here is a fuzzy guess.
ALIASES = {
    "eagle mountain saginaw isd": "eagle mt saginaw isd",
    "fort davis isd": "ft davis isd",
    "fort hancock isd": "ft hancock isd",
    "fort sam houston isd": "ft sam houston isd",
    "goldthwaite cisd": "goldthwaite isd",
    "hamlin isd": "hamlin collegiate isd",
    "lapoyner isd": "lapoynor isd",
    "schertz cibolo universal city isd": "schertz cibolo u city isd",
    "west rusk county cisd": "west rusk county consolidated isd",
}
QUANT = 10000  # 1e-4 degrees


def norm(s: str) -> str:
    s = s.lower()
    for a, b in [("consolidated independent school district", "cisd"),
                 ("independent school district", "isd"),
                 ("common school district", "csd"),
                 ("municipal school district", "msd"),
                 ("school district", "sd")]:
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def load_counties(path):
    """Texas county polygons, for deciding which of two same-named districts a
    polygon actually is. Returns [(name, rings, bbox)]."""
    rr = shapefile.Reader(path)
    fl = [f[0] for f in rr.fields[1:]]
    out = []
    for rec, shp in zip(rr.records(), rr.shapes()):
        a = dict(zip(fl, rec))
        if a.get("STATEFP") != "48":
            continue
        parts = list(shp.parts) + [len(shp.points)]
        out.append((a["NAME"], [shp.points[x:y] for x, y in zip(parts, parts[1:])],
                    shp.bbox))
    if not out:
        raise SystemExit(f"no Texas counties found in {path!r}")
    return out


def _in_ring(pt, ring):
    x, y = pt
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if ((y1 > y) != (y2 > y)) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-18) + x1:
            inside = not inside
    return inside


def county_of(lon, lat, counties):
    for nm, rings, bb in counties:
        if not (bb[0] <= lon <= bb[2] and bb[1] <= lat <= bb[3]):
            continue
        if any(_in_ring((lon, lat), rg) for rg in rings):
            return nm
    return None


def rdp(pts, eps):
    """Ramer-Douglas-Peucker. Iterative, because Texas has rings with tens of
    thousands of vertices and recursion blows the stack on them."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        s, e = stack.pop()
        x1, y1 = pts[s]
        x2, y2 = pts[e]
        dx, dy = x2 - x1, y2 - y1
        denom = dx * dx + dy * dy
        worst, wi = -1.0, -1
        for i in range(s + 1, e):
            px, py = pts[i]
            if denom == 0:
                d = (px - x1) ** 2 + (py - y1) ** 2
            else:
                t = ((px - x1) * dx + (py - y1) * dy) / denom
                t = 0.0 if t < 0 else 1.0 if t > 1 else t
                d = (px - (x1 + t * dx)) ** 2 + (py - (y1 + t * dy)) ** 2
            if d > worst:
                worst, wi = d, i
        if worst > eps * eps and wi > 0:
            keep[wi] = True
            stack.append((s, wi))
            stack.append((wi, e))
    return [p for p, k in zip(pts, keep) if k]


def ring_area(pts) -> float:
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def encode(ring):
    """[(x,y), ...] -> flat delta-encoded ints."""
    out, px, py = [], 0, 0
    for x, y in ring:
        qx, qy = round(x * QUANT), round(y * QUANT)
        out.append(qx - px)
        out.append(qy - py)
        px, py = qx, qy
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--shapefile", required=True, help="tl_YYYY_48_unsd, no extension")
    ap.add_argument("--finance", required=True)
    ap.add_argument("--crosswalk", default="data/district_crosswalk.csv",
                    help="the district registry: carries the county that "
                         "separates two districts sharing one name")
    ap.add_argument("--counties", default=None,
                    help="TIGER county shapefile (no extension). Required "
                         "whenever any district name is shared.")
    ap.add_argument("--out", default="static/district_geo.json")
    ap.add_argument("--outcomes", default="static/outcomes_data.json",
                    help="merge the measures in so the map is one fetch, not two")
    ap.add_argument("--epsilon", type=float, default=0.004, help="simplify tolerance, degrees")
    ap.add_argument("--min-area", type=float, default=2e-5, help="drop rings smaller than this")
    args = ap.parse_args()

    # Eleven Texas district names belong to TWO districts each ("Edgewood ISD"
    # is both Bexar and Van Zandt). Keying a plain dict by name therefore keeps
    # only whichever row the file happened to mention last, and every polygon
    # carrying that name lands on that one number — so one district is drawn
    # with the OTHER's territory and the other gets nothing.
    #
    # That was not hypothetical: on TIGER2024 five districts already shipped
    # this way, including Highland Park ISD (Potter) drawn as Dallas's Highland
    # Park and Northside ISD (Wilbarger) drawn as San Antonio's. TIGER2025 adds
    # a polygon for the second twin of all eleven pairs, so the naive match
    # silently overwrites eleven times and still reports "unmatched: 0".
    #
    # So: candidates are keyed by name, and a shared name is resolved by the
    # county the polygon physically sits in — the same name+county key the bond
    # layer uses. A TEA district number's first three digits ARE its county
    # code, which is what makes the answer checkable against the state.
    tea = collections.defaultdict(list)
    for row in csv.DictReader(open(args.crosswalk)):
        tea[norm(row["district_name"])].append(
            (str(row["district_number"]).zfill(6), row["district_name"],
             row["county"].strip().lower()))

    shared = {n for n, v in tea.items() if len(v) > 1}
    counties = load_counties(args.counties) if args.counties else None
    if shared and counties is None:
        raise SystemExit(
            f"{len(shared)} district names are shared by two districts "
            f"({', '.join(sorted(shared)[:3])}...). Resolving them needs "
            "--counties (a TIGER county shapefile) so the polygon's own "
            "location decides. Refusing to guess: guessing is how five "
            "districts were drawn with the wrong territory.")

    # Fold the measures into the geometry: one request instead of two, and the
    # map can colour itself the moment it has the file.
    measures = {}
    op = Path(args.outcomes)
    if op.exists():
        od = json.loads(op.read_text())
        for num, rec in od["districts"].items():
            m = rec.get("measures", {})
            measures[num] = {
                "t": (m.get("teacher_turnover_pct") or [None])[0],
                "p": rec.get("need", {}).get("pct_econ_disadv"),
                "s": rec.get("spend_per_student"),
                "g": (rec.get("expectation") or {}).get("gap"),
                "e": rec.get("students"),
            }
        print(f"measures merged   : {len(measures):,} districts")

    r = shapefile.Reader(args.shapefile)
    flds = [f[0] for f in r.fields[1:]]
    out, unmatched = {}, []
    kept_pts = raw_pts = 0
    total_polys = len(r.shapes())
    dropped_no_ring = 0

    ambiguous = []
    for rec, shp in zip(r.records(), r.shapes()):
        attrs = dict(zip(flds, rec))
        key = norm(attrs["NAME"])
        key = ALIASES.get(key, key)
        cands = tea.get(key)
        if not cands:
            unmatched.append(attrs["NAME"])
            continue
        if len(cands) == 1:
            num, name, _ = cands[0]
        else:
            # Shared name: let the polygon's own internal point pick the county.
            here = county_of(float(attrs["INTPTLON"]), float(attrs["INTPTLAT"]),
                             counties)
            pick = [c for c in cands if here and c[2] == here.lower()]
            if len(pick) != 1:
                ambiguous.append((attrs["NAME"], here,
                                  [c[0] for c in cands]))
                continue
            num, name, _ = pick[0]
        if num in out:
            # Two polygons resolved to one district. Never silently keep the
            # last one — that is the bug this whole block exists to kill.
            ambiguous.append((attrs["NAME"], "duplicate resolution", [num]))
            continue

        parts = list(shp.parts) + [len(shp.points)]
        rings = []
        for a, b in zip(parts, parts[1:]):
            ring = shp.points[a:b]
            raw_pts += len(ring)
            if len(ring) < 4 or ring_area(ring) < args.min_area:
                continue          # islands and slivers invisible at state scale
            simp = rdp(ring, args.epsilon)
            if len(simp) >= 4:
                kept_pts += len(simp)
                rings.append(encode(simp))
        if not rings:
            dropped_no_ring += 1
            continue
        xs = [p[0] for p in shp.points]
        ys = [p[1] for p in shp.points]
        out[num] = {
            "n": name,
            "c": [round(float(attrs["INTPTLON"]), 4), round(float(attrs["INTPTLAT"]), 4)],
            "b": [round(min(xs), 4), round(min(ys), 4), round(max(xs), 4), round(max(ys), 4)],
            "r": rings,
            "m": measures.get(num),
        }

    # Read the vintage off the file we were actually handed. It used to be a
    # hardcoded "2024", which meant a rebuild on a newer shapefile would ship
    # fresh boundaries under a stale citation — the reader would be told the
    # wrong year by an artefact that was otherwise correct. Refuse rather than
    # guess: a wrong provenance label is worse than a failed build, because it
    # looks checked.
    vm = re.search(r"tl_(\d{4})_48_unsd", Path(args.shapefile).name)
    if not vm:
        raise SystemExit(
            f"cannot read a TIGER vintage from --shapefile {args.shapefile!r}; "
            "expected a name like tl_2025_48_unsd. Refusing to label the "
            "output with a year that is not the file's own.")
    vintage = vm.group(1)

    payload = {
        "meta": {
            "quant": QUANT,
            "districts": len(out),
            "epsilon_deg": args.epsilon,
            "source": (f"US Census TIGER/Line {vintage}, Unified School "
                       "Districts, Texas (public domain)"),
            "note": ("Charter districts have no geographic boundary and are absent by nature, "
                     "not by omission."),
            "unmatched_polygons": unmatched,
        },
        "d": out,
    }
    p = Path(args.out)
    p.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"districts written : {len(out):,}")
    print(f"unmatched polygons: {len(unmatched)}  {unmatched}")
    if ambiguous:
        print(f"UNRESOLVED shared names: {len(ambiguous)}")
        for nm, where, nums in ambiguous:
            print(f"   {nm} (sits in {where}) could be {nums}")
    # Every polygon must land somewhere nameable. Silence here is what let five
    # districts ship with another district's territory.
    seen = len(out) + len(unmatched) + len(ambiguous) + dropped_no_ring
    if seen != total_polys:
        raise SystemExit(
            f"accounting failed: {total_polys} polygons in, but only {seen} "
            f"accounted for ({len(out)} written, {len(unmatched)} unmatched, "
            f"{len(ambiguous)} ambiguous, {dropped_no_ring} with no ring left). "
            "A polygon vanished without being named.")
    print(f"vertices          : {raw_pts:,} -> {kept_pts:,} "
          f"({100*kept_pts/raw_pts:.1f}% kept, epsilon {args.epsilon}deg)")
    print(f"payload           : {p} [{p.stat().st_size/1024:.0f} KB]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
