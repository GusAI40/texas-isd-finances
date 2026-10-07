import gzip
import json

import pytest

from scripts.measure_visual_ratio import load_document, union_area, validate_case


def rect(kind="visual", left=0, top=0, right=100, bottom=100, **extra):
    defaults = {
        "selector": "#x",
        "kind": kind,
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "visible": True,
        "opacity": 1,
        "bounds_kind": "html-mark" if kind == "visual" else "text-range",
        "semantic_role": "data-mark" if kind == "visual" else "narrative",
    }
    return {**defaults, **extra}


def case(regions=None, initial_regions=None, **extra):
    regions = regions if regions is not None else [rect()]
    return {
        "id": "fixture",
        "status": "measured",
        "screenshot": "full.jpg",
        "annotation": "full-annotated.jpg",
        "initial_screenshot": "initial.jpg",
        "initial_annotation": "initial-annotated.jpg",
        "browser": "chromium",
        "browser_version": "1",
        "theme": "light",
        "viewport": {"width": 1440, "height": 900},
        "regions": regions,
        "initial_regions": initial_regions if initial_regions is not None else regions,
        "inventory": [{"selector": "#x", "classification": "visual"}],
        "unclassified": [],
        "graphics": [{"selector": "#plot", "visible": True, "data_marks": 1}],
        "reviewed": True,
        **extra,
    }


def test_union_does_not_double_count_overlap():
    assert union_area([rect(), rect(left=50, right=150)]) == 15000


def test_nested_prose_gets_precedence_and_fails():
    result = validate_case(case([rect(), rect("prose", 10, 10, 20, 20)]))
    assert result["status"] == "FAIL"
    assert result["visual_area"] == 9900
    assert "contradictory visual/prose overlap" in result["errors"]


def test_padded_card_cannot_claim_its_outer_box_as_visual():
    padded = rect(bounds_kind="element-box", semantic_role="data-mark")
    result = validate_case(case([padded]))
    assert result["status"] == "FAIL"
    assert any("not a tight mark/range" in error for error in result["errors"])


def test_enlarged_empty_plot_has_no_visual_credit():
    empty_wrapper = rect(bounds_kind="element-box", semantic_role="plot-wrapper", right=2000, bottom=1200)
    result = validate_case(case([empty_wrapper], graphics=[{"selector": "#blank", "visible": True, "data_marks": 0}]))
    assert result["status"] == "FAIL"
    assert any("no data marks" in error for error in result["errors"])
    assert any("lacks a data semantic" in error for error in result["errors"])


def test_hidden_and_zero_opacity_visuals_fail():
    hidden = validate_case(case([rect(visible=False)]))
    transparent = validate_case(case([rect(opacity=0)]))
    assert hidden["status"] == transparent["status"] == "FAIL"


def test_missing_annotation_fails():
    fixture = case()
    fixture.pop("annotation")
    result = validate_case(fixture)
    assert result["status"] == "FAIL"
    assert "missing annotation" in result["errors"]


def test_lower_page_visual_cannot_compensate_for_prose_heavy_first_view():
    full = [rect(right=1000, bottom=1000)]
    initial = [rect(right=10, bottom=10), rect("prose", 20, 0, 120, 100)]
    result = validate_case(case(full, initial))
    assert result["visual_share"] == 1
    assert result["initial"]["status"] == "FAIL"
    assert "initial viewport fails independently" in result["errors"]


def test_null_or_missing_status_cannot_be_counted_as_visual():
    missing = rect(bounds_kind="text-range", semantic_role="missing-status")
    result = validate_case(case([missing]))
    assert result["status"] == "FAIL"
    assert any("lacks a data semantic" in error for error in result["errors"])


def test_unknown_inventory_and_manifest_entries_fail():
    fixture = case(
        inventory=[{"selector": "#known", "classification": "visual"}, {"selector": "#unknown"}],
        unclassified=[{"selector": "#unknown", "text": "Visible leaf"}],
        manifest_errors=["required analytic root missing: #dash"],
    )
    result = validate_case(fixture)
    assert result["status"] == "FAIL"
    assert "unclassified analytic content" in result["errors"]
    assert any(error.startswith("manifest:") for error in result["errors"])


def test_final_case_requires_positive_manual_review():
    result = validate_case(case(reviewed=False), require_review=True)
    assert result["status"] == "FAIL"
    assert "manual semantic review pending" in result["errors"]


def test_na_requires_reason_and_never_becomes_pass():
    assert validate_case({"id": "na", "status": "na", "reason": "synthetic missing edge"})["status"] == "NA"
    missing_reason = validate_case({"id": "na", "status": "na"})
    assert missing_reason["status"] == "NA"
    assert missing_reason["errors"]


def test_plain_and_gzip_measurements_round_trip_identically(tmp_path):
    document = {"phases": {"final": {"cases": [{"id": "one"}]}}}
    plain = tmp_path / "measurements.json"
    compressed = tmp_path / "measurements.json.gz"
    payload = json.dumps(document).encode()
    plain.write_bytes(payload)
    compressed.write_bytes(gzip.compress(payload))
    assert load_document(plain) == load_document(compressed) == document


def test_truncated_gzip_measurements_are_rejected(tmp_path):
    compressed = tmp_path / "measurements.json.gz"
    compressed.write_bytes(gzip.compress(b'{"phases":{}}')[:-4])
    with pytest.raises((EOFError, OSError)):
        load_document(compressed)
