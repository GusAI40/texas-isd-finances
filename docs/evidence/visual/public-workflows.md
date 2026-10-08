# C4 public-workflow evidence

The final populated-report public-workflow suite passed **34/34 tests in 3.2 minutes** on revision `76cacacfd41bc3cf855feaafd3ce7761a964c108`. The earlier 32-test run is preserved in the JSON history. The two additional checks exercise populated report composition in both engines. It ran with Playwright 1.56.1 using Chromium 141.0.7390.37 and Firefox 142.0.1. The checkout remained dirty because several authorized workstreams shared it; `public-workflows.json` records the SHA-256 of every tested workflow, fixture, and UI file so this result can be tied to the exact bytes under test.

The primary `C-FLOW-01` matrix passed all **12/12** browser, viewport, and theme cells:

| Browser | 1440x900 light | 1440x900 dark | 768x1024 light | 768x1024 dark | 390x844 light | 390x844 dark |
|---|---:|---:|---:|---:|---:|---:|
| Chromium | PASS | PASS | PASS | PASS | PASS | PASS |
| Firefox | PASS | PASS | PASS | PASS | PASS | PASS |

Each matrix cell used reduced-motion mode and completed the full workflow: the ambiguous Wylie search returned actual registry identifiers `043914` and `221912`; Dallas `057905` was selected; a six-digit deep URL overrode stored Houston state; all three lenses worked; Houston comparison and removal worked; section navigation reached its content; finance, outcomes, equity, economics, and national periods stayed distinct; the $500,000 tax-model input worked; source disclosures and semantic tables opened; citation copy or its honest selected-text fallback worked; CSV and PNG downloads were validated; print identity, values, sources, chart bounds, and the print action were validated; and both vendor-free maps completed filters, search, handoff, and back-to-report tasks.

The CSV check parsed the download, required more than ten rows, and found the expected Dallas FY 2025 value. The PNG check decoded the image data and required at least 600×200 pixels, more than four colors, and more than 1,000 non-background pixels. Print media required more than four visible analytical charts, each within the print viewport, together with the Dallas identity, expected finance value, and TEA source.

| Criterion | Result | Executions | Evidence |
|---|---:|---:|---|
| C-FLOW-01 | PASS | 14 | Twelve complete matrix workflows plus the ten-route render inventory in both engines. |
| C-OFFLINE-01 | PASS | 4 | Normal health and forced-503 behavior passed in both engines. |
| MAP-C4-01/02/03 | PASS | 4 | Desktop and mobile in both engines; all four metrics, return to turnover, all 1,016 rows, six columns, missing-last behavior, real zero, focus, pin, extent, disclosure, and handoff passed. |
| DIALOG-C4-01/02/03/04 | PASS | 4 | Named modal semantics, focus containment, exact close return, comparison result return after render, tour cleanup, and removed-invoker fallback passed at desktop and mobile in both engines. |
| FRAME-03/05 | PASS | 4 | Dallas and Argyle default finance frames passed at desktop and mobile in both engines. |
| C-A11Y-01 automated portion | PASS | 2 | Keyboard tasks, 200% CSS root text resize, 320px reflow, and reduced motion passed in both engines. Overall C-A11Y remains PARTIAL because the manual work below is unverified. |

The map test changes the active table metric through turnover, spending, poverty, prediction, and turnover again. It requires one active control, metric-specific caption and note, descending finite values, missing values last, the selected Dallas row, and unchanged focus, URL, pin, extent, and disclosure. A test-only Houston turnover `null` patch proves missing values render as **Not published** rather than `0`; the fixture labels that patch `synthetic-edge-case`. Kenedy’s real `0%` remains a finite value.

The normal-state health probe visited Dallas, Houston, Tioga, Pineywoods Community Academy, and Argyle in each engine. Every district showed the recorded 20,587-row public context, a populated finance report, and no degraded banner. The unavailable fixture returned expected 503 responses, showed the live-finance warning, removed live finance KPIs, and retained the outcomes, economics, equity, and bonds artifacts, the economic/equity/bond charts, the district geomap, and the built-in heatmap.

