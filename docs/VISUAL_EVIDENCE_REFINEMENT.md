# Visual evidence scope refinement

Prepared 2026-10-07 by the Astra planning stage. This is an explicit revision to
the evidence scope in `VISUAL_IMPLEMENTATION_PLAN.md`, not a measurement result.
It authorizes only test harness/evidence changes under the existing ownership.
It does not authorize production page, data, deployment, or plugin changes.

## Evidence and decision

Targeted inspection found that `design/public-portal-prototype.html` is a static
Dallas teacher-turnover/retention concept. Its finder is not functional; its
statewide labels are contextual cards. It has no statewide, Houston comparison,
or unavailable application state. Running it under four state names would create
false coverage. Preserve this historical intermediate artifact unchanged and
observe its actual Dallas concept in twelve browser/viewport/theme cells.
Unsupported original prototype states remain explicitly **UNVERIFIED**.

The original `master` source is available at immutable commit
`73df1896ed0818020ec1c15c06f5ee823db7ec0f`. Its index references historical
`/static/design.css?v=6`, `/static/ask.js`, `/static/track.js`, and a Vercel insights
script. Therefore a baseline replay must account for those assets; serving the
old index with current CSS would not be an original-source baseline.

Legacy baseline records used wrapper geometry and lack independent initial-view
and visible-leaf evidence. Keep them as historical observations under their
original rubric and **OBSERVED_FAIL** validation status. Do not relabel their
numbers as `semantic-painted-marks-v2`, average them with new measurements, or
claim their percentages establish an improvement under the new rubric.

Use a retrospective capture of the historical source for a comparable v2
baseline. The capture date is the real date it is performed, distinct from the
source commit date. It is a reconstruction with present fixed public fixtures,
not proof of what a visitor saw or what was measured before implementation.

## Ordered bounded work

1. Preserve legacy baseline JSON and referenced images in an explicitly named
   legacy evidence artifact before replacing the canonical baseline phase. Do
   not overwrite or discard their original revision, rubric, or capture time.
   Pin the historical SHA above; do not resolve moving `master` on each run.
2. Add a test-only historical-document interceptor to the existing local capture
   harness. Read blobs through Git at the pinned SHA and fulfill the document
   and its owned visual/runtime assets from those bytes. Use the existing local
   server for public artifact/API handling and the same fixed endpoint fixtures
   as final. Do not change production routes, restore files into the working
   tree, create a second checkout, or connect historical code to live mutation
   services. Record hashes of every historical asset served. If a referenced
   owned asset is absent at the SHA, record the absence and the exact test stub,
   if any; never silently use the current asset. Telemetry/paid calls stay
   explicitly stubbed or blocked by the established harness policy. Identify
   such stubs in provenance and retain unexpected-request failures.
3. Capture all six historical public states in Chromium and Firefox at
   1440x900, 768x1024, and 390x844 in both themes: **72 baseline cells**. Reuse the
   v2 geometry/classification engine, fixture payloads, settings, screenshot
   generation, and independent initial/full calculations. A baseline-specific
   selector adapter may map historical elements to the same semantic roles;
   it may not change category definitions, count wrappers, or omit narrative.
   Select comparison through the historical UI. If an original state cannot be
   reproduced, record **UNVERIFIED** with the observed cause, not fabricated
   measurements or N/A. This leaves comparable-baseline completeness unverified
   and does not itself invalidate measured final ratios.
4. Add a prototype-only readiness check and selector adapter for its actual
   `main`, text ranges, and `.bars > i` marks. The production readiness check
   expects `#dash`/`#dname` and cannot honestly certify this static file. Capture
   exactly **12 Dallas prototype cells** under the same v2 category definitions.
   Record its source-file hash, current capture time, embedded fixture origin,
   visible year/status, and that controls are nonfunctional. Do not add invented
   interactivity, new states, or redesigned graphics to the historical prototype
   just to improve its score. Record statewide, compare, and unavailable as
   unsupported **UNVERIFIED** scope entries outside the measured-case list.
   State explicitly that small/charter were never part of this prototype scope.
5. Preserve and finish the complete **72 final cells**. State identity is
   statewide, Dallas, small/Tioga, charter/Pineywoods, Dallas/Houston comparison,
   and unavailable Dallas, crossed with the same twelve browser/viewport/theme
   combinations. Synthetic `missing` is a separate semantic/adversarial test
   suite, not a seventh public screenshot state or a substitute final cell.
