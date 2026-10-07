# Comparison source-period and missing-value refinement

Date: 2026-10-07. Status: approved-scope planning revision for Terra implementation; no implementation or publication performed by this plan.

This narrowly refines D-PARITY-01, D-SCHEMA-01 and the comparison portion of E-VISUAL-01 in `MCP_PLUGIN_IMPLEMENTATION_PLAN.md`. All other contracts and release gates remain in force.

## Evidence and decision

The actual `static/forensic_data.json` records contain:

| District | `year` | `where_it_landed.year` | `where_it_landed.gap` |
|---|---:|---:|---:|
| Dallas `057905` | 2025 | 2024 | 5.5 |
| Houston `101912` | 2025 | 2024 | 3.9 |

`src/mcp_tools.py::compare_districts` copies each record's finance `year` but drops `where_it_landed.year`. `src/mcp_apps.py::visual_payload` then supplies that finance year to every comparison metric, including `points_vs_predicted`. The existing parity tests duplicate this error by expecting artifact `meta.year` for every metric. The text fallback also converts null `students` and `local_pct` to zero. `_metric` renders a null display period as `Not reported` but a null source period as the string `None`.

Add one comparison-row field, `outcomes_year`, copied exclusively from `(record.get("where_it_landed") or {}).get("year")`. Preserve `year` as the existing district finance year. Make `outcomes_year` an optional, nullable `_YEAR` schema property; never add it to required fields. Current calls include it, with null when absent. Historical saved responses may omit it. Never infer the outcome year from the finance year, metadata year, another district, or a year offset.

## Ownership and boundaries

Terra owns only `src/mcp_tools.py`, `src/mcp_apps.py`, `tests/test_mcp_parity.py`, `tests/test_mcp_schemas.py`, and relevant comparison field/period paths in `tests/fixtures/mcp_cases.json`. Preserve all source artifacts, hashes, source vintages, saved host evidence, eleven tool names, existing input bounds, schema required fields, values, units, denominators, limits and protocol behavior.

The widget owner exclusively owns `static/mcp-app.html`, widget/browser code, and `tests/fixtures/mcp_visual_payloads.json`. Terra must report the final additive contract and successful checks to root for coordinated regeneration of those fixtures from actual tool calls. Do not edit or revert the widget owner's work. No SDK, protocol, production, packaging, unrelated documentation, or source-data changes belong to this refinement.

## Ordered implementation

1. **Add independent failing parity tests.** Derive comparison finance year from each source record's `year` and outcome year from its `where_it_landed.year`, eliminating the `expected_compare_row` helper's caller-supplied metadata year. Add `outcomes_year` to its expectation. In comparison fixture definitions, add a `period_path` of `year` for finance metrics and `where_it_landed.year` for the modeled gap. Add/correct only the comparison contract's finance/outcome field paths. Read both metric value and period independently from the artifact; do not derive expected periods from the tool response or the production transformation. Preserve hashes and vintage anchors.

2. **Preserve the source period in the handler and schema.** Add `outcomes_year` from the nested outcome record. Document it as optional and nullable in `_COMPARE_ROW`; retain `year` and every existing key and required-field rule. Do not change financial calculations or the gap value.

3. **Correct only the comparison visual mapping.** Supply `row.get("outcomes_year")` to the gap metric and retain `row.get("year")` for financial metrics. Normalize missing comparison periods to the literal `Not reported` before supplying them to `_metric`, so both `metric.period` and `metric.source.period` agree. Use explicit `is None` handling, not a guessed replacement. This comparison-local normalization avoids changing other view mappings. Keep non-null modeled gaps marked `modeled`; this work does not redefine metric statuses.

4. **Make fallback text truthful.** Display null student counts and null local share as `Not reported` (without a percent suffix on missing share); preserve genuine zero as numeric `0` and `0%`. Preserve the existing table values, explanation, missing-district notice and limits. Add clear per-district period text, such as `Dallas ISD: Finance year 2025; outcome year 2024.` Label missing periods `Not reported`. Use both row fields independently; do not create one global comparison year or imply that finance and outcomes cover the same year.

