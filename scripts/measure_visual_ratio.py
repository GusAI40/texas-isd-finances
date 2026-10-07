"""Validate auditable visual/prose geometry captured by the browser harness.

The script deliberately scores rectangles, not CSS classes.  It is a guard
against padding a prose card or an empty plot and calling it a visualization.
Human review of screenshots and classifications is still required.
"""
import argparse
import json
from pathlib import Path


def area(rect):
    return max(0, rect["right"] - rect["left"]) * max(0, rect["bottom"] - rect["top"])


def union_area(rectangles):
    """Sweep-line union, so overlapping regions are never double-counted."""
    xs = sorted({x for r in rectangles for x in (r["left"], r["right"])})
    total = 0
    for left, right in zip(xs, xs[1:]):
        spans = sorted((r["top"], r["bottom"]) for r in rectangles if r["left"] < right and r["right"] > left)
        covered = 0
        end = None
        for top, bottom in spans:
            if end is None:
                start, end = top, bottom
            elif top > end:
                covered += end - start; start, end = top, bottom
            else:
                end = max(end, bottom)
        if end is not None:
            covered += end - start
        total += (right - left) * covered
    return total


def validate_case(case):
    errors = []
    if not case.get("screenshot") or not case.get("annotation"):
        errors.append("missing screenshot or annotation")
    if case.get("status") == "na":
        if not case.get("reason"):
            errors.append("N/A needs an explicit reason")
        return {"id": case.get("id"), "status": "NA", "errors": errors}
    if case.get("status") and case.get("status") != "measured":
        errors.append("case was not actually measured")
    if case.get("status") == "measured" and (not case.get("browser") or not case.get("browser_version") or not case.get("theme")):
        errors.append("missing browser/version/theme evidence")
    if case.get("unclassified"):
        errors.append("unclassified analytic content")
    regions = case.get("regions", [])
    if not regions:
        errors.append("zero analytic area")
    visual, prose = [], []
    known = {"visual", "prose", "excluded"}
    for region in regions:
        label = region.get("kind")
        if label not in known:
            errors.append(f"unclassified region: {region.get('selector', '?')}")
            continue
        if label != "excluded" and (not region.get("selector") or area(region) <= 0 or not region.get("visible", True)):
            errors.append(f"invalid visible region: {region.get('selector', '?')}")
        if label == "visual": visual.append(region)
        elif label == "prose": prose.append(region)
    # Narrative nested in a visual has precedence. Treating the overlap as
    # prose prevents a chart wrapper from laundering its explanatory paragraph.
    v = union_area(visual)
    p = union_area(prose)
    overlap = v + p - union_area(visual + prose)
    if overlap > 0:
        errors.append("contradictory visual/prose overlap")
    total = v + p
    ratio = v / total if total else 0
    if not errors and (ratio < .95 or p / total > .05):
        errors.append("visual/prose ratio fails 95/5 target")
    result = {"id": case.get("id"), "status": "PASS" if not errors else "FAIL", "visual_area": v, "prose_area": p, "visual_share": ratio, "errors": errors, "exclusions": case.get("exclusions", [])}
    if "initial_regions" in case:
        initial_case = {**case, "regions": case["initial_regions"], "unclassified": case.get("unclassified", [])}
        initial_case.pop("initial_regions", None)
        initial = validate_case(initial_case)
        result["initial"] = initial
        if initial["status"] != "PASS":
            result["status"] = "FAIL"
            result["errors"].append("initial viewport fails independently")
    return result


def validate(document):
    required = ("source_revision", "captured_at", "collector")
    missing = [key for key in required if not document.get(key)]
    phases = document.get("phases")
    if phases:
        flattened = [(phase, case) for phase, value in phases.items() for case in value.get("cases", [])]
        results = []
        for phase, case in flattened:
            result = {"phase": phase, **validate_case(case)}
            if not Path(case.get("screenshot", "")).exists() or not Path(case.get("annotation", "")).exists():
                result["errors"].append("screenshot or annotation file does not exist")
                result["status"] = "FAIL"
            results.append(result)
        required_phases = {"baseline", "prototype", "final"}
        missing_phases = sorted(required_phases - set(phases))
    else:
        results = [validate_case(case) for case in document.get("cases", [])]
        missing_phases = ["baseline", "prototype", "final"]
    measured = [r for r in results if r["status"] == "PASS"]
    return {"status": "PASS" if not missing and not missing_phases and measured and all(r["status"] == "PASS" for r in results) else "FAIL", "missing": missing, "missing_phases": missing_phases, "results": results,
            "manual_review_required": True, "target": {"visual_share_min": .95, "prose_share_max": .05}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("docs/evidence/visual/visual-ratio.json"))
    args = parser.parse_args()
    report = validate(json.loads(args.input.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
