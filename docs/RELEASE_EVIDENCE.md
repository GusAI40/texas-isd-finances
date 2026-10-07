# Visual portal and ChatGPT plugin release evidence

This record separates implemented behavior, independently verified checks, and
external release gates. The audience is parents, taxpayers, and the general public.
The advertised design target is at least 95% meaningful visual content and at most
5% standalone prose, measured independently in the first viewport and full report.
Whitespace, decorative illustrations, and prose inside cards are excluded from
visual credit. Source years, units, model assumptions, and missing-data status stay
readable in the default report.

## Revision and release boundary

- Execution branch: `feat/visual-public-portal-plugin-20261007`; checkpoint
  `37ec5d23c7e8380531db7507bb15c3950ea1d9f1` is documentation/evidence only.
- Production observed on 2026-10-07: `73df1896ed0818020ec1c15c06f5ee823db7ec0f`.
  `/health` and `/stats` respond successfully. That is a health observation,
  not certification of all financial arithmetic or every user journey.
- Implementation changes are undergoing the repository's audit → plan →
  implementation → fresh independent verification process.
- No production finance migration or application release has been applied in
  this execution record yet. A preview deployment is separate from production.

## Evidence by capability

| Capability | Current evidence and remaining gate |
|---|---|
| Additive summary repair | [Fresh independent T2 verification](evidence/t2-sol-verification.md): A-DB-02/03/04 PASS; actual PostgreSQL 17.11, 9 tests, both 12/30 starting contracts, independent Decimal arithmetic, metadata/identity preservation, rollback, recovery and reapplication. This is local evidence; production application and the remaining grants/anomaly gates are separate. |
| Finance access and anomaly transition | [Fresh independent final verification](evidence/data-sol-final-verification.md): 29 integration and four runner checks PASS on actual PostgreSQL 17.11, including effective privileges, dependency guards, thresholds, contention, rollback, current-identity recovery and reapplication. Saved in `de49c2f6c21baf4e818c8be284deec8512e0a692`; production application remains separate. |
| Honest source freshness | [Source refresh review](SOURCE_REFRESH_REVIEW.md), [source ledger](evidence/source-refresh.json). Metadata changes alone did not change served vintages. Missing raw inputs and unresolved row/geometry comparisons remain explicit. |
| Actual 95/5 website | [Design contract](VISUAL_DESIGN_CONTRACT.md), [visual checks](evidence/visual/verification.md). Final first-viewport/full-report results and semantic screenshot review are required; a moved finder or a prototype does not prove the target. |
| Public workflows and accessibility | [Visual plan](VISUAL_IMPLEMENTATION_PLAN.md). Browser, keyboard, reflow, chart/source/table/export/map checks are distinct from ratio measurement. Actual assistive-technology and participant evidence cannot be replaced by DOM tests. |
| Public MCP tools | [Inspector responses](evidence/mcp-host/inspector-results.json), [11 actual owner-host normalized responses](evidence/mcp-host/connector-results.json), [exact portability warning](evidence/mcp-host/inspector-portability.json). These observations used the recorded older deployed revision; repeat against released code. |
| MCP success schemas | [Fresh independent schema verification](evidence/mcp/schema-sol-verification.md): D-SCHEMA-01 PASS locally, strict recursive AJV 8.20.0 validation of 11 current successes, 11 historical host successes, edge cases and invalid nested payloads. New deployed-host validation remains separate. |
| Comparison source periods | [Focused refinement](COMPARISON_PERIOD_REFINEMENT.md), [independent verification](evidence/mcp/comparison-period-verification.md): Dallas/Houston finance remains 2025; modeled outcome differences retain their actual 2024 source period. Optional/null/historical schema compatibility and invalid-year rejection pass. Local widget recapture is being verified separately. |
| Protected preview tools | [Actual authenticated HTTP results](evidence/mcp/preview-http-results.json): eleven public successes plus correct unknown-tool rejection at checkpoint `0c0c0f36af91a43203a3d4160089eae085df42d4`; all eleven actual outputs pass strict recursive AJV. This is application JSON, not an SSO login page; final-revision and actual ChatGPT checks remain separate. |
| Plugin package | [Portable ZIP](artifacts/texas-isd-finances-plugin.zip), [source/extracted archive validation](evidence/mcp/portable-archive.json), [fresh independent package/widget verification](evidence/mcp/final-widget-independent-verification.md). Eight entries and actual creator mapping pass official schemas. Development upload was attempted but Chrome blocks local-file access; permission approval is pending. Complete installation and public availability are not established. |
| Embedded ChatGPT visuals | [Fresh independent agent review](evidence/mcp/final-widget-independent-verification.md): all 36 district/comparison/statewide cells pass initial/full 95/5, with genuine iframe/document dimensions; 56 bridge/browser tests pass. Visible frame, scope, period and noncausal qualifiers remain. This is local sandbox evidence; actual new ChatGPT host rendering is UNVERIFIED. |
| Real public-reader study | [Participant protocol](PUBLIC_USABILITY_PROTOCOL.md), [study status](evidence/public-usability.json). No consenting participant sessions have been recorded; UNVERIFIED. |
| Public plugin directory | Review and independent eligible-account installation remain UNVERIFIED. Website access, a development connection, and a directory listing are distinct outcomes. |

## Controlled rollout and recovery

Verify Git authentication, the correct Vercel project/team, secret formatting,
persisted configuration, and database compatibility without printing credentials.
Rehearse SQL recovery on the disposable target major. Production summary repair
must preserve its OID and existing prefix; the separately guarded anomaly
replacement intentionally changes its OID. Code rollback does not reverse SQL.
Use the reviewed metadata snapshot and maintenance procedure in the finance
runbook; never run the bootstrap against an existing production database.

After an authorized release, record the exact 40-character revision, read-only
database verification, route/asset smoke checks, actual MCP/ChatGPT checks, and
application rollback result if needed. A proposed one-hour/24-hour observation
window has not elapsed and no new automation has been scheduled in this record.
Keep pending elapsed-time, review, account-eligibility, and human-study evidence
visible. Do not claim universally flawless behavior from a passing test suite.
