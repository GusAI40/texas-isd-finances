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
loopback-only PostgreSQL 17.11 harness passed nine tests covering both starting
states, identical second application, failure injection after replacement and
refresh from each state, recovery and reapplication, and pre-mutation rejection
of unexpected view shape, view type, and base type. The owned cluster was removed
successfully. This is local execution evidence only; no production SQL was run.

The anomaly materialized view's revenue/spend ratio formulas require the
separately guarded consumer transition; summary success alone does not certify
anomaly flags.

`scripts/reconcile_anomaly_flags.py` supplies that separate transition. Its
default inspection writes a deterministic, digest-bound catalog preimage. Apply
or recovery requires the preimage and an explicit maintenance-window statement,
then uses a transaction advisory lock and the supported same-owner materialized
view action to hold `AccessExclusiveLock` before a fresh drift check. Replacement
uses a plain `DROP MATERIALIZED VIEW` without `CASCADE`, recreates only the two
numeric numerator expressions, restores the reviewed owner/options/comments,
indexes and effective grants, and rolls the entire transaction back on error.
This has been exercised only in the disposable PostgreSQL 17.11 harness; it is
not evidence that the production target has been transitioned.

`scripts/verify_finance_contract.py` is a separate read-only checker. It obtains
its DSN only through the named environment variable, opens a bounded read-only
transaction, and reports the five public objects, exact summary prefix types,
effective public/NLP grants, denominator exceptions, and latest-year arithmetic.
It deliberately labels anomaly ratio repair as deferred until the guarded
consumer transition is verified on the release target.
