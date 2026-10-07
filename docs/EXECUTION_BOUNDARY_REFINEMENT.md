# Execution boundary refinement: embedded resource and CI dependencies

Prepared 2026-10-07. Targeted Astra planning revision only; no implementation or
verification success is implied by this document.

## Scope and controlling evidence

This amendment resolves two concrete integration boundaries in the existing
visual/plugin and data-trust plans. All other acceptance criteria remain in force.

The root's current focused dictionary/static run reports **5 failures and 117
passes**. The five failures follow inclusion of `static/mcp-app.html` in the
public-portal `PAGES` list: exact ten-page membership, common masthead, full AI
footer, linked design stylesheet, and raw-template reduced-motion checks. The
root separately reports five dictionary checks passing after a fresh 79-route
dictionary build. These observations are not a final full-suite result.

Targeted inspection establishes:

- `tests/test_static_pages.py` discovers every HTML file in `ALL_PAGES`; its
  `PAGES` subset excludes only four explicitly named nonportal pages. Every
  `ALL_PAGES` member receives JavaScript parsing. Public checks currently expect
  exactly ten named portal pages.
- `src/mcp_apps.py::read_resource` composes `mcp-app.html` with the committed
  `design.css` and `visual-components.js` using exact single-use placeholders.
  The delivered resource includes reduced-motion and focus rules from shared
  CSS. It is an embedded report with its own main landmark and website link,
  rather than a portal navigation page. Its advertised and returned network
  allowlists are empty.
- `tests/test_mcp_resources.py` already exercises the real resource handler,
  asset composition, narrow resource allowlist and empty network CSP, but does
  not parse the final composed JavaScript or assert composed accessibility CSS.
- `tests/test_mcp_schemas.py::_run_ajv` executes
  `tests/plugin/validate-tool-outputs.mjs`, whose static import requires
  `ajv/dist/2020.js`. `tests/plugin/package.json` and its lockfile pin AJV 8.20.0.
  `node_modules/` is ignored. `.github/workflows/ci.yml` installs Python
  dependencies only and then invokes pytest. A clean checkout cannot obtain
  this JavaScript dependency from that workflow.

The missing dependency-install step is the demonstrated blocker contemplated by
the data-trust plan's T5 clause allowing a narrowly necessary CI change. This
amendment explicitly authorizes that repository-file change. It does not change
the separate **A-CI-01** requirement for actual Linux evidence at the tested
revision, and does not authorize changing GitHub account/repository Actions
settings. The root reports Actions disabled and approval to restore it pending.

## Exact ownership

The implementation worker owns only:

1. `tests/test_static_pages.py` — deliberate embedded-resource classification.
2. `tests/test_mcp_resources.py` — checks against the delivered composed resource.
3. `.github/workflows/ci.yml` — dependency preflight/install before pytest.

This planner owns `docs/EXECUTION_BOUNDARY_REFINEMENT.md`. Implementation results
are reported to the root; this amendment does not add another evidence artifact.
The worker is not alone in the checkout: other agents own the UI, shared assets,
runtime and other tests. Do not revert or overwrite their edits. Coordinate
before any ownership overlap. No changes to HTML, CSS, JavaScript assets,
`src/mcp_apps.py`, dependency versions/lockfiles, the public-page assertions,
Python matrix, external settings, deployment or architecture are authorized by
this amendment. A newly discovered runtime defect returns to the root/planner.

## Ordered implementation

### 1. Classify the embedded HTML explicitly

In `tests/test_static_pages.py`, introduce a separate exact-name collection such
as `EMBEDDED_PAGES = {"mcp-app.html"}` and exclude it when deriving public
`PAGES`. Preserve the existing private/nonportal names and retain the unfiltered
`ALL_PAGES` discovery and parsing parametrization. Explain that this is a composed
MCP resource, with distinct checks in `test_mcp_resources.py`.

Keep the exact ten expected public names and every existing public design and
accessibility assertion. Do not exclude by prefix, suffix, wildcard, missing
masthead, or automatic feature detection. Add a focused membership assertion
proving the embedded name exists in `ALL_PAGES` and is absent from `PAGES`, so its
classification cannot silently become a missing-file exemption. Any newly added
unclassified HTML must still trip the public expected-pages check.

### 2. Test what the embedded host actually receives

Extend `tests/test_mcp_resources.py` using the real successful `resources/read`
handler result, not a second hand-built composition algorithm. Write its returned
HTML to pytest's `tmp_path` and use the existing `check_page` parser helper to
parse all final inline scripts together. Require nonempty scripts before parsing
so an empty output cannot pass vacuously. Keep the separate raw-template parser
coverage from step 1.

