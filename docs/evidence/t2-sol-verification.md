# T2 independent verification — A-DB-02/03/04

Date: 2026-10-07
Verifier: fresh Luna pass
Scope: `sql/reconcile_finance_summary.sql`, `sql/recover_finance_summary.sql`,
`tests/test_finance_contract.py`, and `tests/fixtures/finance_contract.json`.

## Execution evidence

The dedicated disposable harness was run from the repository using the
repository `.venv` Python and the explicitly selected PostgreSQL 17.11 binary
directory:

```text
PG_BIN=C:\Users\gsanc\.codex\.chatgpt-projects\g-p-6aa23b54aca481919d6bea38fe3e3128\_audit_tools\pg17\pgsql\bin
.venv\Scripts\python.exe scripts\run_finance_contract_tests.py
```

Observed result:

```text
finance contract harness: PostgreSQL 17 development target
.........                                                                [100%]
9 passed in 3.23s
finance contract teardown: owned cluster removed
```

The four binaries independently reported PostgreSQL 17.11 (`postgres`,
`initdb`, `pg_ctl`, and `psql`). No production DSN or production SQL was used.

## Acceptance results

### A-DB-02 — PASS

`test_both_starting_contracts_reconcile_and_reapply_identically` runs for both
`starting_columns = 12` and `30`. It verifies the captured base catalog, then
checks the resulting 30 summary columns against the exact expected names and
types. The pre/post snapshots compare summary and anomaly OIDs, owners,
reloptions, ACLs, and anomaly index OIDs/definitions. The test also checks
unchanged non-derived summary values and anomaly row identity. The SQL source
uses `CREATE OR REPLACE VIEW` and only `REFRESH MATERIALIZED VIEW` for the
dependent anomaly object; it contains no anomaly `CREATE`, `DROP`, or
`CASCADE`, consistent with preserving its definition and identity.

Concrete source/test references: `tests/test_finance_contract.py:267-308`,
`:345-382`; `sql/reconcile_finance_summary.sql:93-118`.

### A-DB-03 — PASS

`assert_correct_arithmetic` independently converts fixture integers to
`Decimal`, divides before quantizing to two places with `ROUND_HALF_UP`, and
compares every captured and synthetic row to the live view. It explicitly
asserts Dallas FY2025 as `(Decimal("23746.63"), Decimal("13529.52"))`.
The fixture includes five public samples plus synthetic positive, negative,
zero, and NULL enrollment rows. The expected function returns `(None, None)`
for NULL or nonpositive enrollment, so these cases prove NULL output without
division errors or zero substitution.

Concrete source/test references: `tests/test_finance_contract.py:311-342`,
`:345-378`; `tests/fixtures/finance_contract.json` (`rows` and
`synthetic_rows`).

### A-DB-04 — PASS

The same test applies reconciliation twice and asserts the complete second
snapshot equals the first corrected snapshot, proving no semantic, row, ACL,
OID, option, or index change on reapplication. The injected `SELECT 1/0`
after `REFRESH MATERIALIZED VIEW` is exercised from both 12- and 30-column
starts; after rollback, the complete snapshot equals the original snapshot.
The recovery test then verifies that post-commit recovery retains 30 columns,
identities, and metadata, restores the documented old integer results
`(23746, 13529)`, and permits corrected reapplication back to the Decimal
results. The recovery SQL is a separate transaction and contains no shrink to
the 12-column contract.

Concrete source/test references: `tests/test_finance_contract.py:380-431`;
`sql/recover_finance_summary.sql:1-75`; `docs/FINANCE_SUMMARY_RECONCILIATION.md`.

## Adversarial coverage and limits

The harness also passed pre-mutation rejection tests for an unexpected extra
summary column, an unexpected view year type, and an unexpected base year type;
each test confirms the full snapshot is unchanged after rollback. This is
supporting evidence for the fail-closed behavior used by A-DB-02/04.

The focused snapshot captures all relation metadata used by the implementation
(OID, owner, options, ACL, definition) and index metadata. Its
`object_metadata` assertion directly compares identity/options/ACL plus
indexes; the anomaly definition is additionally established by source
inspection because reconciliation issues only `REFRESH` and never recreates it.
This verification covers the requested T2 criteria only; it does not certify
the separately deferred anomaly ratio repair or any production target.
