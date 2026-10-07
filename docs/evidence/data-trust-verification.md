# Data-trust independent verification — 2026-10-07

Fresh Luna verification of the saved working tree at `37ec5d2` (working tree
contains Terra and other owner changes). This report is read-only evidence; no production DSN
or production SQL was used. PostgreSQL binaries were checked from the
disposable harness locations: PostgreSQL 18.3/current and PostgreSQL 17.11 at
`_audit_tools/pg17/pgsql/bin`.

The dedicated command was rerun with `.venv\Scripts\python.exe` and
`PG_BIN=C:\Users\gsanc\.codex\.chatgpt-projects\g-p-6aa23b54aca481919d6bea38fe3e3128\_audit_tools\pg17\pgsql\bin`.
It selected PostgreSQL 17.11, ran three tests, and exited 0:
`3 passed in 1.15s`; the owned cluster teardown also reported success. The
tests prove the 12-column wrong-arithmetic start, corrected 30-column view,
post-commit 30-column old-arithmetic recovery, and repair reapplication. They
do not prove the full T2 matrix described below.
The full locked suite was intentionally left pending during this focused T2
verification because other owners were changing UI/MCP/data files.

| ID | Result | Independent evidence and exact gap |
|---|---|---|
| A-DB-01 | FAIL | The PG17.11 run uses an isolated loopback cluster and reports successful teardown, but the harness has no injected-failure cleanup case and does not prove wrong-major rejection as a test. |
| A-DB-02 | FAIL | The PG17 tests create only a 12-column starting view, then prove one corrected 30-column result. There is no already-30-column starting state, catalog snapshot of summary OID/owner/options/grants, or dependent matview OID/definition/index/grant comparison. |
| A-DB-03 | FAIL | PG17 proves Dallas final values `23746.63` and `13529.52` plus null/zero denominator safety after repair. The test does not independently derive Decimal expectations for every fixture/synthetic positive case; the fixture has only one positive Dallas row and three nonpositive rows. |
| A-DB-04 | FAIL | PG17 proves post-commit recovery retains 30 columns and the summary OID, then permits repair reapplication. It does not test second-application semantic/data/ACL identity, injected transaction failure rollback, matview contents/identity rollback, or catalog/grant snapshots. |
| A-DB-05 | FAIL | The only database test checks one `has_table_privilege` result after a local fixture. The SQL/test files do not prove all five public projections, denied base reads/writes, effective NLP restrictions, or idempotent PR #78 grant repair. |
| A-DB-06 | FAIL | `scripts/verify_finance_contract.py` checks only column count, denominator nullability, latest-year arithmetic, and matview existence. It does not inspect types, effective privileges, enrollment exception reporting, public aggregate-only evidence, or anomaly defects beyond a generic deferred line. |
| A-SCOPE-01 | PASS | Bootstrap `sql/create_tables.sql:88` contains the planned initial-schema `DROP MATERIALIZED VIEW IF EXISTS`; this is distinct from production reconciliation. `sql/reconcile_finance_summary.sql` and `sql/recover_finance_summary.sql` contain no DROP/CASCADE, and the only live existing-object replacement is the explicitly `--apply` guarded T3b Python path. `sql/reconcile_anomaly_flags.sql` remains a rollback-only placeholder. |
| A-ANOM-01 | FAIL | `scripts/reconcile_anomaly_flags.py` inventories only non-internal `pg_depend` rows on the relation. It does not inventory row/array types, functions/rules/extensions/constraints, comments, reloptions/tablespace, grant options, default privileges, or reject reviewed-snapshot drift. The SQL transition is commented out. |
| A-ANOM-02 | FAIL | No A-ANOM threshold fixtures (84/85 revenue, 121/120 spend, delta 9/10), null/zero cases, independent arithmetic, per-student preservation, or idempotent reapplication tests exist. |
| A-ANOM-03 | FAIL | No injected failures after DROP/CREATE/restoration/assertions, OID/index/grant rollback assertions, or guarded post-commit recovery tests exist. The Python apply path has no explicit failure injection or captured metadata restoration. |
| A-PG17-01 | FAIL | PostgreSQL 17.11 is available and the dedicated harness passed 3 focused tests with teardown. The required full summary/grants/anomaly/recovery harness is not present: the current module contains only the three summary/recovery/anomaly-transition tests and omits the catalog, ACL, rollback-injection, and dependency matrix. |
| A-ART-01 | FAIL | Required `tests/test_verify_artifacts.py` is absent (focused command reports file not found). `scripts/verify_artifacts.py` has encoding/error handling changes, but no independent coverage for both separators, dependency cascades, traceback/nonzero failures, or both Windows modes was verified. |
| A-ENC-01 | FAIL | The builder uses explicit UTF-8 and LF normalization, but `uv run --locked --no-sync python -m pytest tests/test_data_dictionary.py tests/test_static_pages.py -q` produced 113 passed and 1 failure: committed `docs/DATA_DICTIONARY.md` is stale (78 vs fresh 79 routes). |
| A-ENC-02 | UNVERIFIED | Focused dictionary/static tests have the failure above. A final full-suite run is pending current owner changes; the prior 1,169-pass/32-skip Windows baseline remains distinct from this current final gate. Repository `.venv\Scripts\ruff.exe check .` currently reports owner-scoped visual/MCP lint errors, which are outside this T2 verification. |
| A-CI-01 | UNVERIFIED | No Linux CI result at this exact implementation revision was present in the inspected tree or produced during this verification. |
| A-SOURCE-01 | PASS | `docs/evidence/source-refresh.json` parses and records identity, checked UTC date, disposition, evidence/follow-up for the seven requested signals plus BLS and unpublished-product statuses; `docs/SOURCE_REFRESH_REVIEW.md` states no served artifact/vintage changed. Open/unresolved dispositions remain explicit rather than being treated as refresh passes. |

Additional command evidence from the earlier independent pass: `python
scripts/check_static_js.py` passed 14/14 pages. No full-suite result is claimed
in this focused T2 pass.

Priority repair sequence for Terra: expand the contract fixture to an already-
30-column start and add all rollback/catalog/grant/OID assertions; then rerun
the full Windows checks after the other owners finish.
