# Remaining data trust verification

Date: 2026-10-07
Verifier: fresh read-only Luna pass
Revision inspected: `37ec5d23c7e8380531db7507bb15c3950ea1d9f1`
Scope: A-DB-01, A-DB-05, A-DB-06, A-ANOM-01, A-ANOM-02, A-ANOM-03,
A-PG17-01, A-ART-01, and A-ENC-01. No production database or application
write was performed.

## Execution evidence

The dedicated runner was executed with the repository virtual environment and
the explicitly selected PostgreSQL 17.11 binaries at
`C:\Users\gsanc\.codex\.chatgpt-projects\g-p-6aa23b54aca481919d6bea38fe3e3128\_audit_tools\pg17\pgsql\bin`:

```text
.venv\Scripts\python.exe scripts/run_finance_contract_tests.py
finance contract harness: PostgreSQL 17 development target
...........                                                              [100%]
11 passed in 7.31s
finance contract teardown: owned cluster removed
```

The focused artifact/dictionary/static command was also run:

```text
.venv\Scripts\python.exe -m pytest tests/test_verify_artifacts.py tests/test_provenance.py tests/test_data_dictionary.py tests/test_static_pages.py -q
140 passed, 6 skipped, 5 failed
```

The five failures are the existing `mcp-app.html` static-page expectations in
`tests/test_static_pages.py`; they are outside this data scope. The dictionary
subset alone was `5 passed`.

## Acceptance results

| ID | Result | Evidence and remaining gap |
|---|---|---|
| A-DB-01 | FAIL | `scripts/run_finance_contract_tests.py` does create an isolated loopback cluster, checks that all four selected binaries agree on major 17, and removes the owned cluster after the successful run. There is no injected-failure runner case and no test that selects/rejects a wrong-major binary; the accepted condition requires both. The only cleanup path exercised is the normal successful `finally` path. |
| A-DB-05 | FAIL | `scripts/verify_finance_contract.py:failures` checks all five named public objects with `has_table_privilege` for `SELECT`, checks combined base-table `SELECT,INSERT,UPDATE,DELETE`, and checks the two NLP reads. `tests/test_finance_contract.py:test_public_read_contract_and_readonly_verifier` manually checks only `v_spending_detail` for the API roles and one NLP denial. There is no independent five-projection row-coverage test, no explicit effective `INSERT/UPDATE/DELETE` matrix, no schema `CREATE` check, and no twice-applied PR #78 repair evidence. |
| A-DB-06 | FAIL | `scripts/verify_finance_contract.py` validates only the 12-column `SUMMARY_PREFIX` types and permits any 12/30 column count; it does not validate the 18 appended column names/types. It reports generic enrollment arithmetic violations and a deferred anomaly line, with no distinct enrollment-exception report. Its read-only transaction is useful evidence, but there is no test that attempts/guards schema `CREATE`, no exception-report test, and no test proving connection errors cannot disclose DSN/password components. |
| A-ANOM-01 | FAIL | `scripts/reconcile_anomaly_flags.py:capture` records relation/rowtype/array OIDs, `xmin`, relation metadata, columns, indexes, inbound `pg_depend` rows, relation grants, and enabled event triggers. It does not capture outgoing dependency/extension membership, functions/rules/constraints/comments beyond the limited relation/column/index fields, column grant options as a separate reviewed contract, or default privileges. `test_anomaly_transition_is_explicit_and_preserves_read_contract` exercises one successful PG17 apply and confirms the corrected definition and anon SELECT, but no fixtures reject those missing dependency/metadata cases or prove the pre-DROP rejection matrix. |
| A-ANOM-02 | FAIL | The harness has no revenue/spend threshold fixtures or independent anomaly arithmetic assertions. It applies the transition once and checks the corrected definition; it does not apply against a freshly inspected already-correct state and assert a no-op preserving OIDs/data/metadata, nor verify the original enrollment/per-student flag definitions. |
| A-ANOM-03 | FAIL | The 11-test run includes T2 summary rollback/recovery tests, but no T3b injected in-transaction failure, old anomaly object/data/ACL/index-OID rollback assertion, two-connection reader/tool contention test, wait-time drift rejection, or late registered dependency rollback. `scripts/reconcile_anomaly_flags.py` has no failure-injection or bounded-concurrency test hook. Post-commit recovery of the anomaly replacement is also absent. |
| A-PG17-01 | FAIL | Actual PostgreSQL 17.11 execution is proven by the dedicated runner (`11 passed`, teardown succeeded). The required full summary/grants/anomaly/recovery harness is not present: the current tests cover T2 plus one successful anomaly apply, and omit the catalog, default-privilege, rollback-injection, concurrency, and recovery matrix. Therefore PG17 is not a full acceptance pass. |
| A-ART-01 | FAIL | `tests/test_verify_artifacts.py` covers explicit `data\\` and `data/` missing-path classification, a genuine builder failure, byte drift, and `--update` nonzero behavior. It does not test the known dependency-cascade branch or both Windows encoding modes. The actual `scripts/verify_artifacts.py` run classified all seven missing-source/cascade results as `DRIFT` because builders emit `missing data\\...` rather than the `FileNotFoundError`/`No such file or directory` forms accepted by `is_known_missing_raw_input`; it did not produce the required UNVERIFIED result. |
| A-ENC-01 | FAIL | `scripts/build_data_dictionary.py` does use strict UTF-8 reads, CRLF/CR-to-LF normalization for byte counts, and UTF-8/LF writes. `tests/test_data_dictionary.py` has five structural/fresh-output tests and passed, but has no non-ASCII fixture, LF-vs-CRLF equivalence fixture, changed-working-input fixture, or invalid-UTF-8 failure fixture. Thus implementation clues exist, while the required encoding evidence is absent. |

## Verification boundary

No repair was made during this pass. The focused PG17 result supports the
previous T2 A-DB-02/03/04 evidence in `docs/evidence/t2-sol-verification.md`,
but it does not close the remaining criteria above. The five static-page
failures were observed and left untouched because they belong to the active
visual/MCP work and are outside this verification scope.
