# Visual public portal and ChatGPT plugin: execution plan

**Prepared:** 2026-10-07. **Stage:** audit, planning, and documentation only.
**Baseline revision:** `73df1896ed0818020ec1c15c06f5ee823db7ec0f`.

## Goal and authorization boundary

Parents, taxpayers, and the public can find their district, understand its money
and outcomes through clear visuals, compare like-for-like measures, and inspect
the source behind each number. The same verified public information becomes
available through a tested ChatGPT plugin, with visual answers where supported.
The public website remains directly accessible regardless of ChatGPT eligibility.

This document plans future work. The current authorized deliverable is a
documentation PR containing the audit, this plan, `INDEX.md`, `DICTIONARY.md`, and
`THIRD_PARTY_SERVICES.md`. Application changes, production SQL, deployment, merge,
plugin submission, and publication are separate execution/release steps. No step
below is evidence that those changes have already happened.

Reuse FastAPI, the handwritten HTML/CSS/Canvas/SVG frontend, the existing database,
committed runtime artifacts, and deterministic MCP handlers. No framework rewrite,
new database, new LLM provider, or paid service is required by this plan. Keep
outreach and recipient operations outside the public redesign and plugin scope.

## Evidence controlling the work

The dated [audit](AUDIT_2026-10-07.md) is the evidence register; its final results
supersede provisional test observations below. Repository orientation and service
boundaries belong in [INDEX](../INDEX.md), [DICTIONARY](../DICTIONARY.md), and
[THIRD_PARTY_SERVICES](../THIRD_PARTY_SERVICES.md). These companion documents are
being prepared with this plan. The existing generated
[data dictionary](DATA_DICTIONARY.md) and `data/data_dictionary.json` must be rebuilt
through `scripts/build_data_dictionary.py`, never edited by hand.

| Observed evidence | Planning consequence |
|---|---|
| Live revision matches baseline; health and 41/41 live checks pass. | Useful baseline, not proof that every field, view, or browser interaction is correct. |
| Production `v_finance_summary` has 12 columns; repository SQL defines 30. | Catalog-level schema reconciliation must precede finance feature certification. Startup tracking markers do not prove finance-schema parity. |
| Integer division precedes numeric casting. Dallas FY2025 spending/student is published as 23,746.00 instead of 23,746.63; 1,195/1,202 latest rows differ from decimal calculation. | Correct arithmetic and independently test production view output, API output, and displayed values. |
| The same kindergarten-to-end-of-fifth-grade teacher-retention story displays 3/10 and 4/10, using different exponents. | Establish one documented cohort model; share its calculation and label it modeled. |
| 15 source checks pass publisher/host/content checks; most raw inputs are absent locally. | Availability is verified; missing raw-dependent re-derivations remain UNVERIFIED. |
| The completed network freshness check reports seven upstream-newer signals: `tea_snapshot`, `tea_staar_district`, `bond_elections`, `brb_debt_outstanding`, `census_tiger` (2026 versus served 2025), `usac_erate`, and `usac_entities`. BLS is unverifiable; F-33/NPEFS FY2025 and accountability 2026 were not published at check time. | These are refresh-investigation signals, not proof that seven compatible datasets contain new rows. Confirm the exact product and content before ingestion or vintage changes. |
| Registry has 1,310 districts, FY2025 finance has 1,202, and boundaries have 1,016. | Display dataset-specific coverage; never substitute the registry count for every measure. |
| Windows path handling can label missing raw data as DRIFT; dictionary regeneration depends on encoding and checkout newlines. With inherited UTF-8, 1 test still fails, 1,168 pass, and 31 skip; the residual dictionary mismatch is byte-size metadata from CRLF, not stale financial field content. | Repair verification portability and canonical UTF-8/newline accounting. Preserve genuine failure reporting. |
| Public roles currently have bounded projection SELECT access and no base-table writes; advisories remain. | Reconcile the already-applied grants repair with replayable SQL, preserving intended public projections and private data isolation. Do not blindly switch view security modes. |
| All 14 page scripts parse and 40 configured contrast pairs pass, but the divider threshold is only 1.4. | Neither check certifies browser behavior or full accessibility. |
| MCP exposes 11 bounded artifact tools under stateless protocol 2026-07-28; all 11 live fixture calls returned HTTP 200 without tool errors and with limits. A legacy initialize request fails. | Fixture calls pass; actual ChatGPT compatibility remains unverified until a real-host matrix is run. Preserve the existing tool contracts. |
| The Oct 7 intelligence cron succeeded with 257 rows; outreach remained skipped/unarmed. The latest observed GitHub product Monitor run failed and no recent answer-quality run was evidenced. | Distinguish working dynamic-news cron from GitHub monitoring/answer-quality gaps; preserve the outreach hold. |
| Historical simulated answerability is 82.2%; earlier UX work is simulated. | Do not call either a current accuracy score or a study of real parents. |

