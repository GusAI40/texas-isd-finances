# Independent comparison-period verification

Date: 2026-10-07  
Verifier: fresh read-only Luna pass  
Revision inspected: `de49c2f6c21baf4e818c8be284deec8512e0a692` (`de49c2f`) with working-tree changes. No implementation, source artifact, widget, deployment, or production files were changed; only this evidence report was added.

## Commands and execution evidence

The targeted suite was run with the repository `.venv`:

```text
.venv\Scripts\python.exe -m pytest tests/test_mcp.py tests/test_mcp_parity.py tests/test_mcp_schemas.py tests/test_mcp_resources.py -q
78 passed, 1 warning in 6.00s
```

The warning is the existing Starlette/httpx deprecation warning. The parity
test's boundary tripwires passed: database, LLM, private operations, logging,
and filesystem writes were forbidden during all eleven public tool calls.
Source artifact hashes and vintages were checked by the passing parity suite;
the source artifacts were not modified. Resource tests passed with the single
resource URI and empty connect/resource/frame CSP domains.

Independent live calls produced:

```text
Dallas:  year=2025, outcomes_year=2024, points_vs_predicted=5.5
Houston: year=2025, outcomes_year=2024, points_vs_predicted=3.9
```

Their visual metrics reported finance metrics with display/source period 2025
and `points_vs_predicted` with display/source period 2024 and `modeled` status.
The fallback text explicitly said `Finance year 2025; outcome year 2024` for
each district. Synthetic distinct-year records (finance 2031/2032, outcomes
1998/1997, gaps 5.5/3.9) independently retained each district's own fields.
Omitted and explicit-null outcome years both produced `outcomes_year` omission
or null at the row boundary and `Not reported` for both visual periods. A
non-null gap remained numeric when its outcome year was absent. Synthetic null
students/local share displayed `Not reported`; genuine zero students/local
share and zero gap remained `0`/`0%`/`+0.0`.

## Acceptance results

| ID | Result | Evidence |
|---|---|---|
| CP-01 Source truth | **PASS** | `tests/test_mcp_parity.py` derives finance year from each forensic record's `year`, outcome year from `where_it_landed.year`, and gap from `where_it_landed.gap`. Live Dallas/Houston calls returned 2025, 2024, 5.5, and 3.9. Synthetic distinct-year records prevented metadata/global-year substitution. |
| CP-02 Visual periods | **PASS** | The parity visual contract uses `period_path: year` for operating/debt/local metrics and `period_path: where_it_landed.year` for the modeled gap. Live visual output showed 2025 for finance metrics and 2024 for both gap periods, with units, denominators, limits, values, and modeled status preserved. |
| CP-03 Missing outcome period | **PASS** | Direct transformed-row tests covered omitted and null `outcomes_year`, absent/null nested outcome data behavior, historical rows omitting the additive field, and a non-null gap with unknown year. Both gap display/source periods and fallback text were `Not reported`; no finance-year fallback or `None` was emitted. |
| CP-04 Truthful text and zero | **PASS** | Direct fallback edge cases separated source-null from source-zero students/local share and retained a legitimate zero gap. Existing explanatory text, limits, and per-district finance/outcome labels remained present. |
| CP-05 Additive schema compatibility | **PASS** | The repair declares `outcomes_year: _nullable(_YEAR)` in `_COMPARE_ROW` while leaving it out of `required`. `tests/test_mcp_schemas.py::test_comparison_outcomes_year_is_optional_nullable_and_strictly_typed` ran the pinned strict recursive AJV runner against current integer, historical omission, explicit null, and four invalid values: string `"2024"`, boolean `true`, fraction `2024.5`, and out-of-range `1800`; all classifications were correct. The focused schema/parity runs passed 16/16 in both default and `PYTHONUTF8=1` modes. |
| CP-06 Boundaries and integration | **UNVERIFIED** | Local protocol, parity, resource, and CSP boundary checks passed (78/78). The prior browser evidence reports 56 Playwright passes and empty CSP, but its captured comparison fixture is explicitly stale and labels the gap as 2025. The required post-repair widget fixture recapture and owner-run browser check showing finance 2025 beside outcome 2024 were not available in this verification, so the actual host/rendering gate remains pending. |

## Scope limits

This report covers only the comparison-period refinement. The CP-05 schema gap
is repaired and independently verified. CP-06 requires the
separate widget owner recapture from actual tool calls and concrete browser
evidence. No production, deployment, source ingestion, database, LLM, or
mutation action was performed.

## A-ENC-01 independent verification

The newly added adversarial dictionary tests were independently run in both
Windows modes:

```text
PYTHONUTF8 unset:  .venv\Scripts\python.exe -m pytest tests/test_data_dictionary.py -q
7 passed in 0.83s

PYTHONUTF8=1:     .venv\Scripts\python.exe -m pytest tests/test_data_dictionary.py -q
7 passed in 1.32s
```

The two targeted adversarial tests also passed directly: non-ASCII UTF-8 data
and LF/CRLF equivalents produce identical canonical byte metadata; changing
the current working file changes the reported source; invalid UTF-8 raises a
visible `UnicodeDecodeError`. The builder reads the current file with strict
UTF-8, normalizes CRLF/CR to LF before byte counting, and writes deterministic
UTF-8/LF output. **A-ENC-01: PASS.**
