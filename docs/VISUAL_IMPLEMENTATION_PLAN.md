# Packages B/C: public visual experience implementation

**Prepared:** 2026-10-07. **Parent:** [VISUAL_PLUGIN_EXECUTION_PLAN.md](VISUAL_PLUGIN_EXECUTION_PLAN.md).
**Evidence:** [dated audit](AUDIT_2026-10-07.md); targeted current `static/index.html`,
`static/design.css`, `src/api.py`, `tests/test_render.py`, and public artifacts.
**Status:** executable refinement, not implemented or measured results.

## Outcome, design direction, and scope

A parent or taxpayer reaches district search immediately, sees what the money
buys through meaningful charts and comparisons, and can inspect the year, units,
source, and assumptions without reading repeated introductions. Preserve all
current report sections, audience lenses, navigation, maps, filters, exports,
district links, source access, and offline artifact reports.

Use a restrained civic-data editorial design: the existing ink-on-paper palette,
one blue accent, clear type hierarchy, tabular numbers, purposeful chart marks,
and compact provenance labels. Follow `static/design.css`'s existing tokens and
font families; do not introduce fonts/CDNs, gradients, chart shadows, decorative
illustrations, animation dependencies, a framework, or a new production build.
The frontend-design skill informs hierarchy and composition; the repository's
explicit visual rules take precedence over that skill's optional decoration.

Retain the handwritten HTML/CSS/SVG/Canvas architecture. Extract only reusable
metric semantics and the retention calculation into one small vanilla JS file;
do not rewrite the page's state/data fetching or existing chart library functions.
No paid NLP call, analytics expansion, recipient operation, production SQL,
deployment, or publication belongs to B/C implementation.

Work is shared: Package A owns SQL, data builders, generated dictionaries, its
tests, and encoding fixes in `tests/test_api.py`, `tests/test_wow.py`, and other
named tests. B/C must not touch those files during A execution. New asset-route
tests belong in a separate file. One UI implementer owns `static/index.html` at
a time; sequence slices below. D/E must coordinate later changes to `src/api.py`
and `static/visual-components.js`.

## Existing interfaces and integration points

- `state` in `static/index.html` owns district, summary, compare, outcomes,
  economics, bonds, and other payloads. `loadDashboard()` loads 15 independent
  endpoints with fallback handling, then `renderAll()` isolates renderer failures.
  Preserve those boundaries and the district name fallback.
- District URL state is `?d=<six-digit-ID>`. Explicit links override stored district
  state. `tisd_theme` is applied before first paint; brand navigation uses the
  existing one-shot home behavior. Preserve all three behaviors.
- `renderOneChild(o)` and `wowFacts()` currently derive teacher retention with
  powers five and six respectively. `renderOneChild` also prints a five-year
  caveat. Both must call the shared function below.
- `dollarParts()` prefers the finance summary's same-year per-student number.
  Preserve that precedence and explicit artifact fallback; do not recompute a
  different measure for a prettier chart. A's corrected source contract controls
  finance certification.
- Reuse existing `linBtn()`/`showLineage()`, `renderEconTable()`, `renderBondTable()`,
  `csvDownload()`, `pngDownload()`, `selectDistrict()`, `selectCompare()`, and
  `buildNav()`. Extend their semantics narrowly; don't replace them with copies.
- FastAPI serves assets individually, including `/static/design.css` and
  `/static/ask.js`. A new JS file needs its own explicit route. Never mount all
  of `static/` or add Vercel rewrites.

## Fixed test states and evidence provenance

Create `tests/browser/fixtures/public-states.json` with endpoint-shaped public
responses, source revision/hash, capture date, origin (`artifact`, `read-only API`,
or `synthetic edge case`), and expected values independently derived from sources.
Copy only required public fields. No credentials, contacts, private operations,
or bulky full-state data dump. Use actual static payload handlers in the local
server where possible; intercept only DB responses or deliberately failing edges.