## Measurable 95% visual / 5% standalone prose rule

**Status: proposed acceptance contract; baseline has not yet been measured.**

For the primary analytic content of the landing page, selected-district report,
comparison, and plugin answer, measure occupied component area in CSS pixels:

`visual_share = V / (V + P)`; require `visual_share >= 0.95` and
`prose_share = P / (V + P) <= 0.05`.

- **V:** tightly bounded charts, maps, meaningful pictograms, data tables, and
  concise numeric data cards. A visual component must communicate a value,
  comparison, distribution, location, or change. A colored paragraph is prose.
- **P:** standalone explanatory prose blocks in the primary analytic content.
  Paragraphs inside cards remain P; card borders do not change classification.
- Chart titles, axis labels, legends, values, units, reporting years, population
  or cohort labels, source chips, and concise status/caveat labels count as
  component semantics within V. Long narrative explanations do not. Data cards
  contain a number, its meaning, its vintage, and any material caveat.
- Exclude global navigation, input controls, footer/legal notices, expanded source
  panels, and alternate screen-reader tables from the ratio; report their areas
  separately. Keep critical qualifications visible even if they make the ratio
  fail. Do not move qualifications into excluded regions to improve the score.
- Use the union of tight rendered content bounds, with no overlapping area counted
  twice. Exclude blank space, decorative padding, backgrounds, and oversized empty
  plot regions. Fix plot sizing rules before measurement. Publish classifications
  with screenshots so reviewers can detect inflated visual area.
- Score each initial analytic viewport and the full primary analytic report
  separately. Both must pass; a large chart at the bottom cannot compensate for
  a prose-heavy first screen. An empty/search-only state is N/A with a reason,
  never an automatic pass.

Capture annotated screenshots at **1440×900, 768×1024, and 390×844**, in both
themes, using identical seeded datasets and browser zoom 100%. Record content
bounds, V, P, exclusions, ratio, route/state, revision, and screenshot path in
`docs/evidence/visual-ratio.json`. Measure at least the statewide landing, Dallas
FY2025, a small district, a charter with a not-applicable national measure, a
two-district comparison, and an unavailable-data state. Plugin frames use those
widths where supported and record actual host frame dimensions otherwise.

This is a presentation target, not a claim of 95% coverage, accuracy, or user
success. Accessibility and comprehension remain independent release gates.

## Dependencies and work packages

Each package contains two or three bounded tasks. Tasks name owned path areas;
executors must coordinate any overlap, preserve unrelated changes, and capture
verification evidence. Newly named scripts/tests below are planned deliverables,
not commands that already exist. No package needs GSD scaffolding.

| Package | Depends on | Deliverable and exit gate |
|---|---|---|
| A. Data trust and reproducibility | Approved execution scope | Correct arithmetic, reconciled schema, source/freshness ledger, deterministic checks. |
| B. Design contract and prototype | Audit baseline; final numerical fixtures depend on A | Annotated 95/5 prototype and real-audience test protocol. |
| C. Accessible website | A + B | Working visual public experience with route/feature regression evidence. |
| D. MCP compatibility and parity | A; read-only host probe can start earlier | Actual host matrix and compatible, bounded tools with verified provenance. |
| E. Visual plugin package | B + D; reuse C visual components | Installable plugin package and optional MCP Apps visual answer. |
| F. Host validation and release | C + D + E | Evidence matrix, host tests, publication package, and authorized rollout. |

