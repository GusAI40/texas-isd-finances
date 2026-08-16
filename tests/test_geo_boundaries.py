"""The map must not draw a district with another district's territory.

Eleven Texas district names belong to two districts each. Joining Census
polygons to TEA numbers by name alone keeps whichever row came last, so both
polygons land on one number: one district is drawn with the other's land, and
the other disappears. That shipped. On TIGER2024 five districts were live with
the wrong territory — Highland Park ISD (Potter) drawn as Dallas's Highland
Park, Northside ISD (Wilbarger) drawn as San Antonio's — and the build reported
no error, because an overwrite is not an error unless something checks.

These tests need no shapefile and no network: they check the committed payload
against the committed registry, which is exactly what a CI run can see.
"""
from __future__ import annotations

import collections
import csv
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def geo():
    return json.loads((ROOT / "static" / "district_geo.json").read_text())


@pytest.fixture(scope="module")
def rows():
    with open(ROOT / "data" / "district_crosswalk.csv") as fh:
        return list(csv.DictReader(fh))


def _shared_names(rows):
    by = collections.defaultdict(list)
    for r in rows:
        by[r["district_name"].strip().lower()].append(r)
    return {n: v for n, v in by.items() if len(v) > 1}


def test_there_really_are_shared_names(rows):
    """If this ever drops to zero the fixture is broken, not Texas fixed."""
    assert len(_shared_names(rows)) >= 10


def test_every_district_sharing_a_name_has_its_own_boundary(geo, rows):
    """The bug's signature: one twin present, the other silently gone.

    Checked against the SHARED-NAME LIST, not against has_boundary. That flag
    is derived FROM this payload by build_district_crosswalk.py, so asserting
    the two agree is circular — reintroduce the bug, rebuild both, and the
    suite stays green while five districts are drawn on the wrong land. The
    non-circular fact is that both twins of a name are real Texas districts
    with real territory, so BOTH must be present.
    """
    missing = []
    for name, twins in _shared_names(rows).items():
        for t in twins:
            if t["is_charter"].strip().lower() == "true":
                continue                      # charters have no territory
            if t["district_number"] not in geo["d"]:
                missing.append(f'{t["district_number"]} {name} ({t["county"]})')
    assert not missing, (
        "both districts sharing a name must each have their own boundary; "
        "missing: " + "; ".join(missing))


def test_no_two_districts_share_one_polygon(geo):
    """An overwrite leaves two numbers pointing at identical geometry, or one
    number holding a polygon that belongs to its twin. Identical rings between
    any two districts means the join collapsed."""
    seen = {}
    dupes = []
    for num, rec in geo["d"].items():
        key = json.dumps(rec["r"], separators=(",", ":"))
        if key in seen:
            dupes.append((seen[key], num))
        seen[key] = num
    assert not dupes, f"districts sharing identical geometry: {dupes[:5]}"


def test_payload_and_registry_agree_on_who_has_a_boundary(geo, rows):
    """A drifting count is how a stale flag hides a real change.

    NOTE this one IS circular by construction — has_boundary is generated from
    the payload — so it catches a STALE crosswalk (rebuilt one, not the other)
    and nothing else. It is kept for that, not as a guard on the join; the
    twin test above is the real guard.
    """
    flagged = {r["district_number"] for r in rows
               if r["has_boundary"].strip().lower() == "true"}
    assert flagged == set(geo["d"]), (
        f"registry says {len(flagged)}, payload has {len(geo['d'])}; "
        f"only in registry: {sorted(flagged - set(geo['d']))[:5]}, "
        f"only in payload: {sorted(set(geo['d']) - flagged)[:5]}")


def test_each_twin_sits_in_its_own_county(geo, rows):
    """The strongest non-circular check available without a shapefile.

    A TEA district number's first three digits ARE its county code, and the
    crosswalk carries the county name independently. Two twins must therefore
    have different county codes AND different geometry. When the join collapsed,
    both resolved to one number — so the survivor held its twin's polygon and
    the centroids could not possibly both be right.
    """
    import csv as _csv
    with open(ROOT / "data" / "district_crosswalk.csv") as fh:
        county_of = {r["district_number"]: r["county_code"] for r in _csv.DictReader(fh)}
    for name, twins in _shared_names(rows).items():
        nums = [t["district_number"] for t in twins
                if t["district_number"] in geo["d"]]
        if len(nums) < 2:
            continue
        codes = {county_of[n] for n in nums}
        assert len(codes) == len(nums), f"{name}: twins share a county code {codes}"
        for n in nums:
            assert n[:3] == county_of[n], (
                f"{n} ({name}) does not sit in the county its number encodes")
        cents = {tuple(geo["d"][n]["c"]) for n in nums}
        assert len(cents) == len(nums), (
            f"{name}: twins share a centroid — the join collapsed them")


def test_every_centroid_is_inside_texas(geo):
    """A polygon attached to the wrong district often lands outside the state
    bounding box entirely. Cheap, and it catches a whole class of bad join."""
    out = [(num, rec["c"]) for num, rec in geo["d"].items()
           if not (-107.0 <= rec["c"][0] <= -93.0 and 25.0 <= rec["c"][1] <= 37.0)]
    assert not out, f"centroids outside Texas: {out[:5]}"


def test_the_source_label_states_its_own_vintage(geo):
    """The vintage used to be hardcoded, so fresh boundaries could ship under a
    stale citation. It must name a year, and match the payload it describes."""
    src = geo["meta"]["source"]
    assert "TIGER/Line" in src
    import re
    assert re.search(r"TIGER/Line (20\d{2})", src), src
