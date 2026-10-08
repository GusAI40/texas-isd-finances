# Final visual semantic review queue

Fresh independent Luna agent review is complete for all 72 final cells and all
288 raw/annotated initial/full PNG references. The reviewer confirmed that blue
regions are actual data marks or concise necessary measure labels and red regions
are narrative prose. The canonical final cells now record `reviewed: true`, the
agent identity, review time, and verification-document hashes. This agent review
does not constitute the separate human-participant or assistive-technology study;
both remain unverified.

The review included these six representative first-view images, their matching
`-annotated.png` files, and all remaining initial/full counterparts:

- `final-chromium-statewide-1440x900-light-initial.png`
- `final-chromium-dallas-390x844-light-initial.png`
- `final-firefox-small-768x1024-dark-initial.png`
- `final-chromium-charter-390x844-dark-initial.png`
- `final-firefox-compare-1440x900-light-initial.png`
- `final-chromium-unavailable-768x1024-light-initial.png`

All 72 final cells listed in `measurements.json.gz` were reviewed. Each cell
contains four resolvable lossless PNG references: raw and annotated first
viewport, and raw and annotated full page. Comparison shows Houston selected
through the public UI. Unavailable state shows the live actual-finance unavailable
status while preserving artifact-backed charts. Empty plots, padded wrappers,
decorative diagrams, hidden content, and missing/null statuses receive no visual
credit.

The retrospective baseline and prototype remain observations. The baseline is 72 cells served from pinned Git revision `73df1896ed0818020ec1c15c06f5ee823db7ec0f`. The prototype is exactly 12 Dallas concept cells; statewide, comparison, and unavailable are recorded as unsupported and unverified, while small and charter are outside that prototype's scope.
