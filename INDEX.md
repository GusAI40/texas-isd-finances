# Texas ISD Finances documentation index

This is the short route through the public-data portal documentation. It does not replace the generated field dictionary or source register.

| Start here for | Document |
|---|---|
| Dated audit: evidence, defects, and unknowns | [Audit](docs/AUDIT_2026-10-07.md) |
| Ordered work before UI or plugin changes | [Visual/plugin execution plan](docs/VISUAL_PLUGIN_EXECUTION_PLAN.md) |
| Testable database repairs and recovery | [Data integrity plan](docs/DATA_TRUST_IMPLEMENTATION_PLAN.md) |
| Exact release revision, passing checks, and pending external gates | [Release evidence](docs/RELEASE_EVIDENCE.md) |
| Safe finance migration and recovery instructions | [Finance reconciliation runbook](docs/FINANCE_SUMMARY_RECONCILIATION.md) |
| Measured 95% visual / 5% prose rule | [Visual implementation plan](docs/VISUAL_IMPLEMENTATION_PLAN.md), [design contract](docs/VISUAL_DESIGN_CONTRACT.md) |
| Honest historical and prototype visual evidence | [Evidence scope refinement](docs/VISUAL_EVIDENCE_REFINEMENT.md) |
| Fully populated report composition under the unchanged 95/5 rule | [Populated-report refinement](docs/POPULATED_REPORT_95_REFINEMENT.md) |
| Financial framing and keyboard/map repairs | [Framing refinement](docs/FRAMING_TEST_REFINEMENT.md), [workflow repair refinement](docs/PUBLIC_WORKFLOW_REPAIR_REFINEMENT.md) |
| ChatGPT connection, visual resource, and portable package | [Plugin implementation plan](docs/MCP_PLUGIN_IMPLEMENTATION_PLAN.md), [ChatGPT guide](docs/CHATGPT_PLUGIN.md) |
| Downloadable plugin and archive integrity | [Portable ZIP](docs/artifacts/texas-isd-finances-plugin.zip), [archive validation](docs/evidence/mcp/portable-archive.json) |
| Captured source hashes across Windows/Git line endings | [Hash provenance](docs/evidence/end-of-line-provenance.md) |
| Finance and outcome periods in district comparisons | [Source-period refinement](docs/COMPARISON_PERIOD_REFINEMENT.md), [independent checks](docs/evidence/mcp/comparison-period-verification.md) |
| Metric periods, populations, missing values, and plugin package checks | [Metadata refinement](docs/METRIC_METADATA_REFINEMENT.md), [independent checks](docs/evidence/mcp/metadata-package-independent-verification.md) |
| Reviewed source refresh findings | [Source refresh review](docs/SOURCE_REFRESH_REVIEW.md) |
| Plain-language concepts and comparison rules | [Dictionary](DICTIONARY.md) |
| Libraries, services, tools, protocols, and sources | [Third-party services](THIRD_PARTY_SERVICES.md) |
| Every generated field and route | [Generated data dictionary](docs/DATA_DICTIONARY.md) |
| Source, publisher, vintage, and measure authority | [Source register](src/sources.py) |
| Public MCP tool contract | [MCP guide](docs/MCP.md) |
| Architecture and stack evidence | [Technology stack guide](docs/TECH_STACK_AND_AGENT_SKILLS.md) |
| Dated decisions and corrections | [Engineering log](docs/ENGINEERING_LOG.md) |
| Deployment safeguards and live-release procedure | [Deployment guide](DEPLOYMENT.md) |
| Public/API/MCP usage paths | [Usage guide](docs/USAGE.md) |
| Repository orientation | [README](README.md), [project map](PROJECT_MAP.md), and [agent guide](AGENTS.md) |

The portal is for parents, taxpayers, and the general public. A number must retain its source, fiscal year, denominator, and limitation wherever it is shown.

The dated audit records the baseline. Execution evidence is kept separately under `docs/evidence/`: database verification, visual measurements, and real ChatGPT/Inspector results. A connected development plugin is distinct from a publicly reviewed listing. Missing participant, screen-reader, source-rebuild, or release evidence must remain explicit rather than becoming a certification.
