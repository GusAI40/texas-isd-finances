# MCP/plugin acceptance verification

**Verifier:** fresh Luna review, read-only implementation audit
**Date:** 2026-10-07
**Checkout:** `37ec5d23c7e8380531db7507bb15c3950ea1d9f1` (working tree contains the implementation changes)
**Scope:** acceptance IDs D-HOST-01 through E-PUBLIC-01 in `docs/MCP_PLUGIN_IMPLEMENTATION_PLAN.md`.

## Evidence run

- `.venv\\Scripts\\python.exe -m pytest tests/test_mcp.py tests/test_mcp_parity.py tests/test_mcp_schemas.py tests/test_mcp_resources.py tests/test_plugin_package.py -q`: **68 passed**, one unrelated Starlette deprecation warning.
- `npm run validate -- ..\\..\\plugin` from `tests/plugin`: **PASS** using pinned AJV 8.20.0.
- `npx playwright test tests/browser/mcp-app.spec.js --project=chromium`: **PASS** for the two no-bridge/self-contained frame cases (desktop and 390px). This does not exercise a host tool-result frame.
- A temporary Node program using the pinned AJV 8.20.0 recursively compiled each of the eleven current output schemas against the eleven saved connector payloads. It rejected a nested wrong type, rejected a missing required `limits`, and accepted the explicit nullable `students: null` case. **The run exposed invalid schemas before data validation:** AJV strict schema validation rejects duplicate `limits` entries in `required` (notably schemas built through `_success([... , "limits"], ...)`).
- Inspector portability evidence now exists at `docs/evidence/mcp-host/inspector-portability.json`, with the exact warning and disposition. It is against deployed revision `73df1896…`, while this checkout is a later implementation revision.
- Inspector evidence: `docs/evidence/mcp-host/inspector-results.json`; owner connector evidence: `docs/evidence/mcp-host/connector-results.json`; generated mapping evidence: `docs/evidence/mcp-host/generated-package.json`; release summary: `docs/evidence/mcp/release-matrix.json`.

## Acceptance results

| ID | Result | Evidence and blocking gap |
|---|---|---|
| D-HOST-01 | **PASS (evidence; deployment caveat)** | `docs/evidence/mcp-host/inspector-portability.json` now records the exact one-warning text (multi-type nullable `students`) and the reviewed disposition (retain null semantics, migrate to `anyOf`, repeat strict Inspector). The matrix also records modern success, legacy HTTP 400/-32601, 11/11 owner-host calls, and aggregate-frame limits. The warning evidence is from deployed `73df1896…`, so strict Inspector must be repeated after this implementation revision before treating the live endpoint as closed. |
| D-PARITY-01 | **FAIL** | The new fixture records hashes/vintages for `economics_data.json`, `forensic_data.json`, and `national_data.json`, and identifiers for Dallas/Houston/Tioga/Pineywoods/charter. However, `tests/test_mcp_parity.py` only asserts those anchors and six-digit formatting; it does not independently assert all eleven tool field/value/year/limits contracts or the required bounds and MRTR accept/decline cases. Those remain covered only by selected `test_mcp.py` behavior tests, so the full criterion is not met. |
| D-SCHEMA-01 | **FAIL** | Distinct per-tool schemas now exist and the 68-test suite's custom matcher accepts all eleven saved successes, but a real recursive AJV compile fails schema validation because `_success()` can emit duplicate `limits` entries in `required` when callers include `limits` (observed before payload validation). The test matcher also does not enforce nested object fields/types. Therefore the criterion's actual-schema validation is not complete until schemas compile under strict JSON Schema and nested adversarial cases are part of the test gate. |
| D-BOUNDARY-01 | **PASS (local)** | `tests/test_mcp.py` passes the origin, mirrored header, version, cache, no-DB, no-write/no-LLM, `/query` exclusion, read-only annotation, and unknown-tool checks. `src/mcp_apps.py` only reads committed static assets and rejects unknown resource URIs. This is a local implementation result; it is not an independent-host security claim. |
| D-RESOURCE-01 | **PASS (local)** | `tests/test_mcp_resources.py` passes the single `ui://txisd/report/v1.html` resource, MIME/CSP metadata, unknown/path-like rejection, marker composition, shared-helper reuse, and missing-asset behavior. `src/mcp_protocol.py` advertises resources only when callbacks are supplied and `src/api.py` wires the callbacks. |
| E-VISUAL-01 | **FAIL** | The payload adapter and no-bridge frame are present, and the focused Chromium cases pass. The required `tests/fixtures/mcp_visual_payloads.json` and host-result visual assertions are absent; the browser test only checks the empty/no-bridge state and no network requests. Existing B/C visual measurements are for the website, not these MCP frames, so source-value/status/ratio/accessibility parity for district/comparison/statewide frames is not established. |
| E-BRIDGE-01 | **UNVERIFIED** | Static code contains source/message-shape checks, pending-request timeout handling, safe `txisd.dev` links, empty network CSP, and no `ask.js`/`track.js`. The saved owner-host evidence is against the registered endpoint and reports aggregate tool activity only. The visual resource was not rendered in ChatGPT at this implementation revision; the recorded deployed host revision is `73df`, while the implementation checkout is `37ec5d2`. |
| E-PACKAGE-01 | **PASS (local/owner mapping)** | `tests/test_plugin_package.py` passes, and `tests/plugin/validate.mjs` passes pinned AJV 8.20.0 validation of package manifests, references, public no-auth endpoint, skill frontmatter, mapping shape, and private registration/conversation-data checks. `generated-package.json` records the creator-generated `dev-…` to `asdk_app_…` mapping and hash. This proves the owner development registration/export and local package validation; it does not prove installation or public distribution. |
| E-LISTING-01 | **FAIL** | `plugin/LISTING.md` and `docs/CHATGPT_PLUGIN.md` are candid about unverified gates and name public privacy/transparency/support URLs. However, no evidence records screenshot revision/vintage or reachability/content verification for those URLs, and the assets are not tied to a tested MCP frame. The listing therefore does not meet the plan's evidence requirement yet. |
| E-INSTALL-01 | **UNVERIFIED** | The saved evidence explicitly says endpoint registration is not an install test. No fresh supported test-channel package installation/chat evidence exists. |
| E-PUBLIC-01 | **UNVERIFIED** | No independent eligible-account installation or public directory review/listing evidence is present. The owner registration ID is correctly treated as non-transferable evidence. |

## Targeted follow-up files

- D parity/schema: `tests/test_mcp_parity.py` (missing), `tests/test_mcp_schemas.py`, and `src/mcp_tools.py` (`_OUTPUT_SCHEMA`, `list_tools`).
- Host warning: `docs/evidence/mcp-host/inspector-results.json` and `docs/evidence/mcp/compatibility.json`.
- Visual verification: `tests/browser/mcp-app.spec.js`, missing `tests/fixtures/mcp_visual_payloads.json`, `static/mcp-app.html`, and `src/mcp_apps.py`.
- Listing evidence: `plugin/LISTING.md`, `docs/CHATGPT_PLUGIN.md`, `plugin/assets/`, and `docs/evidence/mcp/release-matrix.json`.

No code or files outside this verification report were changed by this review.