| State ID | Route/state and purpose |
|---|---|
| statewide | `/` with empty storage: statewide analytic landing and district finder. |
| dallas | `/?d=057905`: Dallas FY2025 finance, 2024 outcomes; mixed vintages must remain visible. Turnover pair is `[16.8,18.1]` in the current outcomes artifact. |
| small | `/?d=091907`: Tioga, currently 662 students in economics; modest scale must not inherit Dallas chart assumptions. |
| charter | `/?d=003801`: Pineywoods Community Academy; national artifact's absent reason is `charter`, not zero or unknown. |
| compare | Dallas `057905` plus Houston `101912`, selected through the actual comparison UI; shared-year like-for-like comparisons. |
| unavailable | Dallas with summary/peers/anomaly/breakdown/detail DB routes deliberately returning unavailable responses and `/query` unavailable; artifact outcomes/economics/bonds/maps still work. |
| missing | Separate synthetic fixture patches to a real response: null measure, legitimate zero, suppressed/unknown status, and invalid denominator. Label this test-only data; never publish it. |

Use the actual metadata vintage for every fixture rather than setting all periods
to 2025. A-corrected finance values may be used as explicitly marked expected
fixtures before production changes; never claim they are current live responses.
Unresolved anomaly/freshness findings remain visible qualifications and cannot
acquire a green verified badge through this redesign.

## Proposed shared interface: define before wiring

`static/visual-components.js` exposes one browser namespace, `window.TxisdVisual`,
without a dependency or global page state. Load it synchronously before the
existing inline application script. Node unit tests execute this same file in
an isolated VM; do not duplicate the implementation in tests.

```js
// Documentation contract; implementation belongs to C1 below.
Metric = {
  id, label, value, unit, period, population, denominator,
  status,             // observed | modeled | missing | not_applicable | unverified
  source: { label, url, period },
  limits: [],         // material limits remain visible; details may expand
  model: null        // or { periods, assumptions, formula }
};
TxisdVisual.teacherRetention(turnoverPercent); // result below, or missing/invalid
TxisdVisual.renderMetricMeta(container, metric);
TxisdVisual.renderAccessibleTable(container, columns, rows, caption);
```

Build DOM text safely (`textContent`, validated source URLs); never interpolate
untrusted source labels into HTML. Existing endpoints retain their contracts;
page-local adapters map their values to Metric, without guessing missing metadata.
Make source/math available in one activation and leave period/unit/status plus
critical model qualifiers visible. Tables use captions, column/row headers and
explicit missing labels; an SVG/Canvas alt summary alone is not a data table.

**Retention contract:** a hypothetical cohort of ten district teachers, measured
from the beginning of kindergarten through the end of fifth grade, models six
annual exposure periods labeled K, 1, 2, 3, 4, 5. Use
`expected = 10 * (1 - turnoverPercent / 100) ** 6`; round only the headline with
`Math.round(expected)`. Return the unrounded expected value, rounded count,
periods `6`, status `modeled`, and assumption text. Accept only finite numeric
percentages in `[0,100]`; null/undefined is missing, negative/over-100/non-finite
is invalid/unavailable. Do not silently clamp bad source data.

Both cards and peer comparison use that function. For Dallas's 16.8% and peer
18.1%, both round to 3/10. Test 0→10, 100→0, 20→3, and null/invalid cases.
Visible caption: **“Modeled over six years • 2024 district turnover held constant”**
using the actual source year. Expanded math names the annual-period convention,
constant rate, and equal retention probability assumption. Replace “teachers in
the building” or “teachers your child meets will still be here” with a hypothetical
district-cohort description: district turnover is not building-level tracking or
a forecast of particular people. Preserve the observed turnover percentage itself.

## Auditable 95/5 measurement

Implement the parent ratio `V/(V+P) >= .95`, `P/(V+P) <= .05` without moving or
hiding critical context. V contains meaningful data components; P contains
standalone narrative, including paragraphs inside a card. Numeric values and
their necessary labels/units/periods/status are component semantics. A box with
prose does not become V by receiving a chart class or border.

The collector writes viewport CSS-pixel rectangles and classifications to
`docs/evidence/visual/measurements.json`; `scripts/measure_visual_ratio.py`
validates them and emits `docs/evidence/visual/visual-ratio.json`. It must:

1. Measure the original page before edits using an external selector manifest,
   then prototype and implementation with the same rubric. Store source revision,
   browser/version, viewport, theme, state, full screenshot, initial viewport
   screenshot, and annotated overlay. Missing baseline means UNVERIFIED.
