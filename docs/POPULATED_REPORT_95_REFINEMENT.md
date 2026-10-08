# Populated public reports: focused 95/5 composition refinement

Prepared 2026-10-07 by Astra, planning only. Parent contracts are
[VISUAL_IMPLEMENTATION_PLAN.md](VISUAL_IMPLEMENTATION_PLAN.md),
[VISUAL_DESIGN_CONTRACT.md](VISUAL_DESIGN_CONTRACT.md), and
[VISUAL_EVIDENCE_REFINEMENT.md](VISUAL_EVIDENCE_REFINEMENT.md).
This revision authorizes the bounded presentation work below. It changes no
95/5 threshold, semantic classification definition, public-data contract,
finance framing requirement, or release gate. It does not report implementation
or verification success.

## Evidence and objective

The restored fixture contains 37 actual public GET responses captured at
2026-10-07T23:42:55.403985+00:00, including populated dollar, insight, and
turnaround responses. The resulting complete 72-cell final capture has 24
full-report ratio failures and four desktop-comparison initial-view failures.
The minimum full visual share is 0.9081949955 (Tioga mobile); the minimum
initial share is 0.9301015253. The older 96.36% minimum verdict was withdrawn
after an evidence postprocessing race; it is not an acceptance baseline.

Preserve [the failure record](evidence/visual/failed-final-37-route-2026-10-07.json)
and its four `failed37-*.png` references. Its SHA-256 is
`05bf0fa15ff2a3162a3041c2fbc55c914142ae40b36c534c5f881d568f344c2f`.
It records exact selectors, text, areas, source hashes, and fixture hashes.
The canonical failed measurement gzip hash at this planning checkpoint is
`9ab08f1b58af4dd408de936083431b83d699a2282adf5ddf025b8acc6de98d3b`;
the failed ratio JSON hash is
`981d436a55edc1f5dc24a9fa72f7bbe6835aa75c1b6962a0e0251f3c32d59342`.
Runtime coordination checkpoint: `1526236dc6153354257f5c41a54385c81ace25de`.
Source-byte hashes, rather than an unrelated later Git HEAD, identify a dirty
working-tree capture.

Targeted inspection of `static/index.html` and the visible-leaf inventory found:

| Surface | Observed cause | Bounded repair |
|---|---|---|
| `focusCat()` / `guideHTML()` | The default penny panel repeats instructions, a long category definition, and numeric comparisons as sentences. These account for the desktop comparison first-view failure. | Compose the actual category values and comparisons as compact labeled data; provide adjacent definition/instruction details and visible material category limits. |
| `renderTurnarounds()` | Tioga has nine genuine peer records rendered as repetitive deficit/enrollment recovery sentences. Each contributes about 7,826–8,452 square CSS pixels of prose. | Show every record as a labeled period/recovery comparison using the actual fields. |
| `renderInsights()` | Narrative recommendations follow numeric peer outliers; Tioga debt interpretation contributes about 11,624 square CSS pixels. | Lead with actual district/peer values, signed difference, and annual-dollar impact; keep interpretation in an adjacent disclosure. |
| `FLAG_META` / `renderFlags()` | A 25,859-square-pixel Tioga method paragraph describes denominator sensitivity and enrollment history. Dallas also displays the generic “In small districts…” sentence despite no district-specific size test. | Retain numerical flag thresholds and before/after evidence; show a short general denominator/review caveat, with conditional examples in method details. |

These are presentation findings. A generic conditional example appearing on
Dallas does not establish that Dallas is small or that declining enrollment
caused its spending change. No new size threshold or causal explanation may be
invented for this repair.

## Ownership and boundaries

One implementer owns the targeted renderers and associated local CSS in
`static/index.html`. Change `static/design.css` only if a shared existing token
or responsive rule is necessary; coordinate ownership first. Focused behavior
checks belong in `tests/browser/public-regression.spec.js` and existing unit
tests as appropriate. The evidence owner controls capture outputs and metadata.
Others are working in this checkout: preserve their edits and source revisions.

Do not change API responses, SQL, source artifacts, dictionaries, MCP protocol,
plugin packaging, deployment configuration, historical prototype, or unrelated
public sections. Do not restore empty optional fixtures, trim record counts,
hide substantive sections, change the audience lenses, or manufacture measures.
Use current typography and chart geometry; enlarging marks/whitespace or
shrinking prose merely to improve area ratios is outside this plan.

The existing `semantic-painted-marks-v2` classifier and category definitions
remain fixed. A small selector adapter addition is permitted only for new,
independently reviewed numeric components or painted data marks. It must not
grant visual credit to a narrative wrapper or its descendants. A sentence does
not become visual by using `div`, a `.metric-*` class, SVG text, a border, or a
different parent. Required missing/unavailable explanations remain prose.

