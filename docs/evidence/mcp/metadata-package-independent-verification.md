# Independent metadata, package, and CP-06 verification

Date: 2026-10-07  
Verifier: fresh read-only Luna pass  
Revision: `de49c2f6c21baf4e818c8be284deec8512e0a692` (`de49c2f`) with working-tree changes. Only evidence documents were changed by this pass.

## Execution evidence

The full widget harness completed in both requested browsers:

```text
node_modules\\.bin\\playwright.cmd test mcp-app.spec.js --project=chromium --project=firefox --reporter=line
56 passed (45.1s)
```

Focused resource/schema/static checks passed:

```text
.venv\\Scripts\\python.exe -m pytest tests/test_mcp_resources.py tests/test_static_pages.py tests/test_mcp_schemas.py -q
124 passed in 7.02s
```

Current normal visual fixtures were independently compared to fresh
`src.mcp_tools.call_tool(...).structuredContent.visual` results:

```text
district:   EQUAL=True
comparison: EQUAL=True
statewide:  EQUAL=True
```

The comparison output has finance periods 2025 and outcome periods 2024;
Dallas and Houston metrics carry their own populations. The package screenshots
were visually inspected: district and comparison images show the expected
content and the comparison image visibly shows separate 2025 finance groups and
2024 modeled-outcome group.

## Metadata criteria

| Criterion | Result | Evidence |
|---|---|---|
| MM-01 District population | **PASS** | Current adapter output gives all four Dallas metrics `Dallas ISD`; comparison gives Dallas/Houston their own names. The pure fallback helper yields `District 057905` for a valid six-digit ID and `District not reported` without usable identity. Statewide remains `Texas public school districts`. |
| MM-02 Consistent periods | **PASS** | `_metric` normalizes one period string and uses it for both display and source. Browser/schema checks and fresh fixture parity passed; known years remain strings and missing/null periods render `Not reported`. |
| MM-03 Independent missing status | **PASS** | Current adapter sets null/absent comparison gaps to `missing`, retains positive/negative/zero gaps as `modeled`, and keeps known outcome periods when value is null. Browser synthetic missing/negative/zero/mixed-period cases passed. |
| MM-04 Contract/source preservation | **PASS** | 124 focused tests passed, including strict schemas, current/historical responses, resources, and static checks. Full 56-case browser run passed. Fresh normal outputs equal fixtures and preserve values, years, units, denominators, sources, limits, and eleven-tool behavior. |
| MM-05 Captured visual evidence | **PASS locally** | Owner fixture recapture is now equal to actual tool transformations for all three normal calls; full Chromium/Firefox harness passed and the current package images show the corrected metadata. Actual ChatGPT host rendering remains separately unverified. |

## Package verification

```text
npm --prefix tests/plugin run validate -- ..\\..\\plugin
PASS: official Agent Plugins schemas, public endpoint, references, and skill

.venv\\Scripts\\python.exe -m pytest tests/test_plugin_package.py -q
2 passed in 3.18s
```

The package validator pins Agent Plugins `1.0.0` schema provenance to the
official URLs and matching SHA-256 hashes:

```text
https://agent-plugins.org/schemas/1.0.0/plugin.schema.json
0a4aad95ce337878ad38802ebf0daa3fde76abe3f65400c86bcbb1ec0b3ab883
https://agent-plugins.org/schemas/1.0.0/mcp.schema.json
6539175bfcdf43085855183e86da40ea94b166547a72b47ae9a0a390516d3acb
```

The validator checks the exact one-server mapping
`https://txisd.dev/mcp` with `streamable-http` and no headers, the trusted
creator mapping from `generated-package.json`, package-relative asset paths,
two declared screenshot references, icon/logo assets, and district-report
skill frontmatter. The two package tests begin each negative candidate from a
known valid copied package, validate that baseline, then independently reject
fabricated ID, bad endpoint, missing asset/reference, authorization headers,
unsupported manifest field, and traversal mutations. This prevents a negative
result caused by an already-invalid candidate. The package contains exactly
the declared `icon.svg`, `district-report.png`, and `comparison.png` assets.

### Missing-validator dependency proof

I copied `validate.mjs`, its cached schema/provenance files, and a valid
package candidate into `C:\Users\gsanc\AppData\Local\Temp\txisd-package-validator-missing-20261007`,
outside any `node_modules` ancestor, then ran Node against that isolated
candidate. It failed with an actual nonzero result:

```text
Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'ajv' imported from ...\\txisd-package-validator-missing-20261007\\validate.mjs
MISSING_VALIDATOR_EXIT=1
```

There was no parse-only fallback or fabricated PASS. The ordinary validator
run remains PASS when its pinned AJV dependency is available.

| Package gate | Result |
|---|---|
| Official schema URL/version/hash and exact trusted identity | **PASS locally** |
| Exact server, no-auth endpoint and valid copied candidate | **PASS locally** |
| Path traversal, unsupported field, missing asset, auth, fabricated ID negatives | **PASS** |
| Declared assets and skill frontmatter | **PASS** |
| Actual ChatGPT install/rendering | **UNVERIFIED** |
| Independent public installation/listing | **UNVERIFIED** |

### Current package image evidence

The package PNGs were inspected directly after the current adapter/fixture
update. Current metadata and hashes are:

```text
district-report.png  77,827 bytes  LastWriteTimeUtc 2026-10-07 22:27:31Z
SHA256 8B5B811696C99ABF4C4E9E1A7B3CEFFC5BB386B065FECBA9E5077B7DDA5B0BB6
comparison.png       87,038 bytes  LastWriteTimeUtc 2026-10-07 22:27:53Z
SHA256 4347DEAF64087FED44494A3B33353CC81C43EA11700F8A17D0CF8BC0C5C142D6
```

The source code used for current metadata behavior is `src/mcp_apps.py`,
SHA-256 `4D39DDD25ED3709265ACABFC87228AB87136740899F53804D045F8C7670B656E`;
the browser source is `tests/browser/mcp-app.spec.js`, SHA-256
`C4608EA48BD1D19D97097CF521BECB6D5290B2EBA5B2540E2FB0DA3812304470`.
Direct visual inspection shows the district image's Dallas identity and 2025
finance content, while the comparison image shows Dallas/Houston, finance
groups at 2025, and the modeled outcome group at 2024. The district PNG does
not expose metric population text in its captured viewport, so corrected Dallas
population is proven by fresh tool/fixture equality and browser assertions,
not claimed from pixels that do not display it.

## A-ENC-01 independent verification

The full dictionary test file now contains eight tests and passed in both
Windows modes:

```text
PYTHONUTF8 unset:  .venv\\Scripts\\python.exe -m pytest tests/test_data_dictionary.py -q
8 passed in 0.99s

PYTHONUTF8=1:     .venv\\Scripts\\python.exe -m pytest tests/test_data_dictionary.py -q
8 passed in 1.19s
```

The adversarial coverage includes non-ASCII UTF-8, LF/CRLF canonical byte
metadata, current working-file reflection, invalid UTF-8 rejection, and a
mini isolated builder generation proving canonical UTF-8/LF output and changed
working inputs. **A-ENC-01: PASS.**

## External limits

CP-06/E-BRIDGE local fixture, resource, CSP, and browser evidence now pass;
the companion E1 report was updated accordingly. Actual ChatGPT host rendering,
fresh supported-channel installation, independent public listing, and the
widget 95/5 painted-mark gate remain UNVERIFIED. No implementation, source
artifact, production, deployment, or host state was changed.
