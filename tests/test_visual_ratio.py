from scripts.measure_visual_ratio import union_area, validate_case


def rect(kind, left=0, top=0, right=100, bottom=100, **extra):
    return {"selector": "#x", "kind": kind, "left": left, "top": top, "right": right, "bottom": bottom, "visible": True, **extra}


def test_union_does_not_double_count_overlap():
    assert union_area([rect("visual"), rect("visual", 50, 0, 150, 100)]) == 15000


def test_prose_in_visual_fails_instead_of_improving_score():
    result = validate_case({"id": "nested", "screenshot": "x", "annotation": "x", "regions": [rect("visual"), rect("prose", 10, 10, 20, 20)]})
    assert result["status"] == "FAIL"
    assert "contradictory" in result["errors"][0]


def test_hidden_and_empty_visuals_fail():
    hidden = validate_case({"id": "hidden", "screenshot": "x", "annotation": "x", "regions": [rect("visual", visible=False)]})
    empty = validate_case({"id": "empty", "screenshot": "x", "annotation": "x", "regions": [rect("visual", right=0)]})
    assert hidden["status"] == empty["status"] == "FAIL"


def test_na_requires_reason():
    assert validate_case({"id": "na", "status": "na"})["status"] == "NA"
    assert validate_case({"id": "na", "status": "na"})["errors"]