Assert against the composed output that it has language metadata, a main
landmark, the report's live/status announcement semantics, and the shared
`prefers-reduced-motion` and `:focus-visible` CSS. Verify shared stylesheet/helper
injection and absence of unresolved placeholders. The iframe has no repeated
portal navigation to bypass; do not impose a portal skip link, full masthead,
full public AI footer, or a stylesheet network link to satisfy these tests.
The broader embedded disclosure, value, limits, table and interaction criteria
remain the responsibility of the existing visual/plugin acceptance plan.

Preserve current allowlist/CSP/path rejection tests. Add explicit checks that the
composed document has no external script source or stylesheet load, no stylesheet
`@import`, and no CDN-backed resources. Preserve current no-fetch/no-tracking
assertions and the useful `https://txisd.dev/` website anchor; a user-activated
website link is not a resource fetch. Reuse existing Node availability handling
for local parser checks, while keeping CI's existing mandatory parser step.

### 3. Install the pinned validator dependency in CI

Add one clearly named step before the static parser and pytest steps with:

```yaml
- name: Install plugin validation dependencies
  run: |
    node --version
    npm --version
    npm ci --ignore-scripts --prefix tests/plugin
```

This makes the actual runner Node/npm versions explicit in the log and fails
early if either executable is missing; it does not silently skip schema tests.
Use the existing Ubuntu runner runtime for this bounded fix. Preserve both
existing SHA-pinned GitHub actions, their settings, Python 3.10/3.11/3.12, locked
uv setup, lint, mandatory JavaScript parse step and complete pytest invocation.
Do not add a floating setup action, caching, a second dependency manifest,
package version changes, `npm install`, or `continue-on-error`.

### 4. Verify locally, then record Linux availability honestly

Run the install command from the repository root, confirm the installed AJV
version is 8.20.0 and neither manifest nor lockfile changed, then execute the
static-page, MCP-resource and MCP-schema test files with the repository's locked
Python environment. Run the existing standalone JavaScript parser and ruff on
the changed Python tests. Root integration remains responsible for the planned
full default/UTF-8 Windows runs and broader lint/lock checks after concurrent
work settles.

For clean-install evidence without disturbing another worker's dependencies,
copy only the plugin manifest, lockfile and validator scripts to a disposable
temporary directory, run `npm ci --ignore-scripts` there and verify the AJV import
resolves at 8.20.0. This local smoke check establishes lockfile-based bootstrap;
it does not establish Linux CI success. Preserve any shared existing
`tests/plugin/node_modules` while other workers are using it.

A fresh Luna verifier inspects the final diff and targeted results against the
criteria below. Actual Linux Python-matrix evidence remains UNVERIFIED until
Actions is available and all three jobs pass at the implementation revision.
Never mark a local install or workflow edit as restoration of external Actions.

## Objective acceptance criteria

| ID | PASS evidence |
|---|---|
| BR-STATIC-01 | `PAGES` contains exactly the original ten named public pages; the four existing private/nonportal exclusions remain; only explicitly named `mcp-app.html` is additionally excluded. Every existing public-page assertion is retained and the focused static suite passes. |
| BR-STATIC-02 | `mcp-app.html` is present in `ALL_PAGES` and remains a raw-template parser case. A separate successful handler read produces nonempty inline scripts that parse together through the existing parser. |
| BR-APP-01 | Tests on the actual composed resource prove language/main/status semantics, shared focus-visible and reduced-motion rules, injected shared assets and no unresolved placeholders. No portal chrome or network stylesheet was added to make the tests pass. This is limited structural evidence, not a full accessibility certification. |
| BR-APP-02 | Resource allowlist/path/CSP tests still pass; composed-resource checks reject external scripts/styles/imports/CDNs and retain no-fetch/no-tracking assertions while preserving its website link. |
| BR-CI-01 | Workflow logs Node/npm versions and installs from the existing pinned plugin lockfile using `npm ci --ignore-scripts --prefix tests/plugin` before parsing/tests. Existing action SHAs/settings, Python matrix, uv locks, lint, parser and full pytest checks remain intact. No dependency/version/lockfile change occurs. |
| BR-CI-02 | Disposable clean-install smoke resolves AJV 8.20.0; focused static/resource/schema tests and the standalone parser pass. The fresh verifier records concrete results and any skips rather than assuming success. |
| BR-SCOPE-01 | Implementation diff stays within the three owned files; no external Actions setting, application source/asset, architecture, dependency or deployment change is included. |
| A-CI-01 (unchanged) | Actual Linux CI passes Python 3.10, 3.11 and 3.12 at the implementation revision. Until available, report UNVERIFIED separately from local PASS results. |

If either boundary requires a different implementation scope, return the specific
failure evidence to Astra before proceeding. Existing LATL repair/escalation
rules apply; no broad audit or architecture change is introduced here.
