# C4 public workflow repair refinement

Prepared 2026-10-07 by Astra. This explicitly authorizes two bounded repairs
identified by actual C4 behavior checks. It does not expand into a site audit,
change chart geometry, replace the frontend, or weaken any acceptance criterion.
Only this planning document was changed by the planner.

## Confirmed source evidence

- `static/geomap.html`: `setMetric` updates `metric`, button `aria-pressed`,
  legend, default panel, and canvas, but never calls `renderA11yTable`.
  Furthermore, that renderer hardcodes turnover filtering, turnover ordering,
  the turnover note, and the turnover caption. Merely calling it again is
  insufficient. All six existing columns and district links must remain.
  The actual map payload supplies Dallas `t=16.8`, `s=15518.8`, `p=87.2`,
  `g=5.5`, `e=139096`; tests must use this payload rather than the different
  finance-summary fixture. Its inspected metadata identifies boundary source
  and charter absence, but has no per-metric year. Do not invent metric vintages.
- `static/index.html`: disclaimer and comparison sheets have no dialog role,
  modal semantics, initial-focus setup or focus trap. `closeSheets` only hides
  the overlay/sheets. More > Disclaimer closes the containing `<details>`
  before opening the sheet, so blindly focusing its hidden opener also fails.
  Comparison selection already invokes `closeSheets`; that path must receive
  the same restoration behavior as Escape and dismissal. The tour shares
  the overlay/close helper and must not regress when its lifecycle is adjusted.

## Explicit ownership and sequence

1. Root assigns a Terra implementer exclusive ownership of **only
   `static/geomap.html`** for the map repair below. This is the explicit C4
   exception permitting work outside the original index/CSS files for the
   reproduced defect. Terra is not alone in the codebase and must not revert
   others' edits or modify index, fixtures, or browser tests.
2. The existing visual/UI Sol owner retains exclusive ownership of
   **`static/index.html`** and implements the sheet focus lifecycle below.
   Coordinate with its existing finance-label changes; do not give a second
   implementer this file. No framework, dependency, production route, chart
   resize, or unrelated popover rewrite belongs to this repair.
3. The existing public-workflow Sol owner owns the **existing C4 browser test
   and evidence files already assigned to it**. Keep the reproduced assertions
   red until the UI is repaired. Do not edit UI from this test task; do not make
   focus restoration conditional, catch/ignore failures, or accept an arbitrary
   focused element as success.
4. Run focused map/dialog checks first, then the existing C4 regression matrix.
   Fresh verifier independently compares results with the criteria below.
   Coordinate current final screenshot provenance with the visual owner after
   the last index change; retain the unchanged 95% initial/full threshold.

## Map repair contract

Use the existing `metric`, `METRICS`, and `geo.d` as the single selection/data
source. Derive caption, note, selected measure, ordering, and units from the
active metric. Refresh the table when `setMetric` runs and on initial load.
Before data arrives, a metric activation must safely update selection and defer
data rendering instead of throwing; final initialization uses that selection.

Preserve all six columns, links, all metric buttons, search, district panel,
neighbors, boundary interactions, zoom/reset, and the disclosure's open/closed
state. Keep all mapped district rows in the alternative, sort finite selected
measure values highest first with a deterministic name/ID tie-break, and place
missing selected measures last. Explicitly name missing values rather than
turning them into zero. The caption states the active measure and published-value
count out of total mapped districts; the note states the sorting and missing
convention. Preserve the charter-boundary qualification and existing source
citation. Do not carry the old turnover fiscal-year assertion into other metric
captions; use only supported source years, and qualify absent metric vintage
without inventing one. No map data rebuild is authorized here.

Selecting a district still updates its existing panel and full-report link.
Table cells must match the same district's payload/panel with only the existing
formatting precision applied. Metric changes must not reset the pinned district,
map extent, or current disclosure state. The all-district alternative must not
quietly become a one-district table after a pin/search.

## Sheet focus repair contract

Add a small shared vanilla lifecycle for the existing sheets. Each opened modal
has an accessible name linked to its visible heading, `role="dialog"`, and
`aria-modal="true"` while active. Keep sheets hidden by default and outside the
tab order when closed. Capture the actual invoking element before closing More
or changing focus. Remember any containing disclosure state needed to restore
that opener. Store the opener once per open/close lifecycle, not per tour step
or rerender; permit only the existing single active sheet.

