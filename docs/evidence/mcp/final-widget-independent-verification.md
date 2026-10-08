# Final independent MCP widget verification

**Reviewer:** agent verifier (`gpt-5.6-luna`, fresh verification stage)
**Reviewer type:** agent inspection; not a human study, screen-reader study, or actual ChatGPT host review
**Reviewed at:** 2026-10-07 America/Chicago
**Scope:** E1 and `VISUAL_DESIGN_CONTRACT.md`; `static/mcp-app.html`; browser capture/classifier/manifest/spec files; current raw and annotated MCP evidence; three public visual fixtures; plugin manifests, listing, assets, and portable archive.

## Evidence inspected

I opened contact sheets with the image viewer for every case in all three groups. Each row contained the raw full screenshot, initial annotated screenshot, and full annotated screenshot. The sheets covered all 36 cases: 2 browsers × 3 views × 3 host viewports × 2 themes. I inspected the rendered content, blue painted bounds, initial viewport crop, full-document continuation, mobile reflow, light/dark parity, and the Firefox one-pixel full-height differences. The raw and annotated files were present and viewable; this is an actual image inspection record rather than a file-existence check.

The stored measurement report contains 36 cases with zero page errors, zero manifest errors, zero blocked external requests, and zero unclassified inventory items. Every initial screenshot is exactly the widget frame height (host height minus 40px). Every full screenshot is within ±1px of the captured DOM document height. The observed full-document heights include district mobile 1558/1559px, comparison mobile 2897/2898px, and statewide mobile 1215/1216px; the desktop and tablet cases are also complete.

The current inventory has 2,124 visual records and 312 explicit exclusions across the 36 cases. Exclusions are only the view title and `.mcp-limits` expanded source disclosure, matching the manifest. There are no unclassified records. Visible context and semantic metadata are explicit `.mcp-context`, `.mcp-frame-item` (`dt`/`dd`), table, and metric metadata elements. No standalone narrative paragraph was reclassified as visual. The visible chips retain `Period`, `Status`, and, for district/statewide views, `Frame`, `Scope`, and `Total`; comparison retains `Compare: Matching definition / period / unit / denominator` and `Model: Noncausal`. `Scope: Excludes construction` and `Total: Not all funds` remain default visible wherever the non-comparison frame applies. The comparison bars are partitioned by measure, period, unit, and denominator. Missing, zero, observed, and modeled values remain distinct in the rendered tables and bars.

Current normalized source hashes match the measurement report for the fixture, widget, helper, design CSS, manifest, and collector. The widget hash is `f57a124e613ca75865e656503f75e4d94885bcd040039fdfe706c2e2ab1874a3`; fixture hash is `397df787300b7bf749cd86c6df7f528b455f5b00dd175a35bffdbc55bb65ade9`; manifest hash is `579e3efae078c713ccbafdf0b0da95f732e360cdf938cfc388fee1f1f0721eae`.

## Independent checks

| Criterion | Result | Evidence and limits |
|---|---|---|
| E-VISUAL-01 | **PASS** | `npx playwright test mcp-app.spec.js` independently passed 56/56 in Chromium 141.0.7390.37 and Firefox 142.0.1. Exact fixture value, period, unit, denominator, status, source, district ID, limits, and deep-link assertions passed. Automated visual ratio report is 1.0 full and 1.0 initial for all 36 cases; the image inspection found no classification defect. |
| E-BRIDGE-01 | **PASS for local bridge / UNVERIFIED for actual ChatGPT host** | The same 56 tests cover initialize/readiness, timeout/error, repeated updates, absent/malformed results, stale/unsolicited envelopes, sibling-frame spoof rejection, unsafe URLs, and negative/zero/missing/mixed-period edges. No external payload requests were observed. The actual ChatGPT host rendering gate remains unverified. |
| Measurement-model preservation | **PASS** | `visual-regions-mcp.json` and shared `measurement-core.mjs` were read in full. Tight text-range/painted-mark bounds, explicit exclusions, overlap handling, data marks, and inventory outputs are unchanged in the current evidence hashes. Historical ratio failures and the withdrawn invalid reclassification remain preserved in `visual-ratio.json`. |
| E-PACKAGE-01 | **PASS** | `npm run validate -- ..\\..\\plugin` passed official cached Agent Plugins/MCP schema checks, public endpoint/reference checks, generated mapping identity, asset references, and skill checks. Focused Python checks passed 18/18. Portable archive evidence reports schema/reference validation PASS and current assets match the two cited capture hashes. |

## Package and host limits

`plugin/assets/district-report.png` and `comparison.png` match the cited E1 Chromium captures byte-for-byte. The portable package is `docs/artifacts/texas-isd-finances-plugin.zip` with the recorded archive hash in `portable-archive.json`. Actual host installation, actual ChatGPT rendering, independent-account installation, and public directory listing remain explicitly `UNVERIFIED`; this record does not promote those gates.