The recorded fixture contains **37 deterministic public GET responses** captured from `https://txisd.dev` at `2026-10-07T23:42:55.403985+00:00`. Its 37 SHA-256 entries cover the raw HTTPS response bytes before JSON parsing and pretty serialization. The test does not reinterpret those hashes as canonical JSON hashes.

Argyle’s FY 2025 frame uses the read-only public evidence in `docs/evidence/mcp/framing-argyle-public.json` (`B6C0C9ACFDDFF1898B73FC2E2B6A63245868B1FA42DE000FE840C0DD0413F1F9`) plus bounded read-only peers, dollar, turnarounds, and insights evidence. Its empty `breakdown`, `spending-detail`, and anomaly responses are synthetic unused-section stubs. They keep optional sections deterministic for the frame test and do **not** support a claim that Argyle has clean anomalies or no history. `FRAME-03/05` targets only the default finance hero, rank, caption, period, and qualifiers.

The frame assertions used these actual input facts:

| District | Fiscal year | All funds / student | Operations / student | Statewide percentile |
|---|---:|---:|---:|---:|
| Dallas ISD | 2025 | $23,746 | $14,210 | 70 |
| Argyle ISD | 2025 | $31,704 | $10,357 | 85 |

Request isolation was clean. The final passive workflows had zero uncaught page errors, recognized renderer failures, failed same-origin documents/styles/scripts/images/fonts, unexpected normal-state 5xx responses, or blocked-request attempts. The fixture guards cross-origin traffic, non-GET mutations, paid/private `/query`, `/feedback`, `/track`, and `/telemetry`; none was attempted. Offline tests intentionally generated only the expected fixture 503 responses.

The bounded route inventory rendered `/feed`, `/forensics`, `/geomap`, `/heatmap`, `/about`, `/sources`, `/map`, `/intel`, `/transparency`, and `/docs` in both engines. The root route was exercised by every complete workflow. This is evidence for those routes and workflows; it is not a claim that 200 routes were browser-rendered. The separate 72-cell visual capture is outside this report.

`scripts/contrast_check.py` passed all **40/40** reviewed light and dark token pairs. There is no `tests/test_visual_contrast.py` file, so no result is claimed for that nonexistent test.

## Accessibility limits

`C-A11Y-01` is **PARTIAL**. The automated browser portion passed keyboard tasks, exact dialog focus return, reduced motion, 320 CSS-pixel reflow, and a 200% root-font text-resize check in both engines. The 200% check changed the document root font size while preserving the CSS viewport; it was not native browser zoom.

The following remain **UNVERIFIED**:

- Manual screen-reader task execution
- Native browser zoom at 200%
- The planned 10-participant usability study
- External assistive-technology interoperability and blanket WCAG compliance

## Commands

```powershell
Set-Location tests\browser
npx.cmd playwright test public-regression.spec.js --reporter=line

Set-Location ..\..
.\.venv\Scripts\python.exe scripts\contrast_check.py
```

The final browser command reported `34 passed (3.2m)` with exit code 0. The contrast command reported `ALL PAIRS PASS`.

## Populated-report verification

Both engines passed `POP-COMP-01`: category values, actual hover and pin, distinct zero/unavailable branches, retained peer insights, visible default historical/nonpredictive qualification, and keyboard-accessible full interpretations. Tioga retained all nine actual turnarounds and its one insight. The source SHA-256 is `ef028ef84bdd3258739a83cbc4fce52483debc840e4a113a2552b9a9745bfb7e`; the final test SHA-256 is `a301123f0180d2f569e0679c3edcf870fa9451876288e93e0f97264fd3b61a8b`. This execution result is separate from the fresh independent review and the 72-cell area measurement.
