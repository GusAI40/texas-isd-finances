# D-PARITY-01 fresh verification

**Date:** 2026-10-07
**Verifier:** fresh Luna read-only verification
**Scope:** `D-PARITY-01` only; no source, test, fixture, or deployment changes

## Result

**FAIL — partial implementation evidence.** The endpoint registry and the
requested boundary paths are present and the targeted suite passes, but the
suite does not establish the acceptance condition that all promised artifact
fields, values, years, limits, and comparable definitions are independently
matched. It contains one selected assertion per tool and truthiness checks for
`limits`; that is useful smoke coverage, but it is not a complete parity
fixture.

## Checks that pass

- The live registry has exactly the eleven planned names, in order:
  `find_district`, `district_money`, `district_lineage`,
  `district_forensics`, `district_trends`, `district_bonds`,
  `district_campuses`, `district_debt`, `district_national`,
  `texas_overview`, and `compare_districts`.
- `.venv\Scripts\python.exe -m pytest tests/test_mcp_parity.py -q` passed all
  five tests. The run emitted one existing Starlette/httpx deprecation warning.
- The fixture directly hashes only `economics_data.json`, `forensic_data.json`,
  and `national_data.json`, and checks TEA 2025 and Census 2024 metadata.
- The success loop reads public artifact JSON directly and checks one artifact
  value for each tool: allocation, lineage value, forensic outside-operating,
  trend change, bond totals, debt principal, campus list, national PPCS,
  statewide forensic data, and one comparison operating-per-student value.
- The boundary-path test passes for comparison counts 1, 2, 6, and 7; charter
  national absence; malformed ID/type; dropped-leading-zero repair; Unicode
  name failure; and MRTR ambiguous, decline, and accepted retry behavior.

## Acceptance gaps

1. **Field coverage is shallow.** `test_all_eleven_tools_match_independent_public_artifact_fields`
   asserts one field or subobject per tool. It does not compare all promised
   output fields against their artifact paths. For example, `district_money`
   returns allocation, revenue, recapture, tax, reliability, students, year,
   and other fields, but the parity assertion checks only
   `allocation.total_per_student`; `district_debt`, `district_campuses`, and
   `district_national` likewise check only principal, campuses, and PPCS.

2. **Per-tool years are not matched.** The fixture checks the two top-level
   vintages only. The parity loop does not assert Dallas's returned year,
   lineage fiscal year/source vintage, trend year array, bond election years,
   debt fiscal-year context/history, campus year, national fiscal year, or
   statewide trend years against their source artifacts. Several source
   artifacts expose distinct year semantics (TEA 2025, Census 2024, bond
   history through 2026, and trend 2009–2025).

3. **Limits are only truthiness checks.** Each successful case asserts that a
   nonempty `limits` value exists, but does not compare the returned limits to
   the corresponding artifact `meta.limits`, or verify that the limits describe
   the returned measure's period, denominator, inflation treatment, missing
   coverage, or comparability constraints.

4. **Comparable definitions are not independently verified.** No assertion
   checks units, numerator/denominator, source identity, source URL, metric
   definition, fiscal period, or comparable-measure agreement. This matters in
   particular for `compare_districts`, where the test checks one operating value
   but does not establish that both rows use the same period, unit, and
   denominator.

5. **Source anchors are incomplete.** `mcp_cases.json` has only three artifact
   hashes even though the parity loop reads economics, forensic, trend, bond,
   debt, campus, and national artifacts. There are no independent hash/path
   anchors for trend, bond, debt, or campus artifacts, and no fixture-level
   expected field map for the eleven contracts.

6. **Boundary instrumentation is outside this targeted suite.** The
   implementation evidence points to `tests/test_mcp.py` for no-DB behavior,
   headers, cache, and origin/version safeguards. Those checks are valuable,
   but they are not run by the targeted command and are not instrumented in
   `test_mcp_parity.py` to raise on DB, LLM, write, or private-operation calls.
   This verification therefore records those protections as adjacent evidence,
   not as independently proven by the parity test.

## Reproduction notes

Running `python -m pytest tests/test_mcp_parity.py -q` with the system Python
fails during collection because `asyncpg` is unavailable. The repository
`.venv` contains the required dependencies and produces the five-pass result
above. This is an environment/setup issue, not a parity assertion result.

No repairs were made during this verification.
