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
    """The bug's signature: one twin present, the other silently gone."""
    missing = []
    for name, twins in _shared_names(rows).items():
        for t in twins:
            if t["has_boundary"].strip().lower() == "true" \
                    and t["district_number"] not in geo["d"]:
                missing.append(f'{t["district_number"]} {name} ({t["county"]})')
    assert not missing, "registry says these have a boundary, payload lacks it: " \
                        + "; ".join(missing)


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
    """A drifting count is how a stale flag hides a real change."""
    flagged = {r["district_number"] for r in rows
               if r["has_boundary"].strip().lower() == "true"}
    assert flagged == set(geo["d"]), (
        f"registry says {len(flagged)}, payload has {len(geo['d'])}; "
        f"only in registry: {sorted(flagged - set(geo['d']))[:5]}, "
        f"only in payload: {sorted(set(geo['d']) - flagged)[:5]}")


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