5. **Exercise independent edge cases and compatibility.** Using deep-copied in-memory forensic records and the existing monkeypatch/test approach, cover nested outcome year absent, explicitly null, and `where_it_landed` absent/null. Also use distinct per-district finance/outcome years that differ from `meta.year` to detect global-year assumptions. Retain a non-null gap when removing its year to prove that year missingness alone cannot trigger a finance-year fallback. Test null and zero student/local-share values in separate records, including a legitimate zero gap. Do not mutate source files. Run strict AJV on current, historical, omitted-outcome-year, null-outcome-year and invalid-outcome-year payloads; string and out-of-range numeric years must fail, while integer source years, null and omission pass.

6. **Verify and coordinate.** Run the focused suite below and report acceptance evidence to root. The widget owner then regenerates its captured comparison fixtures and verifies visible finance/outcome periods under the existing actual CSP harness. No fixture may be hand-adjusted to claim a real tool capture. Root obtains an independent fresh Luna verification; Terra does not certify its own work as independently verified.

## Objective acceptance criteria

| ID | PASS condition and evidence |
|---|---|
| CP-01 Source truth | Real Dallas/Houston calls retain `year=2025`, add `outcomes_year=2024`, and retain gaps 5.5/3.9. Independent artifact-path expectations verify every comparison value, finance period, outcome period and limits. Distinct-year injected records prove each district uses its own fields, not artifact metadata or another district. |
| CP-02 Visual periods | All comparison finance metrics have display/source period equal to the district record's finance year. Each gap metric has display/source period equal to `where_it_landed.year` (2024 in the real records). Existing labels, units, denominators, limits and modeled status for non-null gaps survive. |
| CP-03 Missing outcome period | Absent/null outcome year or absent/null nested outcome record produces `outcomes_year=null` in current handler output and `Not reported` in both gap display/source periods and fallback outcome-year text. A historical row omitting the new field also yields `Not reported` in its transformed gap periods. No `None`, finance-year substitution or guessed year is displayed. A non-null gap with an unknown year remains its actual value with unknown period. |
| CP-04 Truthful text and zero | Source-null students/local share display `Not reported`; source zero displays numeric `0`/`0%`, and zero gap remains numeric. Per-district fallback text explicitly labels finance year and outcome year independently, including differing years and missing-period cases. Existing explanatory and missing-district text remains available. |
| CP-05 Additive schema compatibility | Exact eleven-tool registry remains. Strict recursive AJV compiles every current tool schema and validates all eleven actual current successes and unchanged saved owner-host successes. Comparison rows allow integer/null/omitted `outcomes_year`, reject invalid types/out-of-range years, and keep prior required keys. Error/MRTR envelope tests still pass. Saved evidence is not rewritten. |
| CP-06 Boundaries and integration | Existing protocol/resource/public-artifact boundary checks pass without new runtime reads, dependencies, calls, or writes. Resource CSP metadata and actual composed-resource/browser CSP execution remain unchanged and pass the owner/root harness. Widget fixture recapture comes from the resulting tools and visible comparison checks show finance 2025 alongside outcome 2024. Terra reports the owner-run browser check as pending until concrete results arrive; simulated checks alone do not establish host rendering. |

Run from the repository root using its existing Python environment:

```powershell
python -m pytest tests/test_mcp.py tests/test_mcp_parity.py tests/test_mcp_schemas.py tests/test_mcp_resources.py -q
```

`tests/test_mcp_schemas.py` must actually execute the existing pinned strict AJV runner; no validator skip or parse-only replacement. The widget owner/root supplies the existing CSP browser harness invocation and evidence without changing Terra's file ownership. Preserve existing actual-host limitations: local success does not close the ChatGPT rendering or installation gates.

If a criterion needs architecture, contract, ownership or scope beyond the changes above, return the precise conflict to Astra before implementation. Apply the existing two-counted-Terra-attempt escalation rule per failed criterion.
