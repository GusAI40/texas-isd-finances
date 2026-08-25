#!/usr/bin/env python3
"""One page that says what this system actually holds.

Twenty committed artefacts, 87 routes, two database views and a warehouse table
of 140 columns had accumulated with no single place that says what is in them.
That is how a project ends up publishing a figure nobody can find and holding
fourteen columns nobody knew were there.

**Generated, never hand-written.** A hand-written dictionary is accurate on the
day it is written and wrong by the next release, and a dictionary that is wrong
is worse than none because people trust it. Everything below is read out of the
real files at build time: the artefacts are opened and walked, the routes are
parsed from `src/api.py`, the view columns are parsed from the SQL. If a field
is renamed, this changes on the next build or it fails.

What it deliberately does NOT do: describe fields it cannot see. Where a human
explanation exists in the payload (`what_it_is`, `limits`, `label`) it is
quoted; where none exists the field is listed with its type and an example and
left unexplained rather than given a guess.

Usage:
    python scripts/build_data_dictionary.py
    python scripts/build_data_dictionary.py --html /tmp/registry.html

`tests/test_data_dictionary.py` enforces all of the above: every published file
must have a plain-English entry and a group, the builder must still read the
real files, and the committed markdown must equal a fresh run.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"

# What each artefact is FOR, in one sentence a non-engineer can read. This is
# the only hand-written part of the file, and it is checked: a test fails the
# build if an artefact appears in static/ with no entry here, so the dictionary
# cannot silently omit a layer.
PURPOSE = {
    "economics_data.json": (
        "What you pay and where it goes",
        "Tax bill on a $300,000 home, what leaves under recapture, the split "
        "between teaching, buildings and debt, and which similar districts do "
        "better. One year, every district."),
    "spending_detail.json": (
        "Where the operating dollar actually goes",
        "All 16 PEIMS function codes (buses, meals, counsellors, "
        "administration), 8 program codes (special education, bilingual, "
        "athletics) and 4 object codes (payroll, supplies). Per district."),
    "tax_history.json": (
        "What the tax rate has done since 2009",
        "Per-district rate and taxable value, 2009-2024, with the "
        "decomposition that says whether a bill rose because of the rate or "
        "because of property values."),
    "trend_data.json": (
        "Seventeen years of direction",
        "Six measures per district, fiscal 2009-2025, in constant dollars, "
        "each against the state's own line."),
    "outcomes_data.json": (
        "What the money bought",
        "Teacher turnover, experience and salary, class size, attendance, "
        "graduation and STAAR, each against structural peers and against what "
        "the district's demographics predict."),
    "campus_data.json": (
        "What the district rating hides",
        "Every rated campus with its letter grade and score, so a district's "
        "average can be checked against the schools inside it."),
    "campus_performance.json": (
        "STAAR by school, and by student group",
        "What students actually scored, by subject for 8,264 campuses, and by "
        "15 student groups for every district. Plus per-campus teacher "
        "experience, tenure and degree mix."),
    "equity_data.json": (
        "How low-income students do",
        "District STAAR for economically disadvantaged students, benchmarked "
        "against poor students statewide rather than against the local gap."),
    "bond_data.json": (
        "Every school bond election since 1958",
        "4,992 decided propositions with dates, amounts, purpose and vote "
        "counts, matched to districts."),
    "debt_data.json": (
        "What is still owed",
        "Principal and unpaid interest outstanding per district, the year it "
        "clears, and which districts carry capital appreciation bonds."),
    "forensic_data.json": (
        "Four questions Texas answers in four incompatible files",
        "What sits outside the operating total, who pays, what the ballot "
        "promised, and where results landed against what need predicts."),
    "national_data.json": (
        "Texas against the rest of the country",
        "Census F-33 per-pupil spending for every state and every US district "
        "with 500+ students, with each Texas district's national percentile."),
    "erate_data.json": (
        "Federal internet money",
        "E-Rate funding committed and disbursed per district — money paid to "
        "vendors, so it appears in no PEIMS file."),
    "takeover_data.json": (
        "Did the HISD takeover change results?",
        "Difference-in-differences against 13 districts matched on "
        "pre-takeover size and poverty."),
    "district_geo.json": (
        "District boundaries",
        "Census TIGER polygons for 1,016 districts, joined to TEA numbers by "
        "the county the polygon physically sits in."),
    "map_data.json": (
        "Every district placed on two axes",
        "Coordinates for the seating-chart view, from a principal-components "
        "reduction of district characteristics."),
    "fallback_index.json": (
        "The site works with the database switched off",
        "District names, numbers and a dated statewide snapshot, so the "
        "picker, search and headline figure survive an outage."),
    "forensic_quality.json": (
        "Checks on the data itself",
        "Benford's-law tests, reconciliation identities, and districts paying "
        "debt service with no voter-approved bond on record."),
    "source_fingerprint.json": (
        "Proof of which file everything came from",
        "SHA-256, byte count and per-year statewide sums of the cleaned source "
        "CSV, so any figure can be traced to an exact file."),
    "isd_briefing.json": (
        "District news",
        "Headlines resolved to districts, refreshed daily by a cron job."),
}

SKIP_ROUTES = ("/ops/", "/api/outreach/", "/px/", "/feedback", "/track")

# Grouped by the QUESTION each file answers, because that is how someone
# looking for a number thinks. Ordering by filename would be alphabetical
# trivia; ordering by size would be an accident of the source.
GROUPS = [
    ("Money", "What is spent, what is paid, and where it goes",
     ["economics_data.json", "spending_detail.json", "tax_history.json",
      "trend_data.json"]),
    ("Results", "What the money bought",
     ["outcomes_data.json", "campus_performance.json", "campus_data.json",
      "equity_data.json", "takeover_data.json"]),
    ("Obligations", "What is owed, and what voters agreed to",
     ["debt_data.json", "bond_data.json"]),
    ("Context", "How a district compares, and what else reaches it",
     ["national_data.json", "erate_data.json", "forensic_data.json",
      "forensic_quality.json"]),
    ("Plumbing", "Files the site needs but a reader never asks for",
     ["district_geo.json", "map_data.json", "fallback_index.json",
      "source_fingerprint.json", "isd_briefing.json"]),
]


def walk(node: Any, prefix: str = "", depth: int = 0, out: dict | None = None) -> dict:
    """Field paths with their type and one real example value."""
    out = {} if out is None else out
    if depth > 3:
        return out
    if isinstance(node, dict):
        for k, v in node.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                out[path] = {"type": "object", "keys": len(v)}
                walk(v, path, depth + 1, out)
            elif isinstance(v, list):
                out[path] = {"type": "list", "length": len(v)}
                if v and isinstance(v[0], dict):
                    walk(v[0], f"{path}[]", depth + 1, out)
                elif v:
                    out[path]["example"] = str(v[0])[:40]
            else:
                out[path] = {"type": type(v).__name__,
                             "example": str(v)[:60] if v is not None else None}
    return out


def describe_artifact(path: Path) -> dict:
    blob = json.loads(path.read_text())
    meta = blob.get("meta", {}) if isinstance(blob, dict) else {}
    records = blob.get("districts") or blob.get("d") or {}
    sample_key = None
    sample: Any = None
    if isinstance(records, dict) and records:
        sample_key = "057905" if "057905" in records else next(iter(records))
        sample = records[sample_key]
    elif isinstance(records, list) and records:
        sample = records[0]

    title, blurb = PURPOSE.get(path.name, (path.stem.replace("_", " ").title(), ""))
    return {
        "file": path.name,
        "title": title,
        "what_it_is": blurb,
        "bytes": path.stat().st_size,
        "records": len(records) if hasattr(records, "__len__") else None,
        "sample_district": sample_key,
        "source": meta.get("source"),
        "publisher": meta.get("publisher"),
        "year": meta.get("year") or meta.get("fiscal_year") or meta.get("last_year"),
        "first_year": meta.get("first_year"),
        "limits": meta.get("limits") or [],
        "fields": walk(sample) if sample is not None else {},
        "top_level": sorted(blob.keys()) if isinstance(blob, dict) else [],
    }


def routes() -> list[dict]:
    """Public GET routes, parsed from the source rather than listed by hand."""
    src = (ROOT / "src" / "api.py").read_text()
    tree = ast.parse(src)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                continue
            if dec.func.attr not in ("get", "post"):
                continue
            if not dec.args or not isinstance(dec.args[0], ast.Constant):
                continue
            p = dec.args[0].value
            if not isinstance(p, str) or any(p.startswith(s) for s in SKIP_ROUTES):
                continue
            doc = ast.get_docstring(node) or ""
            out.append({
                "method": dec.func.attr.upper(),
                "path": p,
                "summary": doc.strip().split("\n")[0] if doc else "",
            })
    return sorted(out, key=lambda r: r["path"])


def view_columns() -> dict[str, list[str]]:
    sql = (ROOT / "sql" / "create_tables.sql").read_text()
    out: dict[str, list[str]] = {}
    for name in ("v_finance_summary",):
        if f"VIEW public.{name} AS" not in sql:
            continue
        body = sql.split(f"VIEW public.{name} AS")[1].split("FROM public.")[0]
        cols = re.findall(r"(?:AS\s+|^\s{4})([a-z_]+),?\s*$", body, re.M)
        out[name] = [c for c in cols if not c.startswith("all_funds")]
    detail = ROOT / "sql" / "create_detail_view.sql"
    if detail.exists():
        body = detail.read_text().split("AS\nSELECT")[-1].split("FROM public.")[0]
        out["v_spending_detail"] = re.findall(r"AS\s+([a-z_]+)", body)
    return out


def build() -> dict:
    arts = [describe_artifact(p) for p in sorted(STATIC.glob("*.json"))]
    return {
        "generated_from": "the real files, at build time",
        "artifacts": arts,
        "totals": {
            "artifacts": len(arts),
            "bytes": sum(a["bytes"] for a in arts),
            "district_records": sum(a["records"] or 0 for a in arts),
            "fields_documented": sum(len(a["fields"]) for a in arts),
        },
        "routes": routes(),
        "views": view_columns(),
    }


def markdown(d: dict) -> str:
    L = ["# Data Dictionary",
         "",
         "**Generated by `scripts/build_data_dictionary.py` — do not edit by hand.**",
         "A hand-written dictionary is accurate the day it is written and wrong by",
         "the next release, and a dictionary that is wrong is worse than none.",
         "Everything here is read out of the real files at build time.",
         "",
         f"{d['totals']['artifacts']} data files · "
         f"{d['totals']['bytes'] / 1e6:.1f} MB · "
         f"{d['totals']['fields_documented']:,} fields · "
         f"{len(d['routes'])} public routes",
         ""]

    L += ["## What each file holds", "",
          "| File | What it is | Records | Size | Year |", "|---|---|---:|---:|---:|"]
    for a in d["artifacts"]:
        L.append(f"| `{a['file']}` | **{a['title']}** — {a['what_it_is']} "
                 f"| {a['records'] or '—':,} | {a['bytes'] / 1e6:.1f} MB "
                 f"| {a['year'] or '—'} |" if a["records"] else
                 f"| `{a['file']}` | **{a['title']}** — {a['what_it_is']} "
                 f"| — | {a['bytes'] / 1e6:.1f} MB | {a['year'] or '—'} |")
    L.append("")

    for a in d["artifacts"]:
        L += [f"### `{a['file']}` — {a['title']}", ""]
        if a["what_it_is"]:
            L += [a["what_it_is"], ""]
        bits = []
        if a["source"]:
            bits.append(f"**Source** {a['source']}")
        if a["publisher"]:
            bits.append(f"**Publisher** {a['publisher']}")
        if a["year"]:
            bits.append(f"**Year** {a['first_year'] or ''}"
                        f"{'–' if a['first_year'] else ''}{a['year']}")
        if bits:
            L += [" · ".join(bits), ""]
        if a["fields"]:
            L += [f"Fields (from district `{a['sample_district']}`):", "",
                  "| Field | Type | Example |", "|---|---|---|"]
            for path, info in list(a["fields"].items())[:60]:
                ex = info.get("example")
                if info["type"] == "object":
                    ex = f"{info['keys']} keys"
                elif info["type"] == "list":
                    ex = f"{info['length']} items"
                L.append(f"| `{path}` | {info['type']} | {ex if ex is not None else ''} |")
            if len(a["fields"]) > 60:
                L.append(f"| … | | {len(a['fields']) - 60} more fields |")
            L.append("")
        if a["limits"]:
            L += ["**What this data cannot tell you:**", ""]
            L += [f"- {x}" for x in a["limits"]]
            L.append("")

    L += ["## Database views", ""]
    for name, cols in d["views"].items():
        L += [f"### `{name}` — {len(cols)} columns", "",
              ", ".join(f"`{c}`" for c in cols), ""]

    L += ["## Public routes", "", "| Route | What it returns |", "|---|---|"]
    for r in d["routes"]:
        L.append(f"| `{r['method']} {r['path']}` | {r['summary']} |")
    L.append("")
    return "\n".join(L)


def grouped(d: dict) -> list[dict]:
    by_file = {a["file"]: a for a in d["artifacts"]}
    out, seen = [], set()
    for title, blurb, files in GROUPS:
        members = [by_file[f] for f in files if f in by_file]
        seen.update(f for f in files if f in by_file)
        if members:
            out.append({"title": title, "blurb": blurb, "files": members})
    rest = [a for a in d["artifacts"] if a["file"] not in seen]
    if rest:
        out.append({"title": "Ungrouped", "blurb":
                    "Not yet placed — add it to GROUPS in the builder.",
                    "files": rest})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="data/data_dictionary.json")
    ap.add_argument("--markdown", default="docs/DATA_DICTIONARY.md")
    ap.add_argument("--html", default="")
    args = ap.parse_args()

    d = build()
    d["groups"] = grouped(d)
    (ROOT / args.json).write_text(json.dumps(d, indent=1))
    (ROOT / args.markdown).write_text(markdown(d))
    if args.html:
        tpl = (ROOT / "scripts" / "data_dictionary_template.html").read_text()
        payload = json.dumps(d, separators=(",", ":"))
        (ROOT / args.html).write_text(
            tpl.replace("/*__DATA__*/null", payload))
        print(f"wrote {args.html}")
    t = d["totals"]
    print(f"wrote {args.markdown} and {args.json}")
    print(f"  {t['artifacts']} artefacts · {t['bytes'] / 1e6:.1f} MB · "
          f"{t['fields_documented']:,} fields · {len(d['routes'])} routes")
    missing = [a["file"] for a in d["artifacts"] if not a["what_it_is"]]
    if missing:
        print(f"  NO PLAIN-ENGLISH ENTRY for: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
