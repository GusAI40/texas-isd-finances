# Independent E-BRIDGE local verification

Date: 2026-10-07  
Verifier: fresh read-only Luna pass  
Revision: `de49c2f6c21baf4e818c8be284deec8512e0a692` (`de49c2f`) with working-tree changes. Only this evidence report was added.

## Commands and inputs

The actual cross-origin sandbox harness ran from `tests/browser`:

```text
node_modules\\.bin\\playwright.cmd test mcp-app.spec.js --project=chromium --project=firefox --reporter=line
56 passed (48.5s)
```

The focused resource/schema/static checks also passed:

```text
.venv\\Scripts\\python.exe -m pytest tests/test_mcp_resources.py tests/test_static_pages.py tests/test_mcp_schemas.py -q
124 passed in 7.02s
```

Inspected working-file SHA-256 values:

```text
static/mcp-app.html                         CCC2AB8B7D9856FEBB0AA55C7EFE16DA136EDF0915FE8ED647608996D2B284F8
tests/browser/mcp-app.spec.js               C4608EA48BD1D19D97097CF521BECB6D5290B2EBA5B2540E2FB0DA3812304470
tests/fixtures/mcp_visual_payloads.json     AD4EAF27BE80FFC90DAC4DFDDB72530AD7543B0454ABCBF4D591E3A7FC5320DC
docs/evidence/mcp/e1-bridge-browser.json    0F134FC1B9CE873975DEA148AA23B6585454F504BB933BFDCDE3090CA9D72329
```

## Results

| Check | Result | Evidence |
|---|---|---|
| Cross-origin parent bridge and readiness | **PASS** | Chromium and Firefox tests exercised initialize request/response, initialized notification, parent-window source checks, delayed response, initialize error, timeout, and top-level no-parent state. |
| Message authenticity and state safety | **PASS** | The harness rejected a real sibling-frame spoof, malformed/stale/unsolicited envelopes, unsafe payload URLs, and tool errors; repeated parent updates did not leave stale or duplicate DOM. |
| Renderer content and chart semantics | **PASS** | 56 tests assert visible text and content, not only tags: values, period/source period, units, population, denominator, status, source label/URL, limits, district IDs, and deep links across Chromium/Firefox, three viewports, and light/dark themes. |
| Null/negative/zero/mixed-period behavior | **PASS** | Synthetic browser cases verified negative direction and zero baseline marks, missing values as cards, singleton handling, and separate 2025/2024 metric groups without mixed scales. |
| Resource metadata/CSP | **PASS** | Focused resource tests passed; the advertised resource retains empty connect/resource/frame CSP domains. Browser harness observed only allowlisted local host/widget/sibling documents and no third-party requests. |
| Current artifact fixture parity | **PASS** | Fresh `src.mcp_tools.call_tool(...).structuredContent.visual` comparison now equals all three saved views (district, comparison, statewide) after owner recapture. Comparison rows retain finance period 2025 and outcome period 2024; Dallas/Houston populations are district-specific. |
| Widget fixture regeneration | **PASS locally** | The current fixture is byte-for-value equal after JSON decoding to fresh tool transformations for all three normal calls. This local result does not establish actual ChatGPT rendering. |
| Actual ChatGPT rendering | **UNVERIFIED** | Local browser evidence cannot certify rendering in an actual ChatGPT host. |
| 95/5 semantic painted-mark gate | **UNVERIFIED** | The visual-measurement workstream owns this separate ratio verdict; no new ratio claim was made. |

The implementation inspection confirms `event.source === parent` is required
for incoming widget messages, pending requests are removed on resolution or
eight-second timeout, and rendering groups metrics by definition, period, unit,
and denominator. The old evidence's population issue is also visible in the
saved fixture, while the current source adapter remains the implementation under
test; fixture regeneration belongs to the widget owner.

No implementation, fixture, source artifact, production, deployment, or host
state was changed.
