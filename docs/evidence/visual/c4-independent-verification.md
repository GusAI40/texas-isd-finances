# C4 independent verification

> Historical failed workflow review, retained with its original source hashes.
> It does not describe the final 34-test suite. Current execution evidence is in
> [public workflows](public-workflows.md); the fresh independent result is in
> [final independent verification](final-portal-independent-verification.md).

**Verifier:** fresh Luna read-only pass

**Date:** 2026-10-07

**Revision:** `de49c2f6c21baf4e818c8be284deec8512e0a692` (working tree had concurrent changes)
**Scope:** C-FLOW-01, C-OFFLINE-01, and C-A11Y-01 in `docs/VISUAL_IMPLEMENTATION_PLAN.md`. No source, fixture, or browser-test changes were made.

## Execution evidence

Command, run from `tests/browser` against the existing local public server:

```text
npm run test:public -- public-regression.spec.js --project=chromium --project=firefox --reporter=line
```

Result: **24 tests: 18 passed, 6 failed, 1m24s**. The 12 statewide finder shell cases (3 viewports × 2 themes × 2 browsers) passed. CSV export passed. The PNG test passed only its current PNG signature and `>500` byte assertions; it did not establish dimensions or nonblank pixels.

Source hashes at verification time (SHA-256):

| File | SHA-256 |
|---|---|
| `static/index.html` | `682e7507a2003daafeac48d386aa2ade5284110b1df542b02c30c0184c7088aa` |
| `tests/browser/public-regression.spec.js` | `77d2552cabd9ddd557f287fe74515e5367994ec7ff235444072aaf5a448b4994` |
| `tests/browser/public-fixtures.js` | `e7682ec169660c8adbf1cda3971d5ef0fd0441d8bcedabc9080aa0e202cc99d4` |

The failed browser artifacts are under `tests/browser/test-results/` and were produced for both Chromium and Firefox.

## Acceptance results

### C-FLOW-01 — **FAIL**

The criterion requires search/deep links/lenses/comparison/section navigation/maps/filter/CSV/PNG/print/source/citation flows in all 12 browser × viewport × theme combinations. The current test proves only the 12 finder shells plus the individual export checks. It does not prove the complete matrix for the deeper flows, map filtering/alternatives, print reflow/content, or PNG pixel/dimension validity.

Two failures reproduce in both engines:

* `public-regression.spec.js:38-66` fails while selecting a source disclosure. The locator chooses the first `.ledger-detail` whose entire text matches `/source|TEA/i`; the opened body is a “That is 50 cents on debt...” calculation explanation and has no `Source`. A direct DOM inspection found a later, real source disclosure whose body begins `Source: TEA Summarized PEIMS Actual Financial Data ...`. This is a **stale/ambiguous test selector**, not evidence that the source panel is absent.
* `public-regression.spec.js:97-110` fails at `#btn-map`. In the loaded Dallas report the element exists but computed `display:none`, zero-sized at `(0,0)`. The current visible navigation has `a[href="/map"]`; the screenshot and DOM inspection show no visible `#btn-map` action. This is a **stale selector against the current UI**, so the test does not prove a broken map handoff. It also leaves the required map/filter/alternative flow unverified.

The CSV test passed and produced a `.csv` containing a year/fiscal header, `2025`, and the recorded Dallas value. The PNG test verified the PNG magic bytes and file size only; C-FLOW's required nonblank dimensions/pixels remain **unverified**. The print check only stubs `window.print` and checks a boolean, so report identity, sources, values, clipping, and media reflow remain **unverified**.

### C-OFFLINE-01 — **FAIL (test assertion is stale; product behavior partially observed)**

The unavailable-fixture test fails in both engines at `public-regression.spec.js:112-122` because the first matching role image is `#pennies`, a zero-sized artifact-dependent placeholder. A direct unavailable-route inspection found explicit unavailable text, `#outcomes-section` visible, and later visible SVG charts (`#econ-levers`, `#eq-bars`, `#bond-*`, `#trendchart`, `#peerchart`, `#moneychart`) with nonzero bounds. This identifies the failing assertion as a **stale `.first()` selector**, rather than proof that all artifact content disappeared.

The fixture blocks mutation methods and external origins; the passing offline page had no uncaught page errors in the focused inspection. The run still does not satisfy the criterion because the committed test is red and does not assert vendor-free map usefulness, all unavailable labels, or a complete no-private/paid-request audit.

### C-A11Y-01 — **FAIL (coverage incomplete; no blanket claim)**

The two current C-A11Y cases pass their narrow 390×844 dark checks in Chromium and Firefox: semantic trend table/header presence, theme control visibility, one pressed lens, `scrollWidth <= 410`, metadata/citation text, and HTTP 200 responses for the listed routes. They do not cover the approved criterion's required actual tasks for finder/results, section navigation, lenses, comparison, source/table disclosures, dialogs, exports, and return focus. They also do not exercise the required 200% zoom or 320-CSS-pixel representative states, contrast evidence, or an actual screen reader. The 12-state shell loop is not a substitute for those tasks. Therefore C-A11Y remains **FAIL for acceptance coverage**, with no claim about assistive-technology compliance.

## Handoff

The public workflow work is not certifiable from this run. The first repair pass should update the two ambiguous selectors (`.ledger-detail` source selection and hidden `#btn-map`) or add stable behavior-level locators, then rerun the deep flow in both engines. Separately, add real PNG dimension/pixel checks, print-content/media assertions, map filter/alternative checks, and the 200%/320px keyboard coverage before reopening C-FLOW/C-OFFLINE/C-A11Y. This verifier made no implementation or fixture changes.