2. Record tight content bounds, not the outside padded card. For text use Range
   rectangles; for SVG/Canvas use the actual declared plot/axis/legend bounds,
   checked against the rendered screenshot. Numeric-card labels/value bounds
   exclude whitespace. Necessary empty axis space belongs to a fixed-aspect plot;
   arbitrary enlarged canvases/backgrounds do not. Freeze plot aspect ratios and
   typography in the design contract before evaluating ratios.
3. Use union area with overlapping boxes counted once. Nested prose takes P
   precedence over V; report conflicting labels. Crop initial-viewport rectangles
   to the visible analytic area and separately measure the full default report.
   Segment long-page screenshots consistently; sticky navigation does not get
   counted repeatedly. Both initial and full-report ratios must pass independently.
4. Enumerate excluded global navigation, input controls, footer/legal blocks,
   expanded source panels, and alternate accessibility tables. Report each area,
   reason, and content text separately. A parent analytic wrapper cannot be excluded
   wholesale. Necessary disclaimers, model status, missing-data states, and years
   stay in the default experience; source disclosure cannot conceal a caveat.
5. Inventory visible text and rendered analytic elements, including unclassified
   nodes. A result fails validation with unclassified analytic content, unknown
   selectors, zero analytic area, missing screenshot, overlapping contradictory
   labels, or a hidden/zero-opacity supposed visual. A search-only or empty state
   is N/A with an explicit reason, not PASS. Displayed empty-state explanation
   counts as prose; do not pad an unavailable report with fake charts.
6. Include adversarial unit fixtures: prose inside a numeric card, nested/overlapping
   boxes, huge padding, a deliberately enlarged empty plot, invisible content,
   missing annotations, and a lower-page chart compensating for a prose-heavy
   first view. Class changes alone must not improve the score. Manual reviewer
   inspection of semantic classifications and plots is required; software cannot
   certify that a graphic meaningfully represents data.

Do not collapse substantive data sections solely to reduce measured content.
Expanded source explanations and table alternatives remain excluded consistently
at baseline/prototype/final. When an analytic section can expand, measure its
primary expanded state too and publish that result. If a required caveat makes
the ratio fail, retain it and report FAIL rather than shrinking its font or hiding it.

Run the seven states at **1440×900, 768×1024, 390×844**, both light/dark themes,
100% zoom. The publication matrix uses Chromium plus Firefox; record actual
viewport/dimensions. State ratios are targets pending measurement, not current
achievements. Separate accessibility/usability gates prevent optimizing only area.

## Bounded implementation slices and ownership

| Slice | Dependencies | Owned files / focused action |
|---|---|---|
| B1a: browser harness | Audit; independent of A numerical repairs | `tests/browser/package.json`, `tests/browser/package-lock.json`, `tests/browser/playwright.config.js`; add pinned development-only Playwright and fixture/server runner. Keep this nested under tests so it adds no production bundle/build. |
| B1b: baseline capture | B1a | `tests/browser/capture-visuals.mjs`, `tests/browser/fixtures/public-states.json`, `tests/browser/visual-regions.json`; capture the unmodified baseline with provenance and explicit classifications before UI changes. B1 below means B1a plus B1b. |
| B2: scoring contract | B1 | `scripts/measure_visual_ratio.py`, `tests/test_visual_ratio.py`, `docs/VISUAL_DESIGN_CONTRACT.md`; implement geometry validator/adversarial tests and freeze visual rules, including classification/exclusion manifest. |
| B3: prototype and participant protocol | B1/B2 | `design/public-portal-prototype.html`, `docs/PUBLIC_USABILITY_PROTOCOL.md`, `docs/evidence/public-usability.json`; working local prototype for statewide/Dallas/comparison and unavailable state using the fixed fixtures; capture all viewport/themes and correct ratio failures. No production route for prototype. |
| C1: semantic helper and cohort | B contract; can precede live A application | `static/visual-components.js`, `tests/browser/visual-components.test.cjs`, `src/api.py` (one explicit JS asset route only), `tests/test_visual_assets.py`; implement/test shared interface and six-period cohort model before index wiring. |
| C2: entry and district summary | B3 + C1; A contract required for certified finance figures | `static/index.html`, `static/design.css`; move the existing finder ahead of repetitive intro copy, concise statewide dollar graphic, district identity/summary/lens controls. Preserve original element IDs/listeners; move trust prose into an accessible disclosure with visible independent/source/status cues. Wire both retention renderers to C1 and replace unsupported prediction wording. |
| C3: report visuals and semantic parity | C2 | `static/index.html`, `static/design.css`, `tests/browser/public-portal.spec.js`; address three renderer groups sequentially: (a) dollar/outcomes/economics; (b) trend/peers/money/object/program; (c) bonds/equity/takeover/insights/flags/turnarounds. Retain all datasets/controls, existing SVG helpers, section IDs, sources, and tables; simplify prose only with equivalent visible labels and expandable explanation. Snapshot/verify each group before the next. |
| C4: accessibility and route regression | C3 | `tests/browser/public-regression.spec.js`, `scripts/contrast_check.py`, `tests/test_visual_contrast.py`, `docs/evidence/visual/verification.md`; exercise the complete matrix, fix only C2/C3 owned UI/token files for reproduced defects, and distinguish token tests from whole-page accessibility. |

