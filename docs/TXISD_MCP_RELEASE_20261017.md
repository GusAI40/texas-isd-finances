# Texas ISD Finance Intelligence — bounded MCP release, 2026-10-17

Gus explicitly authorized fixing and launching Texas ISD at 15:15:58 UTC on
October 17. The later direction to move on limits this closeout to the work
already started. Production was verified on `fd97a58a46af404594162daed1b0a91d8433dc21`,
Vercel project `prj_Q86h3ZufDMLk7bsyYOj7FP3S9Wqg`, team
`team_hLW8yrUTYNGt9CiRY4IMMSet`. Release uses a protected-master PR and the
existing Vercel Git integration. PR and deployment receipts are recorded in
GitHub after execution, not predicted here.

## Changes and source boundaries

- Includes PR 88's inspected two-file setup guide, source `0509d6a7bc9d65037aadd9d92b0f1d60af6c09e7`.
  No old full-repair branch is merged. The supplied `ab855561e4582a00052a8f329e2b42230ac04ccc`
  could not be fetched from GitHub and is not used.
- Discovery advertises Texas ISD Finance Intelligence and an SVG byte-matched
  to the existing portal favicon (white tile, three blue squares, one gray).
  This does not claim to change the installed ChatGPT listing.
- Argyle's BRB FY2025 balance remains principal $670,626,909, interest
  $554,498,697, total $1,225,125,606. The source review carries the separate
  district HTML, FY2025 HB1378 report, and February 26, 2026 continuing disclosure.
  The latter's principal as-of date is February 15, 2026. Its Table 11 sum is
  $670,626,909.40 + $603,177,645.30 = $1,273,804,554.70 through FY2057.
  Comparability remains unresolved; there is no balance replacement.
- `clears_in` is retained for compatibility and explained as the last positive
  BRB scheduled balance year, not a verified final payment or maturity date.
- Annual debt service now uses existing independently recomputed PEIMS source
  numerators. Argyle changes $31,499,328 to $31,498,615; statewide changes
  $13,859,452,749 to $13,859,481,756, exactly matching the source fixture.
  1,105 district annual totals change; no per-student rate, rank, flag, ballot
  amount, outcome, or BRB balance changes. All 1,202 district source numerators
  are available; future missing verified numerators are withheld and counted.
- Missing finance, accountability and outcome-year labels are added. The stale
  bond tool description no longer hardcodes an obsolete end year.
- `purpose_display` corrects Atheltics, preserves the publisher's original
  `purpose` and stored category, and discloses the remaining classification
  limitation. Ballot analytics are not reclassified in this bounded release.
- Unexpected MCP data-read failures return a generic unavailable-data response
  without exception names or exception text.

## Verification and review

- Python 3.12: 1,193 passed, 31 skipped. Skips include unavailable uncommitted
  source datasets and credential-dependent integrations; no paid queries made.
- Ruff, locked dependency check, whitespace check, and all 14 static JavaScript
  page parsers pass.
- MCP contract regression covers every one of 11 tools, 14 valid and 4 invalid
  calls, exact dollars, source separation, dates, error redaction and favicon.
- All 11 tool payloads were snapshotted against the base. The structured-field
  diff is recorded in `docs/evidence/mcp/release-20261017-tool-diff.json`.
  The entire forensic artifact was compared structurally: only district
  `outside_operating.annual_total` and three statewide total/basis/coverage
  fields changed. Debt artifact numeric data is unchanged.
- Chromium: 71 scoped browser checks pass, including setup at mobile/desktop,
  chat, keyboard and automated WCAG checks. Two additional existing layout
  checks fail identically on production-base HTML and candidate HTML in this
  Linux environment: desktop chart top 366.71875 exceeds the old 350 threshold;
  at 160px selected-report reflow scroll width is 164px for both. Neither is
  introduced by this patch. Remaining broad accessibility variants were not
  rerun. Firefox installation was blocked by the workspace download policy.
- A second source review checked the complete changed code, artifact deltas,
  original publisher dates and amounts, preserved access-control configuration,
  deploy inclusion, and tested PR 88 scope. No additional in-scope defect found.
- Direct `verify_live.py --require-network --expect-revision ...` fails closed
  because this workspace proxy rejects connections to txisd.dev. The authorized
  Vercel read connector and installed MCP connection are available; final live
  receipts use those routes and clearly distinguish them from that blocked run.

## Separate account and security gates

The ChatGPT Origin expansion remains awaiting its separate security approval.
No origin, credential, access control, workflow, cron, paid commitment or provider
configuration is changed. GitHub Actions is left paused; no workflow is enabled
or dispatched. The installed listing rename/icon still requires the signed-in
account owner to save that edit; cloud ChatGPT was signed out. Neither gate is
a prerequisite to this code/data-quality release.

Automatic approval review rejected uploading the modified full historical
engineering log because it contains sensitive operational and security history.
That file is unchanged in this release; this concise public note and the
CLAUDE.md pointer preserve the bounded release memory without republishing it.
