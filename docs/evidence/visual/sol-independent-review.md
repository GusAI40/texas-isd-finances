# Independent visual/model verification

> Historical review of an earlier implementation, retained as an audit record.
> The findings below apply to the source and evidence described here. See
> [final independent verification](final-portal-independent-verification.md)
> and [release evidence](../../RELEASE_EVIDENCE.md) for the current result.

Reviewer: fresh Luna verifier, 2026-10-07. Scope: B-VIS-02, B-VIS-03,
C-MODEL-01, and C-BOUNDARY-01. This is a read-only review of the Sol result;
no production or test files were changed.

## Results

| Criterion | Result | Evidence |
|---|---|---|
| B-VIS-02 | **FAIL** | `tests/test_visual_ratio.py` contains only four adversarial checks (union overlap, prose nested in visual, hidden/empty visual, and missing N/A reason). It does not cover the plan's padded prose card, enlarged empty plot, missing annotation, invisible content with screenshot evidence, or lower-page compensation cases. `tests/browser/capture-visuals.mjs` identifies unlabelled leaves by tag/DOM path, but the recorded final cases have `inventory: []`, `unclassified: []`, and `reviewed: false`; therefore semantic coverage and manual classification are not evidenced. The collector does record separate initial screenshots and `initial_regions`, but the ratio validator does not require `reviewed: true` and only emits `manual_review_required`. |
| B-VIS-03 | **FAIL** | Fresh `python scripts/measure_visual_ratio.py --input docs/evidence/visual/measurements.json` exits 1. Its output has 96 results: all 72 baseline cells fail the 95/5 ratio, 24 final cells pass, and the required `prototype` phase is missing. Final coverage is only `dallas` and `statewide` (12 cells each); `small`, `charter`, `compare`, and `unavailable` have no final captures. The final Dallas/statewide cells do have both `initial_screenshot` and full screenshot paths and the validator reports 100% visual share, but the empty inventory/manual-review state means this cannot establish the plan's complete semantic gate. Representative screenshots show populated dollar graphics and retention evidence, while the desktop Dallas full capture also contains very large blank stretches between report groups; no evidence establishes those as intentional or proves all required renderer states. |
| C-MODEL-01 | **PASS** | `static/visual-components.js:16-27` defines one bounded six-period function, `10 * (1 - turnover/100) ** 6`, with modeled status, rounded output, missing/null handling, invalid-range handling, and a hypothetical equal-probability ten-teacher cohort assumption. `static/index.html:2289-2298` and `:2948-2957` use it for the two retention renderers; the visible note at `:2316` carries source year and district-cohort qualification. The browser unit suite covers 0, 100, 20, 16.8, 18.1, null, and invalid bounds. No individual/building forecast wording remains in the reviewed implementation. |
| C-BOUNDARY-01 | **PASS (source scope)** | The C-owned additions are dependency-free `static/visual-components.js`, nested browser tooling/evidence, and the explicit static helper route in `src/api.py`. No vendor CDN/framework/build migration, startup/database change, analytics expansion, or production build migration is present in the reviewed C files. Existing unrelated working-tree changes are outside this criterion's ownership boundary. |

## Bounded gaps

1. Add the missing prototype phase and final captures for small, charter,
compare, and unavailable states before claiming the full B-VIS-03 matrix.
2. Preserve element identity in inventory and require a positive manual semantic
review flag; make unknown/unclassified visible leaves fail validation.
3. Add the six named adversarial fixtures from the implementation plan and make
the validator fail missing annotations and unreviewed cases.
4. Recheck the full Dallas report capture's large blank stretches and renderer
states with a fresh browser run; do not treat a 100% rectangle score as proof
that all charts or narrative are meaningfully rendered.

This review makes no claim about participant outcomes or screen-reader
compliance; those remain separate gates.