## Ordered implementation

1. **Freeze the evidence input.** Confirm the failure-package hash, all 37
   fixture route mappings and response hashes, and the tested runtime bytes.
   Preserve the failure package and images. Record expected insight/turnaround
   counts and actual field values for Dallas, Tioga, charter, and comparison
   states. Keep deliberately unavailable/synthetic edge cases clearly separate.
   A route that should be populated must fail the test if silently stubbed empty.

2. **Repair the penny guide first.** Replace repeated default instructions with
   a concise accessible affordance such as “Select a spending category,” while
   retaining keyboard/touch/hover/pin and legend behavior. Render the selected
   category's actual cents, total dollars, dollars/student, structural-peer cents,
   statewide cents, previous cents/year, and dollar difference as compact labeled
   numeric comparisons. Use the endpoint fields and existing calculations; preserve
   zero, negative difference, absent comparison, and invalid-denominator handling.
   Do not parse formatted prose to recover numbers when numeric fields exist.

   Keep the all-funds scope, actual fiscal year, unit/denominator, peer/state
   identity and counts, and current category in the default view. Preserve the
   actual meaning of normalized category medians: the peer/state composition
   bars are rescaled median shares, not a particular peer's budget. Provide the
   longer structural-peer matching explanation in native adjacent `details`.
   Category membership text and complete TEA codes remain available in one
   activation. Any category-specific material restriction remains visible by
   default, including the inseparability of safety/technology and residual
   “everything else” accounting. Do not use automatic first-sentence truncation
   or blanket disclosure to decide what is material.

   Build this composition inside `guideHTML()` / `focusCat()`, so hover, pin,
   comparison, and rerender produce the same truthful layout. Do not depend on
   a one-time post-render transform that later interactions bypass. Inspect the
   desktop comparison initial view before proceeding.

3. **Make populated peer reports primarily numeric.** In `renderInsights()`,
   retain every returned item and show its metric, actual year, district value,
   peer median, actual unit, percentage difference/direction, and annual-dollar
   impact. A paired-value comparison with a shared scale is permitted where
   units match; compact numeric cards also suffice. Preserve share versus
   dollars/student semantics and do not conflate percent difference with
   percentage-point difference. Label the dollar impact as a peer comparison,
   not proven savings. Keep “Descriptive comparison; not a cause or finding of
   waste” visible. Preserve each original recommendation/finding in an adjacent
   accessible interpretation disclosure, with source and peer methodology.

   In `renderTurnarounds()`, show every returned district, actual reversal type,
   `struggled` year range, and `recovered_since` year in compact period/recovery
   cards or a small timeline. A timeline may paint only the supplied historical
   interval and discrete first-recovery marker. Do not extrapolate continuing
   surplus/growth beyond the supplied evidence or infer an unreported magnitude.
   Keep the differing meanings of deficit and enrollment records explicit,
   preserve peer identity/count/source, and state that historical peer examples
   do not establish causes or predict this district. No record is collapsed away
   to make the full default report shorter. If dates cannot be validated, retain
   their source text and an honest unavailable marker rather than drawing a
   false interval. A table alternative must preserve all underlying fields.

4. **Fix the anomaly interpretation mismatch.** Preserve every flagged fiscal
   year, observed before/after value, exact flag threshold, and current unavailable
   versus no-flags distinction. Keep a concise default caveat explaining that
   automatic flags are review prompts and per-student changes depend on both
   spending and enrollment. Preserve the all-funds/non-operating construction
   qualification beside spending-spike evidence. Move the longer one-time-grant,
   construction, boundary, and small-district examples into adjacent method
   details, explicitly marked possible explanations rather than district findings.
   Dallas must not be labeled small or assigned an enrollment cause by this
   generic copy. No arbitrary enrollment cutoff is needed or authorized.

5. **Check the default-context contract before scoring.** Review all newly
   composed surfaces at desktop/mobile and after interaction. Mandatory units,
   source years, denominators, observed/modeled status, source qualifications,
   missing versus zero, noncausal limits, and category restrictions remain visible.
   Preserve the existing default finance frames: operating versus all-funds
   distinctions, debt/construction outside operations, appropriate rank/basis and
   denominator, and distinct finance FY2025/outcome SY2024 vintages. The six-period
   hypothetical district teacher-cohort model and its non-individual/constant-rate
   qualifiers remain unchanged. Do not broaden `applyVisualLedger()` to conceal
   these or the populated records.

