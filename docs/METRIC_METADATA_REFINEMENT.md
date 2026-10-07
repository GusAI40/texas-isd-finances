# Bounded visual metric metadata refinement

Date: 2026-10-07. Stage: Astra planning addendum; implementation and fixture recapture pending.

This explicitly revises the comparison-only restriction in step 3 of `COMPARISON_PERIOD_REFINEMENT.md` for the three metadata corrections below. CP-01 through CP-06 remain applicable. It also refines D-PARITY-01 and the metadata portion of E-VISUAL-01. It does not reopen completed source-period work or authorize broader implementation.

## Targeted evidence

- `src/mcp_apps.py::_metric` renders absent/null periods as display `Not reported` but source `None`. Comparison now avoids the defect locally; district and statewide mappings still pass null through.
- All four `district_money` metric calls omit population. Their normal Dallas fixture consequently labels Dallas figures `Texas public school districts`. Comparison currently supplies its own district names; statewide correctly keeps the statewide population. An absent comparison name still triggers the statewide default.
- The comparison gap passes `status="modeled"` even when its value is null. `_metric` prioritizes the explicit status, making unavailable values appear modeled instead of missing.
- The current parity test compares metadata other than population. Its two comparison period assertions use an unparenthesized conditional: when the expected year is null, the assertion evaluates the truthy string `Not reported` without comparing the result. Edge tests must compare an explicitly computed expected string.
- Read-only inspection of the three normal captures in `tests/fixtures/mcp_visual_payloads.json` confirms Dallas district population is wrong; comparison populations and its 2025 finance/2024 outcome periods are correct; statewide population and 2025 period are correct.

## Exact decisions

1. Normalize period once inside `_metric`: `str(period)` for non-null input, otherwise `Not reported`; use that same normalized string for both `period` and `source.period`. Preserve every known year and the comparison finance/outcome source selection. Existing comparison-local normalization may remain; removal is not necessary for this fix.
2. Supply an explicit district identity as population for every district and comparison metric. Use that row's actual nonblank district name. If its name is absent, null, empty or whitespace-only, use `District <district_number>` when the already-supplied ID is a valid six-digit string, preserving leading zeroes. If neither identity is usable, use `District not reported`. Do not guess a name, look up another source, or fall back to the statewide population. A small pure identity helper in `mcp_apps.py` is permitted. Keep statewide population exactly as it is.
3. Change the comparison gap call's status to `missing` when its value is null/absent, and `modeled` otherwise. Keep this status correction local to that call, avoiding a global override of explicitly supplied statuses. Zero is a modeled value. A non-null gap with an unknown period remains modeled with `Not reported` period. A null gap with known outcome year retains that known year and becomes missing. Value missingness and year missingness are independent.

These are display metadata corrections only. Keep numeric values, source years, labels, units, denominators, source labels/URLs, limitations, artifact bytes/hashes/vintages, eleven tool names, public schemas, protocol, resources, CSP and tool text unchanged. No new runtime lookup or calculation is needed.

## Ordered implementation and ownership

1. **Terra adds failing tests** in `tests/test_mcp_parity.py` and, only if needed to run the existing strict validator against new cases, `tests/test_mcp_schemas.py`. Test the actual successful three tool calls against independent public-artifact expectations for normal metadata and unchanged values. Add small pure adapter cases for missing fields, since incomplete synthetic identities/years are not valid complete tool success envelopes. Fix the two conditional assertions by computing `expected_period` first and comparing both period fields to it. Do not generate expectations from `_metric` or another production helper.
2. **Terra implements only the three decisions** in `src/mcp_apps.py`. This addendum does not authorize edits to `src/mcp_tools.py`, source artifacts, other view/rendering code, or fixture schemas. Preserve concurrent Sol/C4 changes; do not revert another owner's edits. No additional fixture expectation files are required.
3. **Terra runs the focused suite** below, including the actual strict AJV runner for all eleven current successes and unchanged historical evidence. Report each MM criterion separately; owner-run browser work remains pending until observed.
4. **Root coordinates widget-owner recapture.** The widget owner retains exclusive ownership of `tests/fixtures/mcp_visual_payloads.json`, `static/mcp-app.html`, browser tests and screenshots. After the adapter changes are available, regenerate all three normal visual fixtures from actual `mcp_tools.call_tool` results. Their metadata should agree exactly with those results. Keep synthetic missing-value browser cases explicitly synthetic. The normal district capture changes its four populations to Dallas ISD; normal comparison/statewide values and metadata should remain the same. Refresh affected screenshots from the actual updated resource under the existing CSP harness, and rerun relevant browser assertions. No unrelated redesign or screenshot-only metadata patching.
5. **Fresh Luna verifies** the implementation, independent expectations, AJV evidence and owner/root browser evidence against MM-01 through MM-05. This planning turn changes only this document.

## Acceptance criteria

| ID | Objective PASS condition |
|---|---|
| MM-01 District population | All four real Dallas district metrics identify `Dallas ISD`. Every real comparison metric identifies its own Dallas/Houston row. Adapter tests use distinct names/IDs to prove no shared-name leakage. Missing/blank names with ID `057905` yield `District 057905`; absent/unusable name and ID yield `District not reported`. No district/comparison metric receives the statewide population. Statewide metrics retain `Texas public school districts`. |
| MM-02 Consistent periods | For district, comparison finance, comparison outcome, and statewide metrics, absent and explicitly null period inputs produce exactly `Not reported` in both period fields. Known years are preserved as strings; no finance/outcome fallback is introduced. Tests compute expected strings before comparisons, so a missing-period mismatch cannot pass through conditional-expression truthiness. |
| MM-03 Independent missing status | Comparison null/absent gap has null value and status `missing`; gap 0, positive and negative numbers retain their exact values and status `modeled`. Cover the cross-product of null/non-null gap and known/missing outcome year: missing value never erases known year, and missing year never erases a non-null modeled value. Other current statuses remain unchanged. |
| MM-04 Contract and source preservation | Independent all-tool parity, strict recursive AJV current/historical success validation, error/MRTR and existing resource/protocol/boundary checks pass. All eleven names survive; normal numeric values, actual years (including 2025 finance versus 2024 outcomes), units, denominators, sources and limits are unchanged. No source bytes/hash/vintage or historical evidence changes. |
| MM-05 Captured visual evidence | Widget owner recaptures all three normal fixtures from actual resulting tool calls and demonstrates fixture/tool equality. Updated rendered district source details show Dallas population; comparison still shows each district and its 2024 outcome period; statewide remains statewide. Synthetic missing-period/null-gap browser cases show `Not reported`/missing rather than `None`/modeled. Existing CSP execution and relevant screenshot/browser checks pass without a new network origin or bridge/resource change. Report host rendering separately; local browser evidence does not establish actual ChatGPT rendering. |

Run in the repository's existing environment:

```powershell
python -m pytest tests/test_mcp.py tests/test_mcp_parity.py tests/test_mcp_schemas.py tests/test_mcp_resources.py -q
```

Use the existing owner/root browser harness for MM-05; do not invent a new runner or claim success from fixture inspection alone. No production deployment is authorized by this plan. If another change is required to satisfy a criterion, return the precise scope conflict to Astra first. Existing counted Terra repair and Sol escalation rules continue to apply.