### A. Correct the data contract before certifying new outputs

1. **A1 — Reconcile arithmetic, schema, and grants.** Own
   `sql/create_tables.sql`, a focused replayable migration in
   `sql/reconcile_finance_summary.sql`, `tests/test_finance_contract.py`, and
   `scripts/verify_finance_contract.py`. Capture the current catalog, view
   definitions, dependencies, and effective privileges; reconcile the existing
   grants repair/PR #78 before writing migration SQL. Define the intended 30-column
   contract from actual consumers and source definitions, cast numerators before
   division, and handle zero/null enrollment explicitly. Preserve six-digit IDs,
   public projection reads, and the restricted NLP role. Do not infer that
   operating spending must equal total minus debt minus capital. Test a disposable
   database first; require target verification and release authority before any
   production migration. Include a tested recovery path for changed views and
   dependent materialized views; do not assume dropping/recreating them is safe.
2. **A2 — Make verification reproducible on Windows and CI.** Own
   `scripts/verify_artifacts.py`, `scripts/build_data_dictionary.py`, their focused
   tests, and any narrowly necessary CI encoding configuration. Distinguish missing
   raw paths in either separator style from actual artifact drift; specify UTF-8
   reads/writes and subprocess encoding where needed. Define dictionary byte-size
   metadata from canonical repository blob bytes or explicit UTF-8/LF content,
   not platform checkout bytes, and document which definition is used. Retest
   with inherited `PYTHONUTF8=1`, default Windows settings, and Linux, including
   CRLF/LF checkouts; parent-only `-X utf8` does not fix subprocesses. Rebuild
   generated dictionaries through the builder only.
3. **A3 — Establish source and refresh proof.** Own `src/sources.py`,
   `scripts/freshness_vintages.json`, source/freshness verification scripts and
   tests, and `docs/evidence/source-refresh.json`. Inventory source vintage,
   retrieval date, publication date, coverage, raw-input hash, and rebuild status.
   Resolve each of the seven measured freshness signals above against the exact
   compatible publisher product: TEA page-year patterns can match statewide PDFs,
   and BRB/USAC metadata timestamps can churn without relevant row changes. Compare
   product identity, schema, reporting period, raw hashes, and relevant row content;
   retain publisher links and evidence of the comparison. Keep BLS unverifiable
   until evidence resolves it, and retain the served vintage for not-yet-published
   F-33/NPEFS FY2025 and accountability 2026.
   Retrieve/rebuild available public sources in an isolated workspace, in existing
   dependency order, and compare results before proposing artifact replacement.
   Advance a served data vintage only after a compatible release is ingested,
   rebuilt, validated, and actually served; a successful check updates the check
   timestamp only. Record demonstrated unchanged content or a false-positive
   product match without pretending a refresh happened.
   Investigate failed monitoring and absent answer-quality runs without enabling
   unrelated operations. Missing/unavailable inputs remain explicit UNVERIFIED
   records. Never invent updated datasets because a URL returns 200.

**Acceptance A:** Independent numeric fixtures produce Dallas 23,746.63 spending
and 13,529.52 operating revenue per student after final rounding; all eligible
FY2025 rows match numeric division within $0.005 before two-decimal presentation.
Three zero/null-enrollment rows produce documented unavailable states. The
declared columns, types, definitions, dependencies, and effective privileges match
the tested database; rerunning the migration is safe. All 15 source-register
entries carry verification/freshness dispositions. Raw-dependent skips are
counted as UNVERIFIED, with public claims downgraded when required. Identical
logical inputs generate identical UTF-8/LF dictionary bytes and byte-size
metadata on Windows and Linux, independent of checkout newline conversion.
Each of the seven upstream-newer signals has a documented disposition: validated
compatible refresh, demonstrated unchanged relevant content, evidenced different
product/false positive, or unresolved. A freshness-release claim requires the
first three dispositions with evidence; unresolved signals remain visible and
block declaring the affected layer current. Refreshed artifacts pass independent
source/rebuild checks and exact served-vintage verification before closure.