Evidence screenshot/JSON outputs are owned by B1/C4 under
`docs/evidence/visual/`; retain representative annotated images plus machine
measurements rather than committing duplicate huge captures. B1 is test harness
setup, not a runtime redesign. Pin the reviewed Playwright version and matching
browser binaries when installed; no floating `latest`. Use local dependencies
only and block external network in deterministic tests except deliberate fixtures.
An optional local axe-core dev dependency may be pinned for automated checks;
it never runs in the public page and never substitutes for keyboard/screen-reader
testing. Avoid touching A-owned root dependency/CI files during this work.

## Verification commands and observable checks

Provide nested npm scripts `test:unit`, `capture:baseline`, `capture:prototype`,
`capture:final`, and `test:public` in `tests/browser/package.json`. Commands run
from that directory with `npm ci`; they must fail if Chromium or Firefox is absent
instead of silently skipping. Launch a local FastAPI server through the existing
locked Python environment on a checked unused port; pass its URL to Playwright,
hide Windows subprocess windows, and stop only the server this runner owns.
Do not interact with any existing port-3000 service. A local-only prototype server
serves `design/` and test assets, not production configuration.

Run `python -m pytest tests/test_visual_ratio.py tests/test_visual_assets.py
tests/test_visual_contrast.py -q`, `python scripts/measure_visual_ratio.py
--input docs/evidence/visual/measurements.json`, `python scripts/check_static_js.py`,
and `python scripts/contrast_check.py`. Extend JS parsing to the new helper through
its direct `node --check` npm step, without changing A-owned script files.

Browser assertions must observe behavior, not just HTML presence:

- Search then select Dallas; district name, six-digit ID, values, year and source
  match fixtures. Switch district, navigate to the boundary map and back, and
  confirm the new district is carried at click time. Brand returns statewide;
  explicit `?d` overrides a previously stored district. Ambiguous district names
  require selection rather than silently choosing the first match.
- Compare Dallas/Houston, remove comparison, and switch lenses without losing
  selection. Inspect at least one finance, outcome, tax, bond, and national widget;
  tables/source panels and chart labels agree with the exact fixture vintage,
  units, denominator and status. Dataset coverage stays separate from registry size.
- Open all populated report sections through section navigation and full scroll;
  assert visible content, nonzero bounds, opacity/visibility, and no renderer
  warnings. Injected unavailable responses must preserve artifact sections and
  name missing features. Zero is a value; null is not drawn as zero. Chart gaps
  stay gaps rather than connected implied observations.
- Exercise real CSV download and parse expected headers/district/year/value;
  exercise chart PNG download and verify valid nonblank image dimensions; inspect
  print media for report identity, values, sources and non-clipped charts. Preserve
  existing citation copy, chart selectors, tax-value input and feedback/ask entry.
  Stub mutation/paid endpoints during browser tests; test display/error paths
  without sending feedback, telemetry, email, or paid queries.
- Visit existing public navigation destinations `/`, `/feed`, `/forensics`,
  `/geomap`, `/heatmap`, `/about`, `/sources`, `/map`, `/intel`, `/transparency`,
  `/docs` and current public report links captured in the baseline. Both vendor-free
  map and similarity map must render, select/filter as currently supported, and
  expose accessible alternatives. `/heatmap` without a token must retain its honest
  optional-provider state. No map implementation changes are planned unless a
  reproduced shared-CSS regression requires a separately coordinated fix.
- Collect uncaught page errors, failed owned-asset requests, unexpected external
  requests, and `section ... could not render` warnings as failures. Explicitly
  asserted unavailable-response cases are separate expected failures; do not use
  blanket console/request suppression.

