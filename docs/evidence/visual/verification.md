# Visual implementation verification

Date: 2026-10-07. Rubric: `semantic-painted-marks-v2`. This record separates
measured geometry from semantic review, participant testing, and actual
assistive-technology testing.

| Acceptance ID | State | Evidence / limit |
|---|---|---|
| B-EVID-BASE-01 | OBSERVED_FAIL | The retrospective baseline contains all 72 browser, viewport, theme, and state cells from pinned Git revision `73df1896ed0818020ec1c15c06f5ee823db7ec0f`, with four image references per cell and the same 37-route public fixture as final. Full-page visual share ranges from 42.57% to 71.88%; first-view share ranges from 22.48% to 88.36%. Historical blank graphics, renderer warnings, and four sub-pixel overlap findings remain recorded as failures. Unsupported historical claims such as 6.6 million data points and 10 official products remain prose and receive no visual trust credit. The preserved wrapper-era legacy result remains a separate historical observation and is not relabeled under v2. |
| B-EVID-PROTO-01 | OBSERVED_FAIL | The immutable Dallas concept has exactly 12 real cells. Full-page share ranges from 75.27% to 81.03%; first-view share ranges from 60.11% to 81.03%. Statewide, comparison, and unavailable remain unsupported and UNVERIFIED; small and charter were outside prototype scope. |
| B-EVID-COMPARE-01 | PASS (geometry and provenance) | Baseline, prototype, and final use the same painted-mark definitions and tight text bounds. Phase-specific source, fixture, manifest, helper, and collector hashes are recorded as both captured bytes and normalized UTF-8/LF bytes. Narrative headings remain prose unless an explicitly reviewed concise measure label applies. |
| B-VIS-02 | PASS (automated scope) | Adversarial unit coverage rejects padding-only plots, blank SVG/canvas wrappers, hidden/null/missing content, prose-padded containers, missing annotations, first-view failures, and cross-view compensation. Fresh independent agent screenshot review is recorded under B-VIS-03; human studies remain unverified. |
| B-VIS-03 | PASS (agent semantic review) | The repaired 37-route final matrix has exactly 72 cells across six states, two browsers, three viewports, and two themes. Every cell independently passes geometry: full-page visual share is 95.83% to 100.00%, and initial share is 98.29% to 100.00%. Fresh independent Luna review inspected all 72 cells and 288 images and passed POP-01–06. There are no page, renderer, manifest, unclassified-content, or blocked-request errors. All comparison cells select Houston and all unavailable cells retain 11 artifact-backed graphics. All 72 cells now carry explicit agent review metadata. The dated failure package remains preserved and immutable. |
| C-A11Y-01 | PARTIAL | Automated reflow, keyboard, focus, reduced-motion, and print checks passed in the focused browser suites. Required human and actual assistive-technology studies remain UNVERIFIED. |
| B-USER-01 | UNVERIFIED | No participant study is claimed by this capture or by agent semantic review. |

## Canonical evidence

- `measurements.json.gz` is the lossless canonical geometry and inventory record.
  Its uncompressed and compressed SHA-256 values are in
  `measurements-provenance.json`.
- `visual-ratio.json` is the compact validator result. Its status and final
  phase are `PASS`: all 72 reviewed cells pass both initial and full-report
  geometry.
- `source-hashes.json` records raw and normalized UTF-8/LF SHA-256 values for
  application sources, the pinned historical blobs, prototype, public fixture,
  selector manifests, shared classifier, and collector. Normalized hashes aid
  verification across Git line-ending conversion; they do not replace the raw
  captured-byte identity.
- `legacy-baseline-wrapper.json.gz` preserves the former wrapper-based result
  under its original rubric. It is not comparable to the v2 ratios.
- `semantic-review-queue.md` lists the representative images and the required
  all-72 review procedure. Every final case has raw and annotated lossless PNGs
  for both the untouched first viewport and fully rendered report.
- `failed-final-37-route-2026-10-07.json` preserves the pre-refinement failure,
  including all failing case ratios and the largest exact prose selectors. Its
  four `failed37-*.png` references preserve raw and annotated Tioga full-report
  and Dallas/Houston comparison first-view examples.
- `measurements-before-review.json.gz`, `visual-ratio-before-review.json`, and
  `final-freeze.json` preserve the exact reviewed generation before metadata
  publication. `review-publication-receipt.json` links pre/post hashes and proves
  geometry, inventory, images, source, fixture, and classifier bytes unchanged.

The validator exits zero with final status `PASS`. The recorded review is an
independent agent semantic inspection and must not be described as human-
participant or assistive-technology evidence; those separate gates remain
unverified.