6. **Verify behavior, then freeze and capture.** Run the existing 32 C4 public
   checks plus focused tests of the changed composition, including real populated
   record counts, mobile default content, disclosures, category rerenders and
   Dallas conditional copy. Test the shipped renderers with disclosures both
   closed and keyboard-opened: default required context remains visible, and
   expanded content retains the complete original finding, category definition,
   conditional anomaly examples, source/method and instructions. Check a zero
   category, missing peer value, and invalid denominator without inventing a
   number. Retain all 36 widget-contract checks. A widget result
   may carry forward only when every runtime and test dependency hash matches;
   otherwise rerun it. Run static-JS parsing, focused unit/adversarial measurement
   checks, and repository-required validation. Record failures honestly.

   Freeze the application, fixtures, classifier/adapter, tests, and contract bytes
   for a complete final capture. Exactly six states (statewide, Dallas, Tioga,
   charter, Dallas/Houston comparison, unavailable Dallas), two browsers, three
   sizes (1440x900, 768x1024, 390x844), and two themes produce 72 unique cells.
   Measure initial and full default report independently. Preserve source/table
   access and measure primary expanded analytic states when applicable; a method
   disclosure must not become a container that hides substantive data records.

7. **Publish complete evidence and obtain fresh verification.** Write captures
   into an isolated staging location, finish compression and ratio validation,
   then replace the canonical artifact set together. No verifier should read a
   mixture of generations. Record raw and normalized source hashes, fixture and
   manifest hashes, capture time, browsers, dimensions, and final ratio-file
   hash. Verify referenced files exist and hashes agree before handing off.
   Independently inspect raw/annotated initial/full images and semantic inventory
   for all cells. Record actual reviewer identity/type; only inspected results
   receive `reviewed=true`. Fresh Luna verifies the criteria below without repair.
   Preserve historical phase provenance and unsupported prototype states.

## Testable acceptance criteria

| ID | PASS evidence required |
|---|---|
| POP-01 truthful inputs | All 37 recorded public GET routes and response hashes are retained; populated dollar/insight/turnaround fixtures and each returned record are represented. Empty/unavailable/synthetic responses have explicit provenance. No public capability or section is removed. |
| POP-02 meaningful composition | Penny, insight, and turnaround comparisons use actual fields, units and periods. Full data/definitions remain available; all peer records remain in default analytic content. Visual credit is limited to meaningful painted marks and tight necessary numeric semantics. No narrative relabeling, wrapper/padding inflation, font shrinking, or artificial plot area occurs. |
| POP-03 context and district meaning | Mandatory context is visible with disclosures closed and after hover/pin/rerender: construction/debt excluded from operating measures, all-funds scope where applicable, actual FY/SY, source/denominator, noncausal peer comparison, and teacher-cohort limits. Missing is not zero. Dallas has no asserted small-district status or unsupported causal explanation. Flag labels retain revenue drop >15%, spending rise >20% with the existing flat-enrollment condition, per-student rise >15%, and enrollment drop >10%; original observed values and backend predicates remain unchanged. |
| POP-04 exact unchanged 95/5 | All 72 unique final cells individually have initial AND full `V/(V+P) >= .95` and `P/(V+P) <= .05` under the unchanged v2 rubric. No averaging, waiver, fixture omission, historical score substitution, unclassified analytic leaf, invalid geometry, blank graphic, renderer error, or missing screenshot is accepted. Required independent semantic review is complete. |
| POP-05 interaction regression | The existing 32 C4 checks pass, plus focused populated-composition checks. All 36 widget-contract checks remain passing with exact dependency hashes or fresh rerun. Search, selection, comparison, lenses, section navigation, pin/hover/keyboard/touch, source/table disclosures, downloads and print retain their contracts; 320px reflow and 200% text resize remain covered. |
| POP-06 reproducible final evidence | Final source/contract/test/fixture/adapter hashes match the captured and tested bytes; all referenced raw/annotated initial/full assets are complete. Capture/measurement publication is coherent and preserved failure evidence remains immutable. A fresh independent verifier gives concrete PASS/FAIL per criterion, with no stale 96.36% claim. |

If any criterion fails, report that failure; do not weaken the rubric or hide a
qualifier. Two counted targeted implementation/check failures on the same
criterion follow the existing Sol escalation rule. Any required change to this
plan or the data/architecture/scope returns to Astra before implementation.

The existing source arithmetic, actual assistive-technology, participant,
historical evidence, actual host/install, publication, and release gates remain
separate. Agent screenshot review is not a parent/taxpayer usability study.
This document authorizes no merge, deployment, production SQL, outreach, paid
request, or public release. Code, documentation, and plugin evidence continue
through the existing GitHub review process with truthful status for every gate.
