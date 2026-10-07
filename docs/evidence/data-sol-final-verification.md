# Final independent data-trust verification

Date: 2026-10-07

Verifier: fresh read-only Luna pass
Revision: `0c0c0f36af91a43203a3d4160089eae085df42d4` (`0c0c0f3`) with working-tree changes. No source, SQL, production, or served-data files were changed by this verification; only this evidence file was added.

## Evidence boundary and commands

The disposable harness used the repository `.venv` and explicitly selected PG17.11 binaries at `C:\Users\gsanc\.codex\.chatgpt-projects\g-p-6aa23b54aca481919d6bea38fe3e3128\_audit_tools\pg17\pgsql\bin`:

```text
.venv\Scripts\python.exe scripts\run_finance_contract_tests.py --pg-bin C:\Users\gsanc\.codex\.chatgpt-projects\g-p-6aa23b54aca481919d6bea38fe3e3128\_audit_tools\pg17\pgsql\bin
finance contract harness: PostgreSQL 17 development target
....                                                                     [100%]
4 passed in 34.39s
.............................                                            [100%]
29 passed in 12.08s
finance contract teardown: owned cluster removed
```

The 4 runner self-tests cover mixed/unparseable versions, wrong requested major, injected test failure, injected skip, and cleanup. A direct wrong-major run (`--expected-major 18`) exited 1 with “selected binaries report 17” and created no cluster. No production DSN or installed service was used.

The focused artifact/provenance/dictionary/static run was:

```text
.venv\Scripts\python.exe -m pytest tests/test_verify_artifacts.py tests/test_provenance.py tests/test_data_dictionary.py tests/test_static_pages.py -q
144 passed, 6 skipped in 3.90s
```

The 10 artifact tests include both default and inherited `PYTHONUTF8=1` zero-check cases. `scripts/verify_artifacts.py` was run in both modes. Each enumerated all 7 chain entries as `UNVERIFIED` and ended with `NOTHING WAS VERIFIED`; neither run reported a false clean result. The six focused skips are existing static-page environment skips and do not affect A-ART-01.

Selected working-input SHA-256 values were:

```text
scripts/run_finance_contract_tests.py  F6AC0DF01B7BDD55A62E79B37D9097D8121EC01FF437155FB4E3B3BA27EB09EE
scripts/reconcile_anomaly_flags.py    8CDC66F71AE0379A7A397767C2B67E803E4EE3696EFCAF6FEA1D126A4388F99E
scripts/verify_finance_contract.py     845F26CCE78002353B1337355DDEBF488EA87ACC9DC6C9BBF918946250E00C90
scripts/verify_artifacts.py            15FC5A98F08C90E1DAF313182E12361E274A80AD943A94AC2DFFE9017D92FD34
sql/reconcile_anomaly_flags.sql        E3F93C09874EA5E92372286A2FC8DAEC0FAC6C26CDF6B53EC087157585BA831F
tests/test_finance_contract.py         9AE817357B1B5B5428ED1C6C23F72BEF9CBBF6B3C2D7049425C785ED301E9191
tests/test_finance_contract_runner.py  8B5F2493CCA1E6774BA4C79EE480915E4092F28EE6A6F4E2E56CB6007070381B
tests/test_verify_artifacts.py         62B21AA8174832E472BDDC8EA5BAEA2CFB4BD429B28AA1AD4EAF621DB5BB48F3
```

## Acceptance results

| ID | Result | Concrete evidence |
|---|---|---|
| A-DB-01 | **PASS** | PG17.11 selected explicitly; all four binaries are major-checked. The 4 runner tests reject wrong/mixed versions, reject skipped integration tests, and prove cleanup after injected failure. Full run was 29/29 with owned-cluster teardown. |
| A-DB-02 | **PASS (preserved)** | Prior independent T2 evidence in `docs/evidence/t2-sol-verification.md`; the new full run retained the 12/30 contract tests and passed them. |
| A-DB-03 | **PASS (preserved)** | Prior T2 evidence proves independent `Decimal` arithmetic, Dallas FY2025 `23746.63` spending/student and `13529.52` revenue/student, and NULL for zero/negative/NULL enrollment; retained by the 29-test run. |
| A-DB-04 | **PASS (preserved)** | Prior T2 evidence proves idempotent reapplication, injected summary rollback, post-commit 30-column recovery, and corrected reapplication; retained by the 29-test run. |
| A-DB-05 | **PASS** | Live PG17 test applies the PR #78 ACL repair twice from permissive grants, checks all five projections for row-count coverage and effective SELECT-only access for `anon`/`authenticated`, denies all base-table privileges and schema CREATE, and verifies `nlp_reader` can read only summary/anomaly. |
| A-DB-06 | **PASS** | Verifier tests cover exact full 30-column names/types, broken grants, latest-year arithmetic, enrollment exception counts, deferred anomaly status, read-only behavior, and a DSN containing password/user/database/application-name secrets; no component appears in output. |
| A-ANOM-01 | **PASS** | PG17 tests cover v2 snapshot identity/OIDs/xmin, relation/rowtype/array dependency rejection before DROP, security-label and column-ACL rejection, comments/default ACL/grant-option restoration, held `AccessExclusiveLock`, and explicit maintenance acknowledgement. The implementation uses plain restrictive DROP without CASCADE. |
| A-ANOM-02 | **PASS** | Independent `Decimal` fixtures assert revenue 84 flags/85 does not, spend 121 flags/120 does not, enrollment delta 9 qualifies/10 does not, NULL/zero previous values are safe, and preserved per-student/enrollment flags remain correct. Fresh corrected snapshot reapplication is an exact OID/data/metadata no-op. |
| A-ANOM-03 | **PASS** | Five in-transaction fault points (`after_lock`, `after_drop`, `after_create`, `after_restore`, `after_assertions`) restore old OIDs/rows/ACLs/indexes. Two-connection tests cover reader contention, advisory-tool serialization, reads and late dependency blocked behind the exclusive lock, and owner drift committed while waiting. Committed receipt recovery guards current OIDs, restores old semantics with new OIDs, and permits repair reapplication. An independent `reviewed_definition_pair` probe rejected an arbitrary receipt definition containing `DROP TABLE` (`False`); no SQL was executed. |
| A-PG17-01 | **PASS** | The complete summary/grants/anomaly/recovery harness passed on actual PG17.11: 29 tests plus 4 runner self-tests, with teardown. This certifies the disposable harness only; it is not production application evidence. |
| A-ART-01 | **PASS** | All 10 artifact tests passed, including separator variants, dependency cascades, genuine traceback/builder failure, byte drift, `--update` failure, child UTF-8 controls, and both Windows encoding modes. Actual 7-chain runs reported `UNVERIFIED`/`NOTHING WAS VERIFIED` because raw inputs are absent. |

## External gates and limits

This is Windows-local disposable-database evidence. It does not certify the production target, deployment, source refresh, real participant gates, Linux CI, or the separate ENC/CI acceptance IDs. The raw artifact sources were absent, so the seven artifact chains remain unverified by design. No production SQL, database, deployment, or source ingestion action was performed.