**Verification:** Run focused pytest tests, `python scripts/verify_sources.py`,
`python scripts/verify_artifacts.py`, `python scripts/check_freshness.py`, and the
new finance-contract verifier against the disposable database. Preserve reports
and explicit skipped-check counts. Use read-only catalog/math queries to verify
production separately after an authorized migration; repository success alone
does not satisfy production parity.

### B. Define and test the visual design before broad UI work

1. **B1 — Build the contract and prototype.** Own
   `docs/VISUAL_DESIGN_CONTRACT.md`, `design/public-portal-prototype.html`, and
   `scripts/measure_visual_ratio.py`. Specify visual hierarchy, responsive sizing,
   both themes, keyboard/focus states, and the exact ratio rubric above. Lead with
   district selection and financial/outcome visuals; use progressive disclosure
   for repeated introduction and trust prose. Preserve a visible source affordance
   and concise caveat on every affected widget. Annotate the existing screenshots
   first to establish an honest baseline, then measure the prototype.
2. **B2 — Validate comprehension with the intended audience.** Own
   `docs/PUBLIC_USABILITY_PROTOCOL.md` and anonymized
   `docs/evidence/public-usability.json`. Use actual consenting adult parents,
   taxpayers, and public readers; target at least 10 participants, including
   mobile users and people with limited school-finance familiarity. If recruitment
   is unavailable, mark this gate UNVERIFIED. Test five tasks: find the correct
   district; read a spending/student trend; compare like-for-like districts;
   distinguish a tax rate from an illustrated tax bill; locate the source/year
   and identify an observed versus modeled result. Collect task success, time,
   assistance, and misinterpretations without names, contacts, or recordings in
   public artifacts.

**Acceptance B:** All applicable prototype views meet the 95/5 rule in six
viewport/theme combinations and expose units, vintage, cohort/denominator, and
material limits. Proposed usability target: at least 8/10 participants complete
each task unaided, median time at most 60 seconds for the first four tasks and
90 seconds for source/model inspection; no observed severe inversion of the
conclusion (for example treating modeled retention as measured student outcomes)
remains unresolved. These are proposed release targets, not measured findings or
population-level statistical claims. Record results, revise, and retest failed
tasks with fresh participants where feasible.

**Verification:** `python scripts/measure_visual_ratio.py` validates saved
annotations and produces the ratio report. Automated scores require human review
of classifications. Actual participant results supply comprehension evidence;
Monte Carlo outputs cannot substitute for them.

### C. Implement the accessible public website

1. **C1 — Build reusable visual reporting components.** Own `static/index.html`,
   `static/visual-components.js`, and focused browser regression tests in
   `tests/browser/public-portal.spec.js`. Follow B's contract within the current
   frontend. Standardize units, dates, source links, empty/not-applicable states,
   responsive charts, and one-click source/math panels. Represent missing data
   separately from zero. Encode observed versus modeled data with labels plus
   distinct line/mark treatments. Resolve teacher-retention assumptions from the
   described cohort (start/end points and number of transitions), use one tested
   function for both cards, and label constant annual turnover as an assumption;
   never choose the exponent just to make both displays agree.
2. **C2 — Preserve all public workflows and accessible equivalents.** Own the
   remaining affected public `static/` pages/styles and
   `tests/browser/public-regression.spec.js`. Preserve existing routes, exports,
   both maps, filters, comparison, district navigation/deep links, and source
   access; simplify presentation without deleting capabilities. Provide accessible
   data tables for Canvas/SVG charts, keyboard operation, focus indication,
   non-color cues, zoom/reflow, and descriptive unavailable-data states. Keep
   offline artifact reports usable when the DB/LLM are absent. Do not expose
   operational contacts or recipient telemetry.

**Acceptance C:** All B ratio and comprehension criteria hold for the implemented
site. Chart/table/API fixtures agree in units, values, year, denominator, and
missing status. No unexplained difference remains between the two retention
cards. Public workflows pass in Chromium and one additional browser, at the
three viewports and both themes. There are no uncaught browser errors, clipped
essential content, or keyboard traps. Check applicable WCAG 2.2 AA criteria,
including normal text contrast 4.5:1, large text 3:1, and required non-text UI/
graphic contrast 3:1; decorative dividers are classified separately. Automated
checks plus keyboard and screen-reader task checks are required; do not infer
whole-site compliance from a configured color-pair script.

