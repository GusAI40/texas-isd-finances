# Final portal independent verification

Reviewer: fresh Luna verifier, agent inspection only (not a human usability study)
Date: 2026-10-07 (America/Chicago)
Scope: frozen final portal source, final visual evidence, public browser workflows, and visual provenance. No application or test repairs were made.

## Evidence freeze

The final capture set contains 72 baseline cases, 72 final cases, and 12 prototype cases. The final set covers six states (statewide, Dallas, Tioga/small, charter, compare, unavailable), two engines (Chromium and Firefox), three viewports (1440x900, 768x1024, 390x844), and two themes. Every final case has raw and annotated full and initial images; no image references are missing. I inspected four contact sheets containing all 72 final cases: full raw, full annotated, initial raw, and initial annotated. Healthy cases show populated report content and marks; compare cases show Houston selected; unavailable cases retain visible report artifacts and the degraded status treatment.

The capture was completed after the fixture freeze. `source-hashes.json` matches every current final application source, fixture, recorder, selector manifest, and measurement source. Historical source entries intentionally remain pinned to commit `73df1896ed0818020ec1c15c06f5ee823db7ec0f`; their mismatch with the working tree is the expected historical identity check. `measurements-provenance.json` matches the compressed canonical evidence byte count and SHA-256, and the decompressed canonical SHA-256. The final measurement inventory has zero missing references, page errors, renderer warnings, manifest errors, unclassified items, or blocked external requests; all 12 compare cases are selected and unavailable cases carry the expected 11 graphics.

## Independent browser run

Command: `npx playwright test public-regression.spec.js --reporter=line` from `tests/browser`.

Result: **32 passed (3.1m)** using Chromium and Firefox. This includes the four real FRAME-03/05 cases (Dallas and Argyle, desktop and mobile), map/table parity, modal focus and tab trapping, normal versus unavailable routes, 320px and 200% reflow, print/export checks, and public route inventory. The run completed with exit code 0. The normal-district checks passed without a false degraded banner; the forced 503 checks preserved the artifacts and warning treatment.

## Criteria

| Criterion | Result | Evidence and limit |
|---|---|---|
| B-EVID-BASE-01 historical baseline | **OBSERVED_FAIL** | The pinned historical baseline is retained as a truthful observation. Its legacy prose includes unsupported claims such as “6.6 million data points” and “10 official sources”; those claims receive no new 95/5 credit. |
| B-EVID-PROTO-01 prototype | **OBSERVED_FAIL** | The 12 prototype cells remain separately identified and are not used as final release evidence. |
| B-EVID-COMPARE-01 provenance | **PASS** | Current fixture and collector hashes were refreshed after capture; current source records and gzip provenance validate exactly. Historical hashes remain pinned to their declared commit by design. |
| B-VIS-02 adversarial validator protection | **PASS** | The focused validator suite previously passed 13/13, including negative cases for removed labels, swapped rendered values, and a different-year operating row. Existing operating-balance, mixed-frame deficit, spike-cause, and construction/debt qualifier guards remain covered. |
| B-VIS-03 final visual evidence | **PASS semantic / automated review pending** | All 72 final raw and annotated initial/full cases were inspected from contact sheets. The final geometry is at least 96.36% full view and 100% initial view; final source and page inventories are clean. `visual-ratio.json` still reports `FAIL` only because all 72 `reviewed` flags remain false with `manual semantic review pending`; this verifier records the semantic review without mutating that evidence JSON. |
| C-FLOW-01 public workflow | **PASS** | Independent 32/32 Chromium + Firefox public regression run passed. |
| C-OFFLINE-01 healthy/unavailable states | **PASS** | Browser assertions and inspected final images show healthy populated reports without a false degraded banner and unavailable reports with honest status plus preserved artifacts. |
| FRAME-03/05 Dallas and Argyle | **PASS** | Four real desktop/mobile cases ran in both engines as part of the 32/32 run; Dallas and Argyle rendered with finance data. |
| C-A11Y-01 keyboard/reflow/print | **PASS bounded** | Browser checks cover keyboard lifecycle, focus return, tab trap, 320px, 200% reflow, print, and export. Native screen-reader behavior, native browser zoom beyond the tested reflow path, and human participants were not evaluated. |
| B-USER-01 human review | **UNVERIFIED** | This is an independent agent inspection, not a human study. |

The current rendered proof values are the corrected live fixture values: 20,587 finance records, 1,310 registry records, 17 distinct financial years, and 15 registered source products. Construction/debt labels carry their qualifier and period; finance and outcomes periods are not silently mixed. Unsupported historical credential claims remain `OBSERVED_FAIL` observations and do not become release credit.

## Superseding notice — 2026-10-07

The preceding B-VIS-03 semantic verdict is **WITHDRAWN / SUPERSEDED**. After that review, the measurement postprocessing artifact was replaced with the final 37-route result. The current `visual-ratio.json` SHA-256 is `981d436a55edc1f5dc24a9fa72f7bbe6835aa75c1b6962a0e0251f3c32d59342`; it reports final minimum full visual share `0.9081949955`, minimum initial share `0.9301015253`, 24 full-view failures, and 4 initial-view failures. This is a material change from the older 96.36%/100% result used above. No final visual PASS is asserted until the new capture and its identifiers are frozen and independently reviewed.

The current canonical measurement artifact has SHA-256 `9ab08f1b58af4dd408de936083431b83d699a2282adf5ddf025b8acc6de98d3b` (gzip) and `555bb46b1afe4320cff07c8bdff272f3b819c2c90359468247886ae20fb97812` (decompressed), with `captured_at` `2026-10-07T23:56:04.044Z` and fixture capture time `2026-10-07T23:42:55.403985+00:00`. The previous review inspected contact sheets generated before this postprocessing replacement, so it did not satisfy the required source/fixture/artifact identity freeze. The failure was a verifier process gap: I treated the completed image capture and refreshed source manifest as the final freeze without rechecking the canonical measurement and ratio hashes immediately before issuing the verdict.

C4’s independent 32/32 browser result remains valid for the stable application hash and is unaffected by this withdrawal. Reviewed flags remain untouched. The next review must first record and recheck the capture timestamp, fixture SHA set, source manifest SHA, canonical gzip SHA, and ratio artifact SHA, then inspect the images belonging to exactly that identity.
