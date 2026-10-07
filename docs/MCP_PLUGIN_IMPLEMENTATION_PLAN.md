# Packages D/E: verified MCP tools and visual plugin package

**Date:** 2026-10-07. **Stage:** executable refinement; no implementation or publication.
**Parents:** [execution plan](VISUAL_PLUGIN_EXECUTION_PLAN.md) and
[visual interface plan](VISUAL_IMPLEMENTATION_PLAN.md).

## Goal and revised compatibility decision

Reuse the working, public, deterministic MCP service to answer district questions
in ChatGPT, optionally show a compact accessible visual answer, and produce a
validated portable plugin package ready for review. Preserve all eleven tools,
their existing data semantics, bounded inputs, limits, and no-auth artifact access.
The website remains the public access path independent of plugin eligibility.

The following new evidence replaces the earlier compatibility uncertainty:

| Probe | Observed result and limit |
|---|---|
| MCP Inspector 2.9.0, legacy mode | `tools/list` cannot pass legacy initialization: HTTP 400, JSON-RPC -32601. This is a compatibility limitation for that mode. |
| Inspector, modern mode | Discovery/tool listing succeeds with eleven tools. Schema portability reports zero errors and one warning, whose exact content must be recorded and reviewed. |
| Actual ChatGPT custom MCP connection | Public HTTPS endpoint, no authentication, registration and connection succeeded. A fresh chat selected the registered plugin and reported eleven successful tool calls with public figures. |
| Host evidence quality | Visible aggregate activity and resulting answer were observed; individual host tool frames were not exported. Do not label the result a captured per-tool transport transcript. |
| Not yet established | Visual resource rendering, package installation, independent-account installation, public review/listing, and complete output/source parity. |

**Decision:** retain stateless MCP 2026-07-28. No blanket legacy adapter, SDK
replacement, session store, or transport rewrite is justified by the current
ChatGPT result. A future demonstrated required-host failure may trigger a narrowly
planned adapter; it must return to the planner with reproducible evidence first.

Retain the registered technical plugin identity in the operator handoff. Do not
commit private chat URLs, conversation IDs, account names, screenshots exposing
unrelated chats, or account settings. A technical registration ID is different
from a conversation ID: use the real verified registration only where the official
package mapping requires it, after confirming it still targets this public server.
Never invent a replacement identifier or copy an example registration from docs.

## Ownership and implementation boundaries

D/E exclusively owns `src/mcp_protocol.py`, `src/mcp_tools.py`, new MCP-only
tests, `static/mcp-app.html`, and the `plugin/` package. `src/mcp_apps.py` may be
added as the bounded resource/payload adapter rather than expanding the API file.
No database, LLM provider, private operations, contact data, network data ingestion,
or sending capability may enter the tools or widget.

The UI owner is currently changing `src/api.py` only for its explicit shared-JS
route and owns `static/visual-components.js`, `static/design.css`, and the browser
harness. D/E must wait for an explicit ownership handoff before touching those
files. The only planned API edit is passing resource callbacks into the existing
MCP handler; preserve the UI asset route and other edits. Consume the finalized
`window.TxisdVisual` interface unchanged if possible. Any needed extension is
proposed to the UI owner first. Add D/E browser tests as a new file without editing
the UI runner/config unless coordinated. A owns finance and generated dictionaries.

## Contracts to preserve and extend

`mcp_protocol.handle(raw, headers, call_tool, list_tools, instructions,
allowed_origins)` currently dispatches discovery, list, and calls. Add optional
`list_resources` and `read_resource` callbacks, defaulting to absent, so existing
callers/tests retain behavior. Preserve request `_meta`/header mirroring, origin
validation, version rejection, notifications, MRTR `input_required`, cache behavior,
and protocol error distinction. No mutable cross-request state is required.