**Verification:** Existing `python scripts/check_static_js.py`, `python
scripts/contrast_check.py`, focused pytest, new browser tests, saved annotated
screenshots, and documented keyboard/screen-reader runs. Pin any browser-test
dependency in a development-only manifest; do not enlarge the Vercel runtime
bundle or introduce a frontend production build solely for test tooling.

### D. Prove MCP compatibility and data parity

1. **D1 — Run the real host probe, then select the minimum adapter.** Own
   `docs/MCP_COMPATIBILITY.md`, `src/mcp_protocol.py`, and protocol tests in
   `tests/test_mcp.py`. First test the existing server with current MCP Inspector
   and the actual ChatGPT connection flow; record date, client version, negotiated
   protocol, request/response/error, and completion status. The observed legacy
   `initialize` rejection is a risk, not proof ChatGPT cannot connect. Only if the
   matrix demonstrates need, implement a small compatible Streamable HTTP adapter
   while retaining deterministic handlers and current clients. Recheck current
   official host requirements at execution time. Correct the stale MRTR docstring
   to reflect tested behavior; do not remove existing functionality to match prose.
2. **D2 — Lock tool provenance and limits.** Own `src/mcp_tools.py`,
   `tests/test_mcp_parity.py`, and `docs/MCP.md`. Retain the 11 existing tools and
   district resolution/disambiguation. Test schemas, bounds, structured results,
   errors, unknown/ambiguous IDs, missing data, vintages, sources, limits, and
   comparison size. Define a shared rendering payload with metric ID, value,
   unit, period, denominator/cohort, status, source, and limitations; map existing
   results without silently breaking their schema. Keep deterministic MCP
   artifact reads independent of `/query`, DB owner access, and LLM credentials.

**Acceptance D:** All 11 tools run successfully where applicable in Inspector
and real ChatGPT; unsupported/absent cases return meaningful structured results.
The connection/initialization/list/call sequence passes with documented supported
clients and protocol versions. Every sampled figure agrees with its exact source
artifact and corresponding website measure; coverage/vintage differences are
explicit rather than forced into false equality. Calls cannot access private
operations, execute SQL, send messages, mutate state, or start paid LLM calls.
Existing origin checks, bounded inputs, and protocol error protections survive.

**Verification:** `python -m pytest tests/test_mcp.py tests/test_mcp_parity.py -q`
plus recorded Inspector and real-host transcripts with secrets removed. A local
JSON-RPC test is necessary but cannot satisfy the real-host gate.

### E. Package the ChatGPT experience

1. **E1 — Reuse visual components inside an optional MCP Apps surface.** Own
   `static/mcp-app.html`, the shared `static/visual-components.js` contract, and
   focused resource/UI wiring in `src/mcp_protocol.py` and `src/api.py`.
   Reuse the website's rendering and D's structured payload, with responsive
   district summary/comparison views, keyboard access, source/math access, and a
   deep link back to the selected district. Add only resource/capability metadata
   required by verified current host contracts. Test content security policy,
   iframe permissions, allowed network origins, and fallback behavior. Schedule
   shared-file edits after C/D owners complete or agree exclusive ownership.
2. **E2 — Create the plugin package and public listing materials.** Own
   `plugin/`, `docs/CHATGPT_PLUGIN.md`, and `tests/test_plugin_package.py`. Follow
   the current official plugin manifest/packaging schema at execution time; use
   the stable HTTPS MCP endpoint, concise instructions to resolve district IDs
   and disclose limits, and optional visual capability from E1. Provide truthful
   descriptions, sample prompts, screenshots, privacy/support links, and a clear
   description of public data and any host limitations. Keep credentials and
   private operator details out of package, examples, screenshots, and logs.

**Acceptance E:** The package passes the current official validator and installs
in the available test channel. A user can ask the five public tasks from B and
receive grounded results; supported hosts render an accessible visual answer,
and unsupported visual hosts receive a useful concise text/table fallback with
sources and website links. No API key or portal account is required for the
public artifact tools. Account/region/plan eligibility and public-directory
availability remain host-controlled and must be described accurately.

