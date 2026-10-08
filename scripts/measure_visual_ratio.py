"""Validate the public portal's auditable visual/prose geometry.

Only painted data marks and tight text ranges are scored. Plot wrappers, card
padding, and decorative diagrams never contribute visual area. Baseline and
prototype phases are observations; only the complete final matrix is a release
gate. Independent semantic review of every final annotated screenshot is
mandatory. The separate human and assistive-technology study remains an
unverified release gate until it is conducted.
"""
from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

FINAL_STATES = ("statewide", "dallas", "small", "charter", "compare", "unavailable")
FINAL_BROWSERS = ("chromium", "firefox")
FINAL_VIEWPORTS = ((1440, 900), (768, 1024), (390, 844))
FINAL_THEMES = ("light", "dark")
KNOWN_KINDS = {"visual", "prose"}
VISUAL_BOUNDS = {"svg-mark", "canvas-mark", "html-mark", "text-range"}
VISUAL_ROLES = {"data-mark", "necessary-label", "necessary-status"}


def load_document(path):
    path = Path(path)
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(path.read_text(encoding="utf-8"))


def area(rect):
    return max(0, rect["right"] - rect["left"]) * max(0, rect["bottom"] - rect["top"])


def union_area(rectangles):
    """Sweep-line union, so overlapping rectangles are counted once."""
    if not rectangles:
        return 0
    xs = sorted({x for rect in rectangles for x in (rect["left"], rect["right"])})
    total = 0
    for left, right in zip(xs, xs[1:]):
        spans = sorted(
            (rect["top"], rect["bottom"])
            for rect in rectangles
            if rect["left"] < right and rect["right"] > left
        )
        covered = 0
        end = None
        for top, bottom in spans:
            if end is None:
                start, end = top, bottom
            elif top > end:
                covered += end - start
                start, end = top, bottom
            else:
                end = max(end, bottom)
        if end is not None:
            covered += end - start
        total += (right - left) * covered
    return total


def _geometry(case, regions_key="regions"):
    errors = []
    visual, prose = [], []
    for region in case.get(regions_key, []):
        selector = region.get("selector", "?")
        kind = region.get("kind")
        if kind not in KNOWN_KINDS:
            errors.append(f"unclassified region: {selector}")
            continue
        try:
            positive_area = area(region) > 0
        except (KeyError, TypeError):
            positive_area = False
        opacity = region.get("opacity", 1)
        if not selector or not positive_area or not region.get("visible", False) or opacity <= 0:
            errors.append(f"invalid visible region: {selector}")
            continue
        if kind == "visual":
            if region.get("bounds_kind") not in VISUAL_BOUNDS:
                errors.append(f"visual region is not a tight mark/range: {selector}")
            if region.get("semantic_role") not in VISUAL_ROLES:
                errors.append(f"visual region lacks a data semantic: {selector}")
            visual.append(region)
        else:
            if region.get("bounds_kind") != "text-range":
                errors.append(f"prose region is not a tight text range: {selector}")
            prose.append(region)

    raw_visual_area = union_area(visual)
    prose_area = union_area(prose)
    overlap = raw_visual_area + prose_area - union_area(visual + prose)
    # Rectangle union uses floating-point browser coordinates; treat only a
    # geometric intersection, not sub-nanopixel cancellation noise, as overlap.
    if abs(overlap) < 1e-6:
        overlap = 0.0
    visual_area = max(0, raw_visual_area - overlap)  # prose precedence
    if overlap > 0:
        errors.append("contradictory visual/prose overlap")
    total = visual_area + prose_area
    share = visual_area / total if total else 0
    if not visual:
        errors.append("zero visual analytic area")
    if total and (share < .95 or prose_area / total > .05):
        errors.append("visual/prose ratio fails 95/5 target")
    return {
        "visual_area": visual_area,
        "prose_area": prose_area,
        "visual_share": share,
        "overlap_area": overlap,
        "errors": errors,
    }