`mcp_tools.list_tools()` strips handlers from the ordered registry;
`call_tool(name,args,input_responses)` returns text plus `structuredContent` for
success, `isError` for tool failures, and MRTR requests for unresolved ambiguity.
Correct the stale docstring denying MRTR; do not delete the implemented feature.
Do not turn declined ambiguity into a guessed district or an empty successful
financial result.

Preserve the existing structured keys for all tools. Add an optional `visual`
object to successful `district_money`, `compare_districts`, and `texas_overview`
results only. Other tools keep useful text/structured answers without opening a
redundant frame. The original text must retain headline limitations regardless
of visual availability.

```text
visual:
  schemaVersion: 1
  view: district | comparison | statewide
  districts: [{ district_number, district_name }]
  metrics: [Metric from VISUAL_IMPLEMENTATION_PLAN.md]
  limits: [source limitations, not hidden UI-only metadata]
  websiteUrl: https://txisd.dev/ or /?d=<validated six-digit ID>
```

Every Metric carries value, label, unit, period, population/denominator, status,
source identity/URL/period, limits, and model assumptions if relevant. Map only
existing artifact fields; do not request DB summary values to force equality with
the website. A field unavailable in the tool's source remains unavailable. Compare
figures only when metric definition, period, unit, and denominator agree; otherwise
state the difference. Do not give unresolved freshness or anomaly findings a
verified status. Tool-data parity is against the exact source and comparable site
measure, not against any similarly named dollar amount.

## Ordered bounded tasks

### D1 — Record compatibility and establish parity tests

**Own:** `docs/MCP_COMPATIBILITY.md`, `tests/test_mcp_parity.py`,
`tests/fixtures/mcp_cases.json`, `docs/evidence/mcp/compatibility.json`.

Record the probe matrix above with dates, Inspector version/mode, endpoint,
revision where known, observed success/error and evidence limits. Incorporate
root's completed all-tool/invalid-case Inspector results when available; do not
assume their status while still running. Review the one portability warning by
its actual text and identify whether it affects supported clients.

Lock the registry's exact eleven names: `find_district`, `district_money`,
`district_lineage`, `district_forensics`, `district_trends`, `district_bonds`,
`district_campuses`, `district_debt`, `district_national`, `texas_overview`, and
`compare_districts`. For every success case independently select expected public
source fields rather than calling the handler to construct its own expectation.
Use Dallas `057905`, Houston `101912`, Tioga `091907`, and Pineywoods `003801`;
the charter national result must carry its applicable absence reason. Preserve
leading-zero behavior and existing name disambiguation.

Test unknown/malformed IDs, duplicate/ambiguous names, invalid argument types,
comparison bounds 1/2/6/7, unavailable artifacts, null values, limits, and MRTR
accept/decline/retry. Identify source filename/hash, data vintage and JSON field
path for each comparison. Mock database/LLM/write entry points to raise if invoked;
calls must remain successful without those dependencies. Verify no hidden
operational endpoint appears in the registry.

**Verify:** `python -m pytest tests/test_mcp.py tests/test_mcp_parity.py -q`.
Add newly failing expectations before implementing D2; distinguish test setup
errors from expected RED evidence.

### D2 — Add portable output contracts and additive visual payloads

**Own:** `src/mcp_tools.py`, `src/mcp_apps.py`, `tests/test_mcp_parity.py`,
`tests/test_mcp_schemas.py`.

Describe each successful tool's actual structured output with an output schema,
including nullable fields and absence variants; currently only `find_district`
has one. Keep schemas honest and bounded without rejecting existing legitimate
payloads or forcing every nested artifact field into a fabricated uniform type.
Do not use a completely unconstrained object as a substitute for documenting
the required result/limits contract. Validate successful fixtures against their
schema. Model error/MRTR envelopes separately from successful output schemas.

Implement the three visual mappings as pure transformations of the handlers'
already-loaded structured public data. No new source or second set of numerical
calculations. Add read-only/non-destructive metadata consistent with actual
behavior. Preserve existing handler dispatch order, inputs, text, limits and
successful output keys. Apply schema corrections for the actual portability
warning only when tests show the specific change is necessary.