**Verification:** `python -m pytest tests/test_plugin_package.py -q`, current
official package validation, UI resource tests, and actual ChatGPT sessions.
Record the actual validator command/version in the release evidence; do not
invent a permanent CLI command before the official packaging contract is checked.

### F. Validate release and publish only with concrete evidence

1. **F1 — Assemble the release matrix.** Own `docs/RELEASE_EVIDENCE.md`,
   `docs/CHATGPT_PLUGIN.md`, and narrowly affected monitoring workflows. Record
   each acceptance ID as PASS, FAIL, or UNVERIFIED with revision, date, command,
   environment, and evidence link. Run the repository minimum checks, focused
   tests, browser/ratio/accessibility checks, source/rebuild checks, finance
   catalog/math checks, tool/host tests, and actual participant sessions. Diagnose
   the product Monitor and answer-quality workflow statuses independently of
   dependency-update workflows. All critical gates must pass; missing required
   evidence blocks a claim of readiness.
2. **F2 — Prepare controlled rollout and publication.** Own `DEPLOYMENT.md` and
   `docs/RELEASE_EVIDENCE.md`. Prepare a tested rollback/recovery procedure, target
   identities, schema/artifact compatibility check, and smoke checklist before
   release authorization. Verify CLI versions if used, Git remote authentication,
   environment formatting, and persistent secrets/configuration without exposing
   values. Verify actual account limits/cost controls for the existing paid
   `/query` path before increasing traffic; artifact tools must not invoke it.
   After authorized release, require exact-revision live verification, critical
   route and real-host smoke tests, and a proposed 24-hour observation window
   with checks at deployment, one hour, and 24 hours. Roll back the application
   release or use the tested database recovery path for a failed critical check;
   never assume code rollback reverses SQL. Submit the reviewed plugin package
   through the documented distribution process when authorized, then verify the
   actual listing and an independent eligible account install. Report pending
   review, restrictions, and availability as observed, not promised.

**Acceptance F:** No critical FAIL or UNVERIFIED remains for the advertised
capabilities. Authorized production matches the released revision and declared
schema, all critical smoke checks pass throughout the observation window, and
the recovery procedure has been rehearsed outside production. Public plugin
publication is complete only when the actual directory listing and independent
install succeed; a working development connection or submitted application is
not publication. If publication is unavailable, report that exact gate as pending
while keeping website access and tested integration status distinct.

**Verification:** `ruff check .`, `python -m pytest -q`, `uv lock --check`,
`python scripts/check_static_js.py`, and `python scripts/verify_live.py
--require-network --expect-revision <released-40-character-sha> --with-query`,
plus A–E evidence and read-only database checks. Use the established UTF-8
environment configuration, report all skips, and record actual test totals rather
than hardcoding the historical audit count. Schedule observation only during an
authorized release; this planning stage creates no monitor or automation.

## Plugin decision and current official references

MCP is the public-data tool interface; the plugin is its installable/discoverable
package; MCP Apps is an optional visual surface. Reuse them together instead of
treating MCP and a plugin as competing replacements. The existing MCP handlers
are a strong starting point, while host compatibility and public distribution
remain distinct unverified gates.

Official sources checked during the 2026-10-07 audit; recheck before execution:

- [Plugin concepts](https://developers.openai.com/plugins/concepts/plugins):
  packaging skills, MCP connections, and optional visual capabilities.
- [Build an MCP server](https://developers.openai.com/plugins/build/mcp-server):
  HTTPS transport, Inspector, and real-host testing.
- [MCP Apps quickstart](https://developers.openai.com/plugins/build/app-quickstart):
  optional embedded visual experience.
- [Build plugins](https://developers.openai.com/plugins/build/plugins):
  current manifests and packaging.
- [Submission](https://developers.openai.com/plugins/deploy/submission):
  review and publication requirements.

The intended result is broad public usefulness with documented evidence and
recoverable releases. No test plan can substantiate a promise that software will
work flawlessly for every user, account, dataset, or future host version.