On opening the disclaimer, focus its heading/container with `tabindex="-1"`
or its existing close control. On opening comparison, focus `#csearch`. Tab and
Shift+Tab remain inside the current sheet, including dynamically added comparison
results. A sheet with no eligible controls keeps focus on its own container.
Prevent background keyboard focus while active with the narrowly appropriate
focus trap/inert handling, restoring any prior inert state on close. Do not hide
the active sheet itself by making its ancestor inert.

Route existing close actions, overlay dismissal, Escape, and successful
comparison selection through the same cleanup. Remove transient focus handling,
hide the sheet/overlay, and restore focus to the original connected, eligible
invoker. Specifically, More > Disclaimer > Got it must restore the More
disclosure's prior open state and focus **`#mm-disclaimer`**; it must not focus
the now-hidden button or silently settle on the document body. Opening through
`#open-disc` returns there. Comparison returns to **`#btn-compare`**, including
after selection and its subsequent render. If the original invoker was actually
removed, use the nearest surviving logical invoking control (the More summary
for its removed menu item, otherwise the existing district finder); test that
exception separately, never use it to excuse the normal path.

Keep the shared tour compatible: its first opening captures its invoker,
subsequent steps keep that invoker, and Skip/Done/Escape/overlay close restore
focus and clear highlights. Preserve tour step text, navigation, and persistence.
No audit or redesign of separate explanation/lineage popovers is authorized.
A visible close control inside the comparison sheet may be added if needed for
an explicit keyboard dismissal; it affects only the opened sheet.

## Objective browser acceptance

| ID | Required observed behavior |
|---|---|
| MAP-C4-01 | Open the table, activate turnover -> spending -> poverty -> prediction -> turnover with actual button interactions. Exactly the chosen button is pressed; caption/note name the active metric and coverage, selected-measure sort order agrees with the fixture, and stale turnover-only wording disappears for other measures. All original columns and district links remain. |
| MAP-C4-02 | Compare named district cells (including Dallas) with `/district-geo` values and corresponding panel values using documented formatting. A district missing turnover but having spending appears with its spending value; zero remains zero and null is explicitly missing. Missing selected values sort last. Synthetic patches used for edge cases are labeled test-only. |
| MAP-C4-03 | Search/select Dallas, change the metric, then use the full-report link: selected district/name/ID and URL remain correct. Changing metric preserves map extent and pin, table disclosure state and keyboard focus on the activated metric button. Zoom/reset and the original controls still function. Activation before payload completion causes no page error. |
| DIALOG-C4-01 | On Dallas, keyboard-activate More summary, then `#mm-disclaimer`. Assert a visible named modal and focus inside it. Activate `#disc-close` with Enter: modal/overlay close, More returns to its prior open state, and `document.activeElement` is exactly `#mm-disclaimer`. Repeat direct `#open-disc` invocation and assert exact restoration to that invoker. |
| DIALOG-C4-02 | Both disclaimer and comparison contain Tab/Shift+Tab, including after comparison results appear. Escape closes and restores the exact invoker. Overlay close also restores it. Closed sheets are not tabbable; normal page tabbing resumes. Run repeated open/close cycles to detect stale handlers/opener state. |
| DIALOG-C4-03 | Keyboard-open comparison from `#btn-compare`, assert its accessible name/modal semantics and `#csearch` initial focus, search Houston, and select the actual result using keyboard. Comparison updates and focus returns to `#btn-compare` after rendering; removal still works. Search failure/empty results retain usable focus and dismissal without trapping the user permanently. |
| DIALOG-C4-04 | Exercise tour through its existing entry points, step forward, then Skip/Done/Escape as applicable. The first invoker is restored and highlights/overlay are cleared; subsequent steps never replace it. The rare removed-invoker fallback has its own explicit check and does not weaken normal exact-opener assertions. |
| C4-REPAIR-05 | Focused checks pass in Chromium/Firefox at desktop and mobile sizes; the existing full C4 browser matrix and relevant source/static checks pass without unexpected page errors. No default report chart dimensions, labels, caveats, filters or data values changed through these two repairs. The final 72-cell 95/5 requirement and independent participant/assistive-technology limitations remain in force. |

Browser keyboard checks establish actual DOM focus behavior, not a completed
screen-reader usability study. Preserve that distinction in the evidence.
