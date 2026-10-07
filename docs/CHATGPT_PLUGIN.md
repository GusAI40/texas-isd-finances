# Texas ISD Finances: ChatGPT plugin and MCP access

The package is in [`plugin/`](../plugin/). MCP supplies eleven deterministic,
read-only public-data tools. The plugin adds instructions, presentation assets,
and the verified development registration mapping. An MCP App adds optional
district, comparison, and statewide visual reports; useful sourced text remains
available when a host cannot display the frame.

Download the complete [portable plugin ZIP](artifacts/texas-isd-finances-plugin.zip).
The [archive validation record](evidence/mcp/portable-archive.json) records its
exact hash and eight entries. The source and an independently extracted copy
both pass the official schema/reference validator. This is a distributable
package; actual host installation and directory approval are separate checks.

The connection is `https://txisd.dev/mcp`, using Streamable HTTP with no
authentication or API key. It does not expose the website's paid `/query` path,
database credentials, private operations, outreach, or student/personnel records.
[`MCP.md`](MCP.md) documents the exact tool list and protocol. Figures come from
committed public artifacts, with their own periods and limitations; they are
actuals, not live budgets. Finance and outcome years can differ.

## Package and validation

| File | Purpose |
|---|---|
| `plugin/plugin.json` | Agent Plugins 1.0.0 identity and OpenAI presentation settings. |
| `plugin/mcp.json` | The single public no-auth server. |
| `plugin/.app.json` | Exact creator-generated registration mapping, independently checked against saved host evidence. |
| `plugin/skills/district-report/SKILL.md` | Resolve ambiguous district names first, preserve six-digit IDs, and quote comparable sourced measures. |
| `plugin/assets/` | Project icon and actual local widget screenshots; these are not ChatGPT publication evidence. |
| `plugin/LISTING.md` | Purpose, examples, limitations, privacy and support materials. |

The development-only validator uses pinned AJV 8.20.0 and cached official
schemas. [`schema-provenance.json`](../tests/plugin/schema-provenance.json)
records version, URLs, and hashes. Candidate packages cannot replace the trusted
registration evidence. Missing dependencies, invalid schemas, escaping paths,
missing assets, changed identity, or authenticated/incorrect endpoints fail.

From the repository root on Windows:

```powershell
npm ci --ignore-scripts --prefix tests\plugin
npm --prefix tests\plugin run validate -- ..\..\plugin
.venv\Scripts\python.exe -m pytest tests\test_plugin_package.py -q
```

## Connection and installation checks

Use the current [official connection and testing guide](https://developers.openai.com/plugins/deploy/connect-chatgpt)
and [package guide](https://developers.openai.com/plugins/build/plugins).
Account/workspace eligibility applies. For a custom connection, select **Add
custom MCP server** in ChatGPT Plugins, enter this endpoint, and use **None**
authentication. For complete package testing, install from a local marketplace
in the supported Plugins Directory. Refresh the connection's metadata after an
authorized server update, then test in a new chat with the plugin selected.

Test Dallas `057905`, Houston `101912`, Tioga `091907`, and charter `003801`;
also test an ambiguous name, an unknown ID, and unsupported private/future-budget
questions. Check all eleven tools, leading zeros, absence reasons, periods,
sources, and limits. The three optional frames must show their actual values,
survive a district switch, and preserve useful text if unavailable. Confirm a
complete install has one intended tool set rather than duplicate connections.
Record host, exact server revision, package hash, date, selected tools and results.
Keep private chat/account details out of public evidence.

## Evidence and publication boundary

[`metadata-package-independent-verification.md`](evidence/mcp/metadata-package-independent-verification.md)
records local schema/package checks, actual tool-fixture parity, and 56 local
Chromium/Firefox bridge tests. [`generated-package.json`](evidence/mcp-host/generated-package.json)
records the actual creator export. Earlier owner-host evidence covers all eleven
tools at the recorded older production revision.

The registration is DEVELOPMENT. Local validation and a connected endpoint do
not establish a fresh complete install, new ChatGPT visual rendering,
independent-account access, or public-directory approval. Track those checks in
[`RELEASE_EVIDENCE.md`](RELEASE_EVIDENCE.md) and the
[`release matrix`](evidence/mcp/release-matrix.json). Public submission and
publication follow the [official review process](https://developers.openai.com/plugins/deploy/submission)
after release authority and actual host checks; no approval or universal account
availability is promised.

The complete archive was prepared and its development upload was attempted on
2026-10-07. The browser extension blocked `fileChooser.setFiles` because “Allow
access to file URLs” is disabled. That permission has not been changed; its
approval is pending. The upload did not succeed, so no new installed version is
claimed. This browser permission gate is separate from server deployment and
public-directory review.

Privacy: [website policy](https://txisd.dev/about#privacy). Sources:
[transparency](https://txisd.dev/transparency). Support:
[GitHub issues](https://github.com/GusAI40/texas-isd-finances/issues).
The widget itself adds no tracking or persistent storage. Hosting and ChatGPT
provider handling remain separate; no-auth does not mean there are no
infrastructure logs or provider retention.
