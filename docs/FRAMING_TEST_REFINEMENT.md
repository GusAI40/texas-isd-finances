# Four failing framing checks: bounded refinement

Prepared 2026-10-07 by Astra from targeted inspection of `tests/test_api.py`,
`tests/test_framing.py`, the four named renderers in `static/index.html`, the
`/stats` source query, and existing public fixtures. No implementation occurs in
this document. This refines test acceptance for the four reported failures;
it does not weaken the independent finance-framing rule or the 95/5 gate.

## Findings and decision

| Reported failure | Evidence and disposition |
|---|---|
| Hero credentials | `test_hero_credentials_match_the_data` requires the literal `>17</b><i>years of budgets`. The page instead has `#proof-years = 17` paired with `actual financial years`, and `#proof-points = 20,587` paired with `actual-finance records`. Existing recorded `/stats` and fallback stats contain `total_years=17`, `start_year=2009`, `end_year=2025`, `total_records=20587`. The source query uses `COUNT(DISTINCT year)` and `COUNT(*)` over the finance summary. The old wording is stale; preserve the more accurate actual-finance source kind and test the counted facts. |
| Statewide rank | `renderKPIs` now says `Above ...% of Texas districts · all funds`. The rank's own visible label no longer explains construction and debt. This is a genuine loss of plain financial context. Restore a compact inclusion qualifier locally; do not merely change the test to accept `all funds`. |
| Deep-link hero | `renderWelcomeFor` computes operating spend/student and passes it alongside the summary's all-funds spend/student to `renderHeroMetrics` unconditionally. The old `nonOpShare` threshold and `building them` narrative are not required when both frames are always shown. However, `all funds / student` alone is still technical shorthand: the shared first-view ledger must explicitly qualify construction/debt inclusion. |
| Penny caption | `updateHeroDollar` displays separate all-funds and operations/student figures and a debt/capital qualifier; the exact old phrases `runs schools` and `everything spent` are stale. Its latest-available operating row can nevertheless differ from `d.year`, and its truthiness condition hides legitimate zero. These directly affect the acceptance of the replacement frame; fix locally before replacing the old phrase checks. |

The historical Argyle numbers in source comments are a regression example, not
a newly verified current fixture. The inspected Dallas FY2025 public fixture
contains all-funds spend/student 23,746, enrollment 139,776, operating spend
1,986,168,795, debt service 500,174,938, and capital projects 766,316,261. Expected
operations/student must be independently divided from that row, retaining its
year and provenance. Do not derive operating spending by subtracting debt and
capital from all-funds spending: these source definitions are independent.

## Ordered implementation and ownership

1. Root coordinates the existing UI owner before further capture. That owner
   alone changes `static/index.html`. The new Terra task owns only
   `tests/test_api.py` and `tests/test_framing.py`, is not alone in the codebase,
   and must preserve concurrent edits. The existing browser regression owner
   owns any browser checks; no second agent edits their files. No SQL/data
   builder/asset dependency change is authorized by this refinement.
2. UI owner adds visible, compact qualifiers beside each affected all-funds
   figure, for example `all funds / student · includes construction & debt` in
   the shared hero ledger and `all funds · includes construction & debt` in the
   rank card. The penny caption names construction and debt explicitly rather
   than relying only on the word capital. Equivalent concise wording is allowed;
   the semantic assertions below, not a required sentence, control acceptance.
   Keep separate operations/student values, unit and fiscal year. These labels
   must be default-visible, not comments, tooltips or disclosure-only text.
3. In `updateHeroDollar`, select the operating summary row for `d.year` with a
   valid positive enrollment. Preserve `dollarParts`' same-year summary
   spend/student preference. Use an explicit null/validity check so valid zero
   is displayed. If same-year operating data is absent, show an honest compact
   operations-unavailable status; do not silently substitute another year or
   zero. This authorizes only the named caption calculation and its shared hero
   output. Preserve other fallback and data-contract behavior.