**Verify:** `python -m pytest tests/test_mcp_parity.py tests/test_mcp_schemas.py -q`;
modern Inspector schema check must show no errors. Document any remaining warning.
Use a pinned development-only JSON-schema validator; coordinate dependency setup
with the package validation harness below rather than adding a runtime dependency.

### D3 — Expose a single versioned visual resource

**Own:** `src/mcp_protocol.py`, `src/mcp_apps.py`, `tests/test_mcp_resources.py`,
`docs/MCP.md`. **Coordinated edit:** `src/api.py` MCP callback wiring only, after
the UI owner releases that file.

Serve one allowlisted resource, `ui://txisd/report/v1.html`, through resources
discovery/read. Reject unknown resources and path-like/traversal inputs; never
read arbitrary disk paths or proxy URLs. Advertise resources only when callbacks
exist, and associate the resource only with D2's three visual tools. Retain old
tool behavior for hosts that ignore UI metadata.

The resource provider composes `static/mcp-app.html` with the exact current
`static/visual-components.js` and selected shared styles using fixed replacement
markers, so no CDN or runtime network dependency is required. Do not duplicate
the helper's logic in the widget. Validate markers and escape inline closing-script
sequences during composition; reject missing assets. Keep the generated HTML in
memory, derived from committed files, rather than creating another hand-maintained
bundle. Test the resource references the same helper bytes/behavior as the site.

