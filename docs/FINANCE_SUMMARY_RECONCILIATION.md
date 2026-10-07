# Finance summary reconciliation

`sql/reconcile_finance_summary.sql` is an additive, target-verified repair for
the two per-student calculations in `public.v_finance_summary`. It accepts only
the captured 12-column public prefix or the declared 30-column extension, with
the exact names, order, and types. It also requires every referenced base column
with its captured type and the known materialized-view dependency before making
any change. Unexpected shape, type, option, or dependency state aborts before
replacement.

The replacement retains the summary OID, owner, supported security/check
options, and grants. It appends the declared 18 columns when starting from the
captured 12-column view. The transaction refreshes `public.v_anomaly_flags` while
retaining that object's OID, owner, options, definition, grants, and index OIDs,
then reloads PostgREST only upon commit. Base rows, roles, and the deferred
anomaly ratio formulas are unchanged.

There are three distinct rollback actions:

1. An application rollback changes only the application release. The additive
   30-column database contract remains compatible and should not be shrunk.
2. A failure inside the reconciliation transaction rolls back the view
   replacement and materialized-view refresh together. PostgreSQL restores the
   exact 12- or 30-column pre-transaction definition, contents, identities,
   options, grants, and indexes.
3. After a successful commit, `sql/recover_finance_summary.sql` is a separate,
   never-automatic incident action. It retains all 30 fields and both object
   identities and restores the documented old integer arithmetic. This is a
   compatibility recovery with known-wrong calculations, not a correctness
   repair. Reapplying reconciliation restores correct decimal arithmetic.

The disposable contract fixture records the captured 140-column production base
catalog, five public sample rows, and clearly labeled positive, zero, negative,
and NULL-enrollment synthetic cases. Expected values are calculated independently
with Python `Decimal` and two-place rounding. On 2026-10-07 the dedicated,
loopback-only PostgreSQL 17.11 harness passed four runner self-tests and 29
finance integration tests. The runner checks exact binary-major agreement,
rejects wrong and unparseable versions and skipped integration tests, and proves
owned-cluster cleanup after successful, failed, and skipped test runs. The
finance tests cover both starting states, identical second application,
transactional failure and post-commit recovery, complete public/NLP effective
access, verifier failures, and the anomaly transition cases described below.
The final owned cluster was removed successfully. This is local execution
evidence only; no production SQL was run.

The anomaly materialized view's revenue/spend ratio formulas require the
separately guarded consumer transition; summary success alone does not certify
anomaly flags.

`scripts/reconcile_anomaly_flags.py` supplies that separate transition. Its
default inspection writes a deterministic, digest-bound catalog preimage with
relation, row/array type, column, index, rule, dependency, default-privilege,
security-label, comment, ACL/grant-option, target-identity, and tuple-version
metadata. Apply requires that preimage and an explicit maintenance-window
statement, then uses a transaction advisory lock and the supported same-owner
materialized-view action to hold `AccessExclusiveLock` before a fresh drift
check. Unsupported metadata or relation/type/array dependencies are rejected
before DROP. Replacement uses plain `DROP MATERIALIZED VIEW` without `CASCADE`,
recreates only the two numeric numerator expressions, restores the reviewed
metadata, indexes and effective grants, and rolls the entire transaction back
on error.

A successful apply writes a separate digest-bound committed receipt containing
both the old preimage and freshly captured replacement state. Guarded recovery
accepts that receipt, requires the current replacement OIDs and catalog to match
its committed half, verifies that the two definitions form the reviewed repair
pair, and only then restores the old semantics with explicitly new OIDs. An old
preimage cannot authorize recovery against a replacement object. PostgreSQL
17.11 tests cover every injected failure point, corrected-state no-op, threshold
boundaries, NULL/zero inputs, comments/default privileges/grant options,
relation/rowtype/array dependencies, reader and tool contention, late consumers,
wait-time owner/xmin drift, guarded recovery, and repair reapplication. This is
not evidence that the production target has been transitioned.

The v2 command sequence uses an environment-variable name for the DSN and two
different files for the two different authorities:

```powershell
python scripts\reconcile_anomaly_flags.py --dsn-env FINANCE_TARGET_DSN --inspect `
  --snapshot anomaly-flags-preimage.json
python scripts\reconcile_anomaly_flags.py --dsn-env FINANCE_TARGET_DSN --apply `
  --snapshot anomaly-flags-preimage.json --receipt anomaly-flags-committed-receipt.json `
  --maintenance-window "approved-window-id"
python scripts\reconcile_anomaly_flags.py --dsn-env FINANCE_TARGET_DSN --recover `
  --receipt anomaly-flags-committed-receipt.json `
  --maintenance-window "approved-incident-window-id"
```

Run a new inspection before an idempotence check or repair reapplication. The
preimage has `kind: anomaly-preimage`; the apply output has `kind:
anomaly-transition-receipt` and contains separately digested `preimage` and
`committed` snapshots. Recovery rejects a preimage passed in place of a receipt,
a receipt for different current OIDs or target identity, and any pair whose
definitions or metadata differ beyond the reviewed two-expression transition.

`scripts/verify_finance_contract.py` is a separate read-only checker. It obtains
its DSN only through the named environment variable, opens a bounded read-only
transaction, and reports the five public objects, all 30 exact summary names and
types, the anomaly dependency, explicit effective privilege matrices, schema
CREATE denial, enrollment-exception counts, and per-district latest-year
arithmetic. Connection failures expose only the exception class, never DSN
components. The anomaly status is reported separately as either corrected or
deferred, so a summary/access pass cannot imply an anomaly repair.