Run Chromium and Firefox across all three viewports and both themes. Extend to
200% zoom and a 320-CSS-pixel reflow check for representative core states. Required
data visualization scroll areas may scroll with clear controls; the page itself
must not hide essential content horizontally. Theme persistence must apply before
the first paint, and reduced-motion preference must not leave content invisible.

Keyboard checks cover finder/results, section navigation, lenses, comparison,
source disclosure, table disclosure, dialogs, exports and return focus. Screen-reader
checks cover the five public tasks with an actual available reader; if unavailable,
record UNVERIFIED rather than substituting a DOM snapshot. Verify applicable WCAG
2.2 AA semantics and contrast: normal text 4.5:1, large text 3:1, necessary UI/marks
3:1. Decorative dividers may remain low contrast; identify them explicitly and
test meaningful focus/boundary/series tokens separately. Do not change the divider
threshold alone and claim accessibility is fixed.

## Real-audience protocol and completion criteria

Recruit at least ten consenting adults drawn from parents/taxpayers/public readers,
including mobile users and people unfamiliar with school finance. Recruitment is
not authorized external outreach in this implementation task. Prepare the protocol
now; record participant testing **UNVERIFIED** until actual participants are available.
Do not populate simulated records or rebrand prior administrator simulations.

Five unaided tasks: find the correct district; interpret a spending/student trend;
compare matching district measures; distinguish rate from an illustrated tax bill;
find source/year and distinguish observed from modeled retention. Proposed targets:
at least 8/10 succeed on each task, median at most 60 seconds for the first four
and 90 seconds for the fifth, with no unresolved severe inversion of meaning.
Record anonymized task result/time/assistance/device and comprehension errors,
never names, contact details or recordings in public evidence. Retest failed tasks
after changes and preserve earlier results. Participant targets do not block coding
or local checks; they remain an independent release gate.

| ID | PASS evidence required |
|---|---|
| B-VIS-01 | Baseline, prototype and final annotated captures exist with identical classification rules, revisions and fixture provenance; no invented baseline percentages. |
| B-VIS-02 | Measurement tests reject overlaps/double counts, padded prose cards, empty enlarged plots, hidden elements and missing classifications; initial/full report results are independent, exclusions itemized and manually reviewed. |
| B-VIS-03 | Every applicable primary analytic state meets ≥95% V/≤5% P across three viewports/two themes; required caveats remain visible. Legitimate N/A states have reasons, not a PASS score. Chromium/Firefox dimensions and results are recorded. |
| C-MODEL-01 | Both retention cards and peers use the same six-period function; source pair 16.8/18.1 produces 3/10 for both, boundaries/missing/invalid pass, source year and district-cohort model assumption are visible. No individual/building-level forecast remains. |
| C-DATA-01 | All measured widgets retain source, unit, period, population/denominator and status; chart/table/source-panel fixtures agree. Missing, zero, not-applicable, unverified, and modeled states remain distinct. |
| C-FLOW-01 | Search/deep links/lenses/comparison/section navigation/maps/filter/CSV/PNG/print/source/citation flows pass behavior checks in the 12 browser×viewport×theme combinations. No existing public route or capability is removed. |
| C-OFFLINE-01 | Unavailable DB/LLM leaves artifact reports and vendor-free maps useful with explicit unavailable labels; zero unexpected renderer errors and no paid call or private data leakage. |
| C-A11Y-01 | Automated checks plus actual keyboard/screen-reader tasks prove required names/roles/tables/focus/contrast/reflow/non-color cues; findings and any unavailable manual evidence are reported without claiming blanket compliance. |
| C-BOUNDARY-01 | Only planned vanilla components and one explicit asset route are added; no vendor/CDN/framework/build migration, startup/database change, analytics expansion or modification of A-owned work. |
| B-USER-01 | Actual ten-participant results meet the proposed five-task targets; absent participant evidence remains UNVERIFIED and blocks a tested-public-usability claim. |

Record PASS/FAIL/UNVERIFIED per ID in the C4 evidence file. A source arithmetic
gate, actual participant gate, or actual assistive-technology gate must not be
substituted with a screenshot ratio. This plan completes local B/C implementation
and evidence preparation; D/E host/plugin work and F release remain separate.