4. Terra replaces only the four stale assertion groups and narrowly necessary
   UTF-8 reads/helpers in its two files. Keep all other independent framing
   checks (especially operating balance and no mixed-frame deficit) intact.
   Parse the actual proof elements and paired label text, not one exact HTML
   serialization. Read the committed recorded stats/fallback provenance for
   offline assertions. Where a controlled `/stats` response is available, use
   `total_years`, not merely end minus start plus one; year ranges can have gaps.
   Do not add skips to make these four checks green or require live DB access.
5. For hero/penny/rank tests, assert the emitted content from the actual named
   functions and shared helper, not just words anywhere in the HTML file. A
   small Node invocation from the Python test can execute the extracted actual
   functions with narrowly stubbed DOM/formatting/chart dependencies and return
   their emitted markup/text. Do not reimplement the renderer or financial
   formula in the test oracle. Browser evidence from the existing owner proves
   default visibility; source-only checks cannot prove that.
6. Use the existing recorded Dallas row and obtain an actual Argyle `061910`
   summary through the available read-only public source or an existing verified
   local snapshot. Preserve its captured date/source/hash and only necessary
   fields; coordinate any fixture-file change with its owner. An embedded
   fixture in the test file is permitted when fully attributed. Do not turn old
   explanatory comments into purported live data. Add clearly synthetic variants
   only for zero, null, invalid denominator, and mismatched-year behavior. An
   unavailable Argyle source is reported as an evidence gap, never invented.
7. Run the focused four tests and unchanged complete framing suite, then the
   existing full suite in both established Windows modes. The browser owner
   checks Dallas plus Argyle default hero/rank/caption on desktop and mobile
   with real rendered values and labels. UI owner recaptures affected final
   visual evidence after the last markup change; previous screenshots cannot
   certify modified content. Do not lower or bypass the 95% threshold.

## Objective acceptance criteria

| ID | PASS evidence |
|---|---|
| FRAME-01 | The proof row's numeric finance-year and record counts match the actual recorded source (`total_years`, `total_records`) used for that evidence, with actual-financial-data labels. Registry count remains a separately named quantity; bond history is not presented as finance history. The fixture vintage is explicit. Live-source disagreement must be reported rather than silently accepting a stale claim. |
| FRAME-02 | The populated rank card itself visibly identifies its ranking as all-funds spend/student including construction and debt. Removing either inclusion concept from that card's emitted output fails its test even if the words remain elsewhere in the page. |
| FRAME-03 | Actual Dallas and Argyle deep-link render output names the district/FY and separately labels the authoritative all-funds spend/student and independently computed operating spend/student. The adjacent all-funds qualifier names construction and debt. No material-share threshold or old story sentence is required. Hiding/removing either frame, swapping their values, or omitting the qualifier is detected. |
| FRAME-04 | The dollar caption and shared ledger use same-year frames. A fixture with newer or older unrelated operating rows never borrows their value. A legitimate zero operating figure renders as zero; null/missing/invalid-denominator data renders unavailable. All-funds retains its summary-authoritative rounding, construction/debt inclusion is explicit, and no value is described as the residual of the other. |
| FRAME-05 | Existing operating-balance, mixed-frame-deficit, source-column and change-flag guards remain in force. The four reported tests and full framing suite pass in both Windows modes with explicit UTF-8 source reads where needed; full-suite results disclose unrelated failures/skips. Real browser evidence confirms qualifiers and both valid frames are visible by default. |
| FRAME-06 | The final visual matrix is recaptured for changed content and retains all 72 required cells passing initial/full >=95% with semantic review. Essential finance qualifiers remain scored according to the unchanged rubric; no font shrinking, concealment, fake marks or classification exemption is used to absorb the added context. |

Before declaring the replacement tests protective, demonstrate narrowly that
removing a required label, swapping the two rendered monetary values, and
substituting a different year's operating row fail the relevant assertions.
This can use in-memory mutated renderer copies or synthetic input variations;
never mutate the shared production file during concurrent work.

This supersedes only the four exact-phrase requirements identified above.
It preserves the original test module's independent framing rules and all
data/source-status, accessibility, usability, and release evidence limitations.
