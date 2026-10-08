# Independent visual/model verification

> Historical review of an earlier implementation, retained as an audit record.
> The findings below apply to the source and evidence described here. See
> [final independent verification](final-portal-independent-verification.md)
> and [release evidence](../../RELEASE_EVIDENCE.md) for the current result.

Reviewer: fresh Luna verifier, 2026-10-07. Scope is limited to B-VIS-02, B-VIS-03,
C-MODEL-01, and C-BOUNDARY-01. No production or test files were changed.

## Results

| Criterion | Result | Evidence |
|---|---|---|
| B-VIS-02 | **FAIL** | `tests/test_visual_ratio.py` has 4 adversarial checks: union overlap, prose nested in visual, hidden/empty visual, and missing N/A reason. It does not cover the required padded prose card, enlarged empty plot, missing annotation, invisible content with screenshot evidence, or lower-page compensation cases. `capture-visuals.mjs:47-50` collapses every leaf without an ID to a tag selector (`p`, `span`, etc.), then compares only selector strings; the recorded final Dallas cases consequently claim `unclassified: []` with `inventory: []`, despite many visible narrative leaves. Every baseline/final case has `reviewed: false` and says manual semantic review remains required. `measure_visual_ratio.py:98-99` reports `manual_review_required` but never fails an unreviewed case. The collector captures only `fullPage: true` screenshots (`capture-visuals.mjs:60,103`), with no initial-viewport screenshot/rectangle path. |
| B-VIS-03 | **FAIL** | Independent validator run against `docs/evidence/visual/measurements.json` reports Dallas final Chromium light visual shares of **75.44%** (1440×900), **74.08%** (768×1024), and **61.45%** (390×844), each with `visual/prose ratio fails 95/5 target`; the current verification record reports the same values and Firefox is materially the same. The final evidence contains only Dallas cases (12 browser×viewport×theme cells), has no prototype phase, and has no independent initial/full results. Required caveats remain visible, but the target is not met. Largest prose sources in the 1440px final case are `#outcomes-support` (89,877 px²), `#eq-trap` (76,809), the generic explanatory `p` under outcome/economics sections (60,934 and 60,512), `#bond-b5-sub` (59,755), and `#hero-sub` (46,580, duplicated in the region list). |
| C-MODEL-01 | **PASS** | `static/visual-components.js:16-27` is the sole retention implementation: finite `[0,100]` input, six periods, `10 * (1 - turnover/100) ** 6`, unrounded and rounded values, `modeled` status, and cohort/equal-probability assumption. `static/index.html:2292-2301` sends both district and peer turnover through that function; `static/index.html:2837-2843` does the same for the peer/wow card. The visible card note at `static/index.html:2319` includes the source year and hypothetical district-cohort qualifier. The old building/individual forecast wording is absent. From `tests/browser`, `npm run test:unit` passes all 1 test, covering 0→10, 100→0, 20→3, 16.8→3, 18.1→3, null→missing, and invalid bounds→unverified. |
| C-BOUNDARY-01 | **PASS (planned source scope)** | The C additions are dependency-free vanilla JS (`static/visual-components.js`), nested pinned Playwright tooling/evidence, and one explicit `/static/visual-components.js` route (`src/api.py:2397-2405`). The adjacent `mcp_apps` import and MCP `list_resources/read_resource` wiring (`src/api.py:37,2624-2625`) are an explicitly coordinated D/E MCP integration in the shared API file, not an unplanned C architecture change. No vendor CDN/framework/build migration, startup/database change, analytics expansion, or production build migration was found in the C-owned helper/browser additions. Shared A/MCP worktree changes are outside this criterion's C ownership boundary. |

## Bounded repair targets

For the next Terra attempt, keep the change bounded to the visual collector/manifest
and the named renderer groups. Fix identity-preserving inventory and initial/full
capture first; then reduce narrative geometry in the existing `static/index.html`
renderer groups, starting with `#outcomes-support`, `#eq-trap`, the outcome/economics
explanatory paragraphs, `#bond-b5-sub`, `#hero-sub`, and `#money-support`. Do not
reclassify prose as visual or exclude required caveats. The C model and planned
source boundary already pass.