Use MCP Apps MIME `text/html;profile=mcp-app` and `_meta.ui.resourceUri`.
Declare exact UI CSP metadata; this self-contained frame needs no network or
nested-frame origins. A resource version is a cache key: change it on breaking
HTML/JS/CSS changes. Confirm metadata against current host docs and actual
rendering; do not relax the site's global CSP to make the frame work.
[Official UI reference](https://developers.openai.com/plugins/build/chatgpt-ui).

**Verify:** `python -m pytest tests/test_mcp.py tests/test_mcp_resources.py -q`;
Inspector modern discovery/list/read succeeds; legacy rejection remains an
explicit known compatibility result, not a regression hidden by skipped tests.

### E1 — Implement a small accessible visual answer

**Own:** `static/mcp-app.html`, `tests/browser/mcp-app.spec.js`,
`tests/fixtures/mcp_visual_payloads.json`. Consume UI-owned shared assets read-only.

Build district money, two-to-six district comparison, and statewide summary views
from `visual.metrics`. Reuse shared metadata/table helpers and the website's
color/type rules. Render finite values and separate modeled/missing/not-applicable/
unverified states, with visible year/unit/denominator/status and source/limits.
Show comparisons as matching bars/small multiples and a real semantic table;
zero is not missing. Provide safe source links and the district website deep link.
No login, persistent user storage, tracking scripts, paid queries, write controls,
or private operations. Do not include `ask.js`/`track.js` in the resource.

Use the standard MCP Apps postMessage bridge: initialize, announce readiness,
accept tool-result notifications, and issue only explicitly selected read-only
tool calls when needed. Validate `event.source`, message shape/method/request ID,
and documented origin behavior; maintain pending-request timeouts and reject
stale/unsolicited responses. Follow the host's sandbox origin contract rather
than hardcoding a guessed origin. No `eval`, HTML injection, arbitrary navigation,
or fetching a URL supplied in tool output. A missing/failed bridge shows a useful
noninteractive explanation and website link, without pretending it is connected.
[Official bridge quickstart](https://developers.openai.com/plugins/build/app-quickstart).

Test success, absent visual payload, malformed fields, tool errors, loading,
repeated updates, ambiguous-district flow, missing bridge, and delayed responses.
Host tool notifications and user-initiated reads must update the existing frame
without stale district labels or duplicated event listeners. If the frame doesn't
need new tool calls, omit that capability rather than adding unused controls.

**Verify:** run the shared browser harness in Chromium/Firefox at the B/C three
viewports and both themes; assert source/table/value parity, keyboard/focus,
reflow, contrast and no external network. Reuse B/C's 95/5 collector with actual
host-frame dimensions recorded separately. Simulated bridge tests do not replace
actual ChatGPT visual rendering, which remains a later host gate.

### E2a — Create the portable package and real registered mapping

**Own:** `plugin/plugin.json`, `plugin/mcp.json`, `plugin/.app.json`,
`plugin/skills/district-report/SKILL.md`.

Use root portable manifests with `$schema` references to Agent Plugins 1.0.0
plugin/MCP schemas. Name the package `texas-isd-finances`; use stable HTTPS
`https://txisd.dev/mcp`, transport `streamable-http`, and no authentication.
Place OpenAI presentation settings under `extensions.com.openai`; its `apps`
field points to `./.app.json`. Obtain that file's exact registered-mapping shape
from an official schema/current creator output, then use the root-verified
technical registration ID. Do not guess keys. Keep paths package-relative.
No lifecycle hooks or duplicate compatibility manifests are required.
[Official package guide](https://developers.openai.com/plugins/build/plugins).

The district-report skill instructs resolution/disambiguation first, then
appropriate deterministic tools, comparable periods/definitions, visible limits,
and source links. It must not instruct another model to ignore user instructions,
hide uncertainty, invent data, call private/paid endpoints, or promise universal
availability. It should help the five B/C public tasks within the available data;
explicitly state unsupported questions instead of substituting another measure.

### E2b — Validate schemas and package references

**Own:** `tests/plugin/package.json`, `tests/plugin/package-lock.json`,
`tests/plugin/validate.mjs`, `tests/test_plugin_package.py`.

Create an isolated, pinned development-only schema-validation runner. Retrieve
the official manifest/MCP schemas, referenced schemas and relevant OpenAI mapping
contract, record URL/version/hash, and validate with a maintained JSON-schema
validator supporting the declared dialect. Cache verified schema inputs outside
runtime source; an unavailable schema is UNVERIFIED, not a homemade substitute.
No use of JSON parsing alone as a claim of schema validation. Provide `npm run
validate -- <package-path>` and a test entry point with explicit missing-tool
failure, not a skip. Include traversal/missing-file/unsupported-field fixtures,
bad endpoint/auth cases, and a fabricated registered ID case. Verify mapping
identity against root's actual registration evidence, not just its prefix.

Validate package references and nested skill frontmatter; check packaged content
for forbidden private conversation/account data and credentials. Confirm OpenAI
registration mapping and portable MCP wiring resolve to the same server without
creating two duplicate visible tool sets in tested hosts. Any host-specific
duplication requires a focused packaging revision, not a transport rewrite.

**Verify:** run the schema validator and
`python -m pytest tests/test_plugin_package.py -q`; save validator version,
schema hashes and exact results. Revalidate the staged package including assets.

### E3 — Prepare truthful listing, privacy, and support materials

**Own:** `plugin/assets/icon.svg`, `plugin/assets/district-report.png`,
`plugin/assets/comparison.png`, `docs/CHATGPT_PLUGIN.md`,
`plugin/LISTING.md`.

Use the current project identity and real widget screenshots with public fixtures;
no invented badges, testimonials, reviewer approval, or participant findings.
Record screenshot revision/vintage. If the official package schema demands a
different image format, generate the required equivalent from the same source
and coordinate that exact path before changing references.

Prepare concise purpose, read-only capabilities, examples, limitations, data
sources, unsupported cases, installation/testing steps, review checklist and
support/privacy URLs. Reuse verified public website `/about#privacy`,
`/transparency`, and repository issue/support paths only when their actual content
matches the proposed statement; check reachability and public permissions. Do
not invent an email address or assume a commercial contact is plugin support.
If a suitable public support or privacy statement is missing, record the exact
needed public-page change for coordinated review rather than claiming completion.

Distinguish public district data and application behavior from ChatGPT/provider
retention. The tools do not themselves call `/query`; the website's stored-question
flow is separate. Verify logging behavior before saying requests are not stored;
no-auth does not mean no infrastructure logs. Never promise anonymous browsing,
no retention, or access for every account without evidence.

### E4 — Verify the resulting package in real hosts; prepare review handoff

**Own:** `docs/evidence/mcp/release-matrix.json`, `docs/MCP_COMPATIBILITY.md`,
`docs/CHATGPT_PLUGIN.md`. Root owns account interactions and any later authorized
submission; this plan does not submit or publish.

Run all eleven tool fixtures and negative/MRTR cases in modern Inspector against
the implemented revision; repeat relevant tools in actual ChatGPT. Verify the
three visual-tool frames load, present exact result values/status/limits, and
link to the correct district. Test a new chat and a repeated district switch.
Record observed host/version/date and per-check evidence; if the host reveals
only aggregate activity, retain that limitation instead of inventing raw frames.

Validate a real package install in the available local/test channel, separately
from the already-working custom endpoint registration. Public reachability and
owner-account use are not public-directory distribution. Prepare the review-ready
package and instructions using current
[submission requirements](https://developers.openai.com/plugins/deploy/submission).
Independent eligible-account install and a visible public listing are release
gates; if unavailable, record them as UNVERIFIED or pending review. Do not infer
that a technical registration is transferable to every account.

## Acceptance matrix

| ID | Objective PASS condition |
|---|---|
| D-HOST-01 | Dated compatibility matrix preserves observed modern Inspector/ChatGPT success, explicit legacy failure, the actual portability warning and host-evidence limits; no unjustified transport adapter. |
| D-PARITY-01 | All eleven tool names/contracts survive; independent artifact field/value/year/limit fixtures pass, including charset/leading zeros, missing/charter, bounds and MRTR accept/decline. |
| D-SCHEMA-01 | Successful results validate against actual output schemas; errors/MRTR retain their own envelopes; no portability errors and any remaining warning has a reviewed disposition. |
| D-BOUNDARY-01 | Instrumented tests prove tool/resource calls use public artifacts only, no DB/LLM/write/private operation, with existing origin/header/version/cache safeguards intact. |
| D-RESOURCE-01 | The one allowlisted versioned resource lists/reads correctly; traversal/unknown paths fail; only intended tools link it; helper reuse and asset availability are proved. |
| E-VISUAL-01 | District/comparison/statewide frames match their source payloads and B/C semantics, ratios and accessibility checks; absent visual support preserves useful sourced text. |
| E-BRIDGE-01 | Bridge success/error/timeout/update/spoofed-message cases pass; CSP permits only demonstrated needs, no third-party network/tracking/private or paid path. Actual ChatGPT renders the implemented resource. |
| E-PACKAGE-01 | Official-schema and package-reference validation passes; verified real registration mapping targets this endpoint; no invented identity, duplicate tools, private chat data or credentials. |
| E-LISTING-01 | Listing assets reflect actual tested UI and vintages; capabilities, privacy/support URLs and limitations match verified behavior; no fabricated reach/approval/usability claim. |
| E-INSTALL-01 | Resulting package installs and works in a fresh supported test-channel chat; endpoint-registration success alone does not satisfy this criterion. |
| E-PUBLIC-01 | Independent eligible-account install and actual public listing/review status are verified after authorized publication; otherwise explicitly pending/UNVERIFIED. |

Sequence D1 → D2 → D3 → E1; package authoring/validation can proceed once D1's
registration evidence is available, while screenshots wait for E1. Shared-file
wiring waits for B/C ownership handoff. Run focused pytest, direct widget JS
syntax checks, schema validation, browser tests and real-host probes; report each
ID as PASS/FAIL/UNVERIFIED with revision and evidence. No local mocked test can
close an actual-host, installation, review or public-access gate.