def validate_case(case, require_review=False):
    errors = []
    warnings = []
    case_id = case.get("id")
    if case.get("status") == "na":
        if not case.get("reason"):
            errors.append("N/A needs an explicit reason")
        return {"id": case_id, "status": "NA", "errors": errors, "warnings": warnings}
    if case.get("status") != "measured":
        errors.append("case was not actually measured")
    for field in ("screenshot", "annotation", "initial_screenshot", "initial_annotation"):
        if not case.get(field):
            errors.append(f"missing {field}")
    for field in ("browser", "browser_version", "theme", "viewport"):
        if not case.get(field):
            errors.append(f"missing {field} evidence")
    if case.get("manifest_errors"):
        errors.extend(f"manifest: {message}" for message in case["manifest_errors"])
    if case.get("page_errors"):
        errors.append("uncaught page error")
    if case.get("renderer_warnings"):
        errors.append("renderer warning")
    if case.get("blocked_external_requests"):
        errors.append("unexpected external request")
    if case.get("state") == "compare" and case.get("comparison_selected") is not True:
        errors.append("comparison state was not selected through the UI")
    if case.get("state") == "unavailable" and not case.get("unavailable_artifact_graphics"):
        errors.append("unavailable state did not preserve artifact graphics")
    inventory = case.get("inventory")
    if not inventory:
        errors.append("empty visible analytic leaf inventory")
    elif any(not item.get("classification") for item in inventory):
        errors.append("inventory leaf lacks a classification")
    if case.get("unclassified"):
        errors.append("unclassified analytic content")
    for graphic in case.get("graphics", []):
        if graphic.get("visible") and graphic.get("data_marks", 0) <= 0:
            errors.append(f"visible graphic has no data marks: {graphic.get('selector', '?')}")

    full = _geometry(case)
    errors.extend(full.pop("errors"))
    initial = _geometry(case, "initial_regions")
    initial_errors = initial.pop("errors")
    if initial_errors:
        errors.append("initial viewport fails independently")
    if require_review and case.get("reviewed") is not True:
        errors.append("manual semantic review pending")
    elif case.get("reviewed") is not True:
        warnings.append("manual semantic review pending (observational phase)")

    return {
        "id": case_id,
        "status": "PASS" if not errors else "FAIL",
        **full,
        "initial": {"status": "PASS" if not initial_errors else "FAIL", **initial, "errors": initial_errors},
        "errors": errors,
        "warnings": warnings,
        "reviewed": case.get("reviewed") is True,
    }


def _expected_final_ids():
    for browser in FINAL_BROWSERS:
        for width, height in FINAL_VIEWPORTS:
            for theme in FINAL_THEMES:
                for state in FINAL_STATES:
                    yield (browser, state, width, height, theme)


def _case_identity(case):
    viewport = case.get("viewport") or {}
    return (
        case.get("browser"), case.get("state"),
        viewport.get("width"), viewport.get("height"), case.get("theme"),
    )


def validate(document, evidence_root=Path.cwd()):
    missing_metadata = [
        key for key in ("source_revision", "captured_at", "collector", "rubric_version")
        if not document.get(key)
    ]
    phases = document.get("phases") or {}
    phase_results = {}
    for phase_name in ("baseline", "prototype", "final"):
        phase = phases.get(phase_name)
        if phase is None:
            phase_results[phase_name] = {
                "status": "UNVERIFIED", "gate": phase_name == "final",
                "reason": "phase has no captured measurements", "results": [],
            }
            continue
        results = []
        for case in phase.get("cases", []):
            result = {"phase": phase_name, **validate_case(case, require_review=phase_name == "final")}
            for field in ("screenshot", "annotation", "initial_screenshot", "initial_annotation"):
                artifact = case.get(field)
                if artifact and not (evidence_root / artifact).is_file():
                    result["errors"].append(f"{field} file does not exist")
                    result["status"] = "FAIL"
            results.append(result)
        gate = phase_name == "final"
        if not results:
            status = "FAIL" if gate else "UNVERIFIED"
        elif all(result["status"] == "PASS" for result in results):
            status = "PASS"
        else:
            status = "FAIL" if gate else "OBSERVED_FAIL"
        phase_results[phase_name] = {
            "status": status, "gate": gate, "case_count": len(results), "results": results,
        }

    final_cases = phases.get("final", {}).get("cases", [])
    identities = [_case_identity(case) for case in final_cases]
    counts = Counter(identities)
    expected = set(_expected_final_ids())
    missing_final_cells = [list(item) for item in sorted(expected - set(identities))]
    duplicate_final_cells = [list(item) for item, count in sorted(counts.items()) if count > 1]
    unexpected_final_cells = [list(item) for item in sorted(set(identities) - expected)]
    final_gate_errors = []
    if missing_final_cells:
        final_gate_errors.append(f"missing {len(missing_final_cells)} required final cells")
    if duplicate_final_cells:
        final_gate_errors.append(f"duplicate {len(duplicate_final_cells)} final cells")
    if unexpected_final_cells:
        final_gate_errors.append(f"unexpected {len(unexpected_final_cells)} final cells")
    if missing_metadata:
        final_gate_errors.append("missing document metadata")
    if phase_results["final"]["status"] != "PASS":
        final_gate_errors.append("one or more final cases fail")

    return {
        "status": "PASS" if not final_gate_errors else "FAIL",
        "missing": missing_metadata,
        "phase_results": phase_results,
        "final_gate_errors": final_gate_errors,
        "missing_final_cells": missing_final_cells,
        "duplicate_final_cells": duplicate_final_cells,
        "unexpected_final_cells": unexpected_final_cells,
        "manual_review_required": True,
        "target": {"visual_share_min": .95, "prose_share_max": .05},
        "note": "Baseline/prototype are observations and never fail the final release gate.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("docs/evidence/visual/visual-ratio.json"))
    args = parser.parse_args()
    report = validate(load_document(args.input))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, separators=(",", ":")) + "\n", encoding="utf-8")
    summary = {
        "status": report["status"],
        "phases": {name: value["status"] for name, value in report["phase_results"].items()},
        "final_gate_errors": report["final_gate_errors"],
        "missing_final_cells": len(report["missing_final_cells"]),
    }
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
