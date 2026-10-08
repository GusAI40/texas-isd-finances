# Independent final framing verification

**Reviewer:** fresh Luna verifier (read-only source review)
**Reviewed:** 2026-10-07 America/Chicago
**Scope:** FRAME-01 through FRAME-05 in `docs/FRAMING_TEST_REFINEMENT.md`; `static/index.html`, `tests/test_api.py`, `tests/test_framing.py`, Dallas public fixture, and `docs/evidence/mcp/framing-argyle-public.json`.
**Limit:** This is an agent verification record, not a human study, screen-reader study, or FRAME-06 visual review. No database, paid query, host, or production mutation was performed.

## Evidence run

- `.venv\\Scripts\\python.exe -m pytest tests/test_framing.py tests/test_api.py -k "framing or hero_credentials" -q`: **14 passed**, 81 deselected, one unrelated Starlette deprecation warning.
- `.venv\\Scripts\\python.exe -m pytest tests/test_framing.py -q`: **13 passed** in the default Windows mode.
- `PYTHONUTF8=1 .venv\\Scripts\\python.exe -m pytest tests/test_framing.py -q`: **13 passed** in the explicit UTF-8 Windows mode.
- The tests execute the named shipped JavaScript renderers through Node `vm` and a bounded DOM stub. They do not reimplement the renderer or formula. The proof test reads the recorded public `/stats` payload, checks its captured vintage, checks the page's paired numeric/label output, and compares `/stats` when the local API is available.

## Recorded source facts

The recorded stats fixture (`tests/browser/fixtures/public-endpoints.json`, captured 2026-10-07 18:39:01 CDT) reports `total_records=20,587`, `total_years=17`, `start_year=2009`, `end_year=2025`, and `total_districts=1,310`. The page keeps these quantities visibly separate: `20,587 actual-finance records`, `17 actual financial years`, and `1,310 districts in the registry`; the bond history is separately described as beginning in 1958. The audit's source register records 15 publisher checks, but that is source-register evidence rather than a finance-row count.

The read-only finance audit (`docs/evidence/2026-10-07/finance.json`) independently records 20,587 registry rows, 1,310 districts, 2009–2025, zero invalid six-digit IDs and duplicate district-year keys, and three missing/nonpositive enrollments. Its Dallas FY2025 row is district `057905`, total spend `3,319,208,715`, enrollment `139,776`, stored all-funds spend/student `23,746`, and operating spend `1,986,168,795`. The Argyle fixture is district `061910`, FY2025, total spend `193,842,830`, enrollment `6,114`, stored all-funds spend/student `31,704`, and operating spend `63,325,274`; it is explicitly marked as unreconciled production evidence with known integer-division truncation. The fixture's `checked_at` is `2026-10-07T23:03:53.6103926Z` and observed revision is `73df1896…`; the historical values are not treated as corrected live data.

## Acceptance results

| Criterion | Result | Evidence and limits |
|---|---|---|
| FRAME-01 | **PASS** | `test_hero_credentials_match_the_data` checks the actual recorded `total_years` and `total_records`, captured vintage, actual-finance labels, absence of the stale “years of records” wording, and live `/stats` agreement when available. Registry count is separately labelled and bond history is not used as finance history. |
| FRAME-02 | **PASS** | `renderKPIs()` is executed through the test harness. Its populated rank detail emits `all funds / student · includes construction & debt`; the assertions require all three concepts and fail on in-memory removal of either inclusion word. |
| FRAME-03 | **PASS (local renderer); browser owner evidence pending** | `renderWelcomeFor()` plus `renderHeroMetrics()` is exercised for Dallas and Argyle fixtures. Output includes district name/FY, separate all-funds and operations/student values, and a construction/debt qualifier. The same assertion group detects missing frame/qualifier or swapped rendered values. This does not certify desktop/mobile browser visibility here because the targeted Playwright cases were skipped (`4 x`) in this invocation; no new browser or 72-cell claim is made. |
| FRAME-04 | **PASS (local renderer)** | `updateHeroDollar()` selects a valid positive-enrollment row matching `d.year`, preserves the summary-authoritative all-funds figure, emits operations/student separately, displays legitimate zero, and emits unavailable for null/missing/invalid same-year data. It does not derive operations as an all-funds residual. The synthetic different-year case rejects a mutated first/latest-row lookup. |
| FRAME-05 | **PASS for focused/full framing gates** | Existing operating-balance, mixed-frame-deficit, source-column, and change-flag guards remain present; 13/13 framing tests pass in both Windows modes and the proof test passes. Full repository suite and final browser/visual matrix are outside this bounded verifier scope. |

## Independent negative demonstrations

These were run in memory from the actual renderer source; `static/index.html` and tests were not modified.

1. Removing `includes construction & debt` from the `renderHeroMetrics` output produced a rank/hero string with no construction/debt qualifier; the relevant assertion rejected it.
2. Replacing the all-funds value expression with the operations value produced `$10,357` in the all-funds slot for Argyle while the operations slot remained `$10,357`; the expected `$31,704` assertion rejected it.
3. Replacing the same-year `.find()` predicate in `updateHeroDollar()` with an unconditional first-row selection produced `$1 operations / student` from a FY2024 row while the dollar was FY2025; the same-year expected-output assertion rejected it.

The current tests therefore exercise actual renderer output and detect these bounded mutations. The negative demonstrations do not prove browser layout, accessibility, or live-source freshness.

## Manual source hashes

SHA-256 at review time:

- `static/index.html`: `E53B2CD103C07DE9F8D7788C15EAB775B2AC2BBBD0C7E872B851C1128F224E7F`
- `tests/test_api.py`: `C37F3BFFE70561D43FC9B9D9D37620A4916BCB27AAF15B544343829D4A608289`
- `tests/test_framing.py`: `839BBDA51C3A9CC83A6864F21E358B13B9EAFC2F0AA5D7D3161A508E8600B1B1`
- `tests/browser/fixtures/public-endpoints.json`: `D757A8675D5877FC7EA430112003574EA65464F84A5AF87CF0D6929960F7B9AE`
- `docs/evidence/mcp/framing-argyle-public.json`: `B6C0C9ACFDDFF1898B73FC2E2B6A63245868B1FA42DE000FE840C0DD0413F1F9`

Working-tree source/test files were already modified by the implementation workflow; this verifier made no source or test edits.