6. Run the geometry/adversarial checks and capture validation. Review raw and
   annotated initial/full images and classifications for all measured cells.
   Record the actual reviewer identity/type and findings; set `reviewed=true`
   only after inspection. Automated geometry alone is not semantic review.
   Do not describe agent inspection as human participant testing or external
   human review. Report any unavailable required human review as UNVERIFIED.
7. Publish phase-specific results and limitations in the existing verification
   evidence. A phase must carry its own source revision or file hash, capture
   time, rubric version, selector-adapter hash, fixture hashes, source mode,
   asset overrides/stubs, browser versions, and dimensions. Top-level metadata
   must not overwrite or imply identical provenance for all three phases.

## Revised testable acceptance criteria

| ID | Acceptance and truthful status |
|---|---|
| B-EVID-BASE-01 | Legacy records and their referenced evidence remain available with the original rubric. The canonical v2 baseline has exactly 72 unique expected cells, all captured from the pinned historical index/assets with phase-specific provenance and matching final fixtures. Every cell has raw/annotated initial/full captures and complete v2 inventory/exclusions. Ratios below 95% are valid observed failures, not an evidence-integrity failure. Missing capture/state/asset provenance is UNVERIFIED; invalid geometry is FAIL. |
| B-EVID-PROTO-01 | Exactly twelve unique Dallas concept cells cover both browsers, three sizes, and two themes with raw/annotated initial/full captures, complete v2 inventories, file hash, embedded-fixture provenance, and nonfunctional-control qualification. Statewide/compare/unavailable each explicitly remain UNVERIFIED. No duplicate Dallas screenshot is labeled another state. Ratios are observations and may fail 95%; unclassified content and invalid geometry remain failures. |
| B-EVID-COMPARE-01 | Baseline/prototype/final use the same semantic-painted-marks-v2 definitions and tight bounds. Selector adapters are versioned and reviewed. Historical narrative stays prose, numeric facts retain only necessary semantics, unsupported claims do not become visual facts merely by residing in cards, and disclaimer/model text is not hidden to improve scores. Any reported before/after numerical difference uses matching baseline/final cells and fixtures; the partial prototype is never compared as a full application. |
| B-VIS-03 (unchanged threshold, explicit matrix) | All 72 final identities exist once and each independently passes both initial and full V/(V+P) >= .95 and P/(V+P) <= .05, with valid screenshots, tight painted/text bounds, classified leaf inventory, itemized exclusions, no contradictory overlap, no invisible/empty supposed visuals, and required semantic review. No final cell is waived by historical or prototype results. A missing final cell, unknown analytic content, invalid geometry, or missing required review prevents final PASS. |

Separate evidence integrity from the ratio outcome: a historical source can be
captured correctly and honestly produce **OBSERVED_FAIL** for the target. A
score-only phase PASS must never imply full prototype-state coverage. Store a
distinct coverage status/reason; the unsupported prototype scope remains
UNVERIFIED even when the twelve actual observations are valid.

## Exact supersessions and retained gates

- B1b's requirement to capture the unmodified page *before UI changes*, and
  measurement item 1's corresponding timing, are replaced for missing v2 evidence
  by the explicitly retrospective historical-source capture above. The original
  timing claim remains unavailable; no source date is used as a capture date.
- B3's four-state working-prototype and correct-all-prototype-ratio-failures
  requirements are superseded by B-EVID-PROTO-01 for this already-built static
  intermediate. This is a documented scope revision, not a claim that the
  original B3 deliverable was completed. Its participant protocol remains.
- Original B-VIS-01 is replaced by B-EVID-BASE-01, B-EVID-PROTO-01, and
  B-EVID-COMPARE-01. Report these separately so incomplete historical evidence
  cannot be hidden behind the final ratio gate. Final-only ratio validation may
  pass while a broader historical evidence claim remains UNVERIFIED.
- The seven-state screenshot sentence is clarified to six public matrix states
  plus the separate synthetic missing-data suite. B-VIS-02 adversarial and
  independent initial/full requirements remain. B-VIS-03's 95/5 threshold is
  unchanged and applies to every final public matrix cell.
- C-MODEL-01, C-DATA-01, C-FLOW-01, C-OFFLINE-01, C-A11Y-01,
  C-BOUNDARY-01, B-USER-01 and source-arithmetic/data certification gates remain
  unchanged. Required years, modeled/observed status, missing-data explanations,
  source qualifications and limitations remain visible. Participant and actual
  assistive-technology evidence cannot be replaced by screenshots or agent
  review. Local coding completion is not deployment or public-usability approval.

Rationale: this recovers comparable measurements from a real historical source,
preserves the actual intermediate artifact rather than inventing a past design
stage, and concentrates the release threshold on the complete implemented public
experience while keeping every evidence gap visible.
