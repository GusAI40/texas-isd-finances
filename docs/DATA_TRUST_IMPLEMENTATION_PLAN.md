# Package A: executable data-trust refinement

**Date:** 2026-10-07. **Parent plan:** [Visual/plugin execution plan](VISUAL_PLUGIN_EXECUTION_PLAN.md).
**Execution branch:** `feat/visual-public-portal-plugin-20261007`, documentation base `2b59328`.
**Stage:** implementation is authorized; this artifact is planning only. This
refinement defines local code, tests, and evidence. Production SQL, merge, and
deployment remain separately controlled release actions, not planner actions.

## Objective and explicit boundaries

Produce a tested, additive repair for the public finance summary; portable,
truthful artifact verification and dictionary generation; and reviewed freshness
dispositions. Preserve existing public reads, restricted NLP access, database
object identity, and unrelated changes. Terra implements the bounded tasks below;
a fresh Luna independently evaluates each acceptance ID. A change to this plan,
acceptance criteria, or migration architecture returns to Astra before implementation.

The captured public fixture is `../execution-finance-inputs.json`: PostgreSQL 17
production catalog, 140 base columns/types, 12-column summary definition, anomaly
materialized-view definition, dependency list, Dallas FY2024/FY2025, and the three
nonpositive/null-enrollment rows (`101865`/2011, `123807`/2010, `061803`/2009).
Use that evidence, not reconstructed guesses. It contains no credentials; copy
only the necessary public catalog/sample subset into the owned test fixture.

**Anomaly decision:** targeted inspection confirms that `revenue_drop_flag` and
`spend_spike_flag` also divide bigint values before comparison. Correcting their
materialized-view definition is explicitly outside this additive summary repair.
PostgreSQL cannot `CREATE OR REPLACE MATERIALIZED VIEW`; changing it requires a
separate dependency/identity migration. T2 preserves its definition, OID, indexes,
and grants and refreshes corrected per-student inputs. The newly identified defect
is explicitly added as **T3b (A1b)** below, a separately tested consumer transition
under the user's full data-integrity scope. Record both flags as known defective
until that transition is tested and applied; T2 alone cannot certify them. Do not
change bootstrap anomaly formulas alone and imply production has been repaired.

## Ordered work and exact ownership

Execute T1 → T2 → T3 → T3b → T4 → T5. Root may perform T6's read/download investigation
concurrently, outside authoritative artifacts. T6 unresolved items do not block
independent design prototypes or read-only host probes; they gate affected data
freshness claims and release capabilities. Other agents are present: never revert
their changes or edit files outside the assigned task without coordination.

### T1 — Establish an actual PostgreSQL regression harness

**Owned paths:** `scripts/run_finance_contract_tests.py`,
`tests/test_finance_contract.py`, `tests/fixtures/finance_contract.json`.

Create a development-only runner that initializes a temporary PostgreSQL cluster,
loads the public fixture, runs the focused tests, and tears down its own cluster.
Use explicit `PG_BIN` and validate `postgres --version`, `initdb`, `pg_ctl`, and
`psql` come from the same major. This host's 17 directory contains debug symbols,
not a runnable server; runnable PostgreSQL 18.3 is available. Use 18.3 explicitly
for immediate development evidence and label that major accurately. Target-major
17 verification remains required before production application: obtain an isolated
17 binary distribution from the publisher-linked distribution with integrity
verification, or run the same harness in a verified PostgreSQL 17 CI environment.
Do not modify globally installed services or claim 18 results prove 17 execution.
Use standard-library process control and the existing psycopg2 dependency; no
new runtime package.

Bind only loopback on a checked unused high port, retry a port race with a new
owned cluster, and keep all data/logs/credentials in a unique temporary directory.
Use a temporary password and local SCRAM authentication; never a global service
or production DSN. Hide spawned Windows processes (`CREATE_NO_WINDOW` or hidden
`Start-Process`), enforce startup/shutdown timeouts, and record the owned directory,
port, and PID. Before cleanup, verify resolved paths are within the allocated
temporary root. Stop only via `pg_ctl -D <owned-directory>`; verify its PID/port
has stopped before deleting that directory. On cleanup failure retain the path
and report failure, rather than killing an arbitrary PostgreSQL process.

Construct both captured 12-column and legacy 30-column starting states. Establish
all five public finance objects with their reviewed schemas: summary, detail,
breakdown, anomaly matview, and district similarity. Use existing SQL for real
projections where available; seed required supporting columns/tables explicitly.
Create `anon`, `authenticated`, and `nlp_reader` only inside this cluster. Preserve
the production anomaly definition as a fixture, with its documented limitation.
Tests must independently derive expected arithmetic using Decimal/source values.

**Verification:** `uv run --locked --no-sync python scripts/run_finance_contract_tests.py`.
The runner must fail clearly when its explicitly requested major is unavailable
or any selected integration test is skipped. Ordinary pytest may mark this integration module
skipped when invoked without the dedicated harness; report that skip honestly.
First establish failing arithmetic/schema assertions against the captured state;
then use the same tests to prove T2. Capture teardown success even on test failure.

### T2 — Implement the additive summary repair and safe recovery

**Owned paths:** `sql/create_tables.sql`, `sql/reconcile_finance_summary.sql`,
`sql/recover_finance_summary.sql`, `tests/test_finance_contract.py`,
`docs/FINANCE_SUMMARY_RECONCILIATION.md`.

Change only the two summary per-student formulas in the bootstrap to cast the
numerator to numeric before division. Preserve NULL when enrollment is zero,
negative, or NULL. Add a separate reconciliation SQL file with explicit transaction,
bounded lock/statement timeouts, schema-qualified references, and fail-closed
preconditions. Accept the known 12-column prefix or declared 30-column contract
only: validate column names, order, and types, all required base columns/types,
and the known dependent anomaly matview. Unexpected shape must abort, not adapt
silently. `CREATE OR REPLACE VIEW` must retain the original 12-column order/types
and append exactly the 18 existing declared fields. Preserve view ownership,
security options, OID, and grants. Do not run the full bootstrap in production,
issue DROP/CASCADE, change `src/migrations.py`, alter base rows, or change security
mode to invoker.

In that same transaction refresh `public.v_anomaly_flags`, run contract assertions,
and notify PostgREST to reload its schema only upon commit. The refresh updates
dependent per-student results but does not repair the deferred ratio formulas.
Reapplication to an already-correct 30-column view must produce identical
definitions/data/access and preserve OIDs/indexes. Inject a failure after view
replacement and refresh in the test transaction and prove complete rollback.

Recovery has two different meanings: an uncommitted failure rolls back completely
to the 12- or 30-column starting state; post-commit recovery cannot shrink 30
columns to 12 using `CREATE OR REPLACE`. Provide a separately invoked, never
automatic recovery SQL that preserves all 30 fields, OIDs, dependencies, and
grants while restoring the prior two expressions and refreshing the matview in
one transaction. Label that exceptional recovery as restoring known old arithmetic,
not a correctness repair; it requires an incident decision. Test it and subsequent
reapplication of the corrected migration. The runbook must distinguish application
rollback, transaction rollback, and post-commit compatibility recovery.

**Verification:** rerun T1 with both starting states and each failure/recovery path.
Compare catalog snapshots, query results, grants, matview indexes, and row counts
before/after. No text-only SQL test or SQLite mock substitutes for execution.

### T3 — Reconcile the existing grants repair and expose read-only verification

**Owned paths:** `sql/harden_public_finance_read_contract.sql`,
`sql/test_public_finance_read_contract.sql`, `scripts/verify_finance_contract.py`,
`tests/test_finance_contract.py`, `docs/FINANCE_SUMMARY_RECONCILIATION.md`.

Bring the two reviewed SQL files from PR #78 into this branch, preserving attribution
and noting that the repair was already applied to production on 2026-09-15.
Do not merge that PR or reapply production SQL as part of this task. The repair
checks the five object kinds, removes broad public/API-role privileges, restores
SELECT for `anon`/`authenticated`, and enables the similarity SELECT policy. It
does not change NLP privileges. Execute it twice against the disposable database,
including a permissive legacy ACL fixture, before/after the additive migration.

Extend database tests to verify real SELECT coverage under each public role and
denied mutation/base reads. Verify `nlp_reader` reads only summary/anomaly within
the finance surface and cannot read the base or other three public projections;
preserve its other established restrictions. Assert no schema CREATE or public
mutation privilege is introduced. Check effective privileges, not ACL text alone.

Implement `verify_finance_contract.py` as a read-only catalog/math checker whose
DSN is obtained from an explicitly named environment variable, never an argument
value or printed log. Require a read-only transaction with statement timeout.
Report columns/types, dependencies, public/NLP effective privileges, enrollment
exceptions, and numeric mismatches for all eligible latest-year rows; store only
public aggregate/error evidence. Do not run mutation probes in this verifier;
those belong in the disposable integration tests. Identify deferred anomaly ratio
defects separately so a summary PASS cannot be read as whole-finance PASS.

**Verification:** T1 plus
`python scripts/verify_finance_contract.py --dsn-env FINANCE_VERIFY_DSN` against
the temporary database. With deliberately broken schemas/grants/math, require a
nonzero failure and useful diagnostics. Production use later is read-only and
must name/verify the correct target separately.

### T3b (A1b) — Repair anomaly ratios through an explicit consumer transition

**Owned paths:** `sql/create_tables.sql` (the two anomaly formulas only),
`sql/reconcile_anomaly_flags.sql`, `scripts/reconcile_anomaly_flags.py`,
`tests/test_finance_contract.py`, `docs/FINANCE_SUMMARY_RECONCILIATION.md`.

This is a distinct, bounded follow-on to additive T2/T3. The observed production
matview owner is `postgres`, with two known indexes and no dependent views.
That last observation is insufficient: inventory all incoming `pg_depend`
relationships to the relation, row type, and associated array type, including
functions/type consumers, rewrite rules, extension membership, constraints,
indexes, and other registered consumers. Classify intrinsic/internal dependencies
and the two captured indexes explicitly. Fail on every unexpected external
dependency; do not use CASCADE or silently expand the replacement graph. Record
name-based API/NLP consumers and prove their queries retain names/types/meaning.

Implement a read-only default inspection mode that captures the exact old
definition, column names/order/types, owner, reloptions/tablespace, effective ACLs
including grant options, comments, index definitions, and dependency inventory.
The separate apply mode must be explicitly selected and target-verified; this
task exercises it only on the disposable database. The supported transaction
protocol below replaces the original unsupported `LOCK TABLE` instruction.
After its locked reinspection succeeds, replace it using a plain targeted
`DROP MATERIALIZED VIEW public.v_anomaly_flags` without CASCADE, then recreate
the same name/column contract with only the two numerators cast before division.
Restore captured owner/options/ACLs/comments and both index definitions; revoke
any unintended default-privilege grants on the new object. Populate the matview,
run arithmetic/consumer/access assertions, notify PostgREST, and commit together.
Do not touch summary/base OIDs or rows. The matview/index OIDs intentionally
change on successful replacement; downstream references must be name-based or
the precondition must reject them.

Use strict current thresholds: revenue 100→84 flags, 100→85 does not; spend
100→121 flags with enrollment delta below 10, 100→120 does not; delta 9 qualifies
and delta 10 does not. Test NULL/zero previous values and preserve the existing
per-student/enrollment rules. Derive expected values independently, not from a
copy of the SQL expression. Fix the same two expressions in the bootstrap so new
databases match the migration.

Inject errors after DROP, after CREATE, and during restoration/assertions to prove
transaction rollback restores the original matview OID/data/index OIDs/grants.
After successful commit, recovery is another guarded transaction restoring the
captured old definition and metadata with new OIDs; it cannot promise the original
OID. Test that recovery, repair reapplication, and second apply as an idempotent
no-op when the correct definition/metadata already exist. An extra dependent view
and a composite-type consumer fixture must each cause precondition rejection
before DROP. Keep anomaly claims FAIL until the corrected definition is verified
in the actual release target; passing a local replacement test is not deployment.

**Verification:** dedicated PostgreSQL harness with `A-ANOM-*` cases, public-role
and NLP queries before/after, synthetic boundary cases, real Dallas samples, and
all rollback/recovery/dependency-rejection cases. Run on PostgreSQL 17 before
production application; 18.3 evidence may support development only.

#### T3b revision — supported PG17 locking and bounded concurrency

**Reason for revision:** independent PG17.11 and PG18.3 execution both reject
`LOCK TABLE` on a materialized view. Do not retry that statement, replace it with
an advisory lock alone, or refresh/discard the old data merely to obtain a lock.
Use the following precise protocol for apply and post-commit recovery; ownership
remains limited to T3b's existing files. No production application is authorized.

1. Inspection stays read-only. Save a versioned, deterministic JSON snapshot and
   digest, explicitly supplied back to apply, containing target identity (server
   endpoint/database and database OID, server major, and cluster identifier when
   accessible), relation/rowtype/array/index OIDs, and all metadata described
   above. Include relation `pg_class.xmin::text` as an additional drift token,
   column ACLs and grant options, relation/column/index/type comments, access
   method, populated state, and relevant default privileges. Include registered
   dependencies on each allowlisted internal object as well as the three root
   objects; do not whitelist every `i` or `a` dependency by category alone.
   Check extension membership in the outgoing direction too. Restore supported
   metadata or reject its nondefault presence explicitly before replacement;
   never silently omit it (including security labels or special column/index
   properties). Reject unreviewed DDL event triggers that could change the
   operation's effects. A capture is evidence, not executable arbitrary SQL.

2. Open one `READ COMMITTED` transaction, set local bounded lock, statement, and
   idle-in-transaction timeouts, and acquire a stable, documented
   `pg_advisory_xact_lock` key for this database/object name. All invocations of
   this tool, including recovery, use the same key before object locks. Verify
   target identity and compare the current snapshot to the supplied one; reject
   any drift or unexpected dependency. Quote identifiers through the database
   driver's identifier facility and bind data values. Do not interpolate owners
   or metadata into SQL using string formatting.

3. Execute `ALTER MATERIALIZED VIEW public.v_anomaly_flags OWNER TO <captured
   owner>` with the safely quoted captured owner. PG17's supported owner action
   acquires `AccessExclusiveLock`; its same-owner path leaves the object intact.
   Immediately assert in `pg_locks` that this backend holds that lock on the
   captured OID. Reinspect in a **new statement after the lock has been acquired**
   and compare the entire reviewed snapshot, including OIDs and `pg_class.xmin`.
   The xmin check is necessary: if ownership changed while waiting, the owner
   statement might otherwise restore the captured owner and conceal that drift.
   Any changed tuple token, identity, metadata, or dependency aborts the whole
   transaction, undoing that tentative owner action as well. Do not use a stale
   repeatable-read snapshot for this check. Do not release the lock through a
   savepoint rollback and continue. This step must be demonstrated on actual
   PG17; source inspection alone is not a passing execution result.

4. Only after successful reinspection may the existing plain, non-CASCADE DROP
   and recreation proceed. Keep the native restrictive DROP as a final dependency
   guard, even after the inventory passes. Any error, timeout, dependency race,
   failed restoration, or failed assertion rolls back the **entire** transaction;
   do not catch it and commit partial work. Restore exact allowed metadata and
   effective grants (including grant options), clearing unexpected grants from
   default privileges; validate public/NLP name-based queries and independent
   arithmetic before transactional notification and commit. Capture a committed
   result receipt separately from the preimage used for recovery. A newly
   inspected, already-correct object is an idempotent no-op only after all the
   same identity, dependency, metadata, and access checks; an old preimage is
   never silently accepted as authority for a different replacement OID.

**Guarantees and release constraint:** the relation lock waits for conflicting
readers and prevents ordinary relation reads/refreshes/DDL from interleaving
with replacement. The transaction exposes no committed half-replacement. It
does not promise uninterrupted requests: queued or cached-OID queries may
require normal client retry after replacement. The advisory lock serializes
cooperating migration tools only. It does not freeze role membership, default
privileges, independently addressed type/index metadata, other administrative
DDL, or base data writes. Release therefore requires a documented maintenance
window with those administrative writers quiesced; source ingestion must also
be quiesced for deterministic before/after arithmetic and consumer comparisons.
Do not infer that condition from a momentarily empty `pg_stat_activity`, disable
roles, terminate sessions, or take broad catalog locks. The apply interface must
record an explicit maintenance-window acknowledgement and fail closed when it
is absent. This is an operator-supplied condition, not a claimed database-level
guarantee against arbitrary privileged changes. If that condition cannot be met,
return to planning; do not claim this protocol makes unrestricted online DDL safe.

**Additional acceptance evidence (existing IDs retained):** A-ANOM-01 now requires
the real held-lock assertion, relation/rowtype/array dependency fixtures, rejected
metadata/OID/owner drift including a change committed while the lock waits, and
the maintenance-window guard. A-ANOM-02 requires a freshly inspected corrected
state to no-op without changing OIDs/data/metadata. A-ANOM-03 additionally requires
two-connection tests showing (a) a held reader causes a bounded timeout with no
change, (b) a competing tool cannot enter the guarded section, (c) reads during
replacement wait or time out and fresh name-based reads succeed after commit,
and (d) a late registered type dependency either blocks or causes restrictive
DROP failure with full rollback, never cascade. Use deterministic barriers and
bounded waits, not sleep-based race assertions. Existing arithmetic, metadata,
failure-injection, recovery, and PG17 requirements remain in force.

**Primary basis:** PostgreSQL documents the supported
[materialized-view owner action](https://www.postgresql.org/docs/17/sql-altermaterializedview.html).
PG17's [table command implementation](https://github.com/postgres/postgres/blob/REL_17_STABLE/src/backend/commands/tablecmds.c)
assigns `AccessExclusiveLock` to `AT_ChangeOwner` and skips catalog owner changes
when the owner matches; the [utility dispatcher](https://github.com/postgres/postgres/blob/REL_17_STABLE/src/backend/tcop/utility.c)
obtains that lock before execution. The protocol's concurrency limits follow
the documented [lock semantics](https://www.postgresql.org/docs/17/explicit-locking.html),
[statement snapshots](https://www.postgresql.org/docs/17/transaction-iso.html), and
[restrictive materialized-view DROP](https://www.postgresql.org/docs/17/sql-dropmaterializedview.html).
This is the selected implementation design, to be confirmed by the tests above.

### T4 — Make artifact verification classify evidence truthfully

**Owned paths:** `scripts/verify_artifacts.py`, `tests/test_verify_artifacts.py`,
`tests/test_provenance.py` (only subprocess encoding/diagnostic boundary).

Write failing unit cases for missing `data/` and `data\` inputs, absolute Windows
paths, missing upstream temporary artifacts, a genuine traceback, a nonzero
builder failure, and successful rebuild with differing content. Normalize only
diagnostic path comparison; do not suppress errors merely because text contains
`not present`, `run scripts/`, or an arbitrary missing file. Known missing source
inputs and dependency cascades produce UNVERIFIED; real builder bugs and changed
output produce a failure. Keep existing exit semantics for absent raw data but
report verified/unverified counts and `NOTHING WAS VERIFIED` for zero checks.

Specify UTF-8 for JSON reads. Run Python builders with explicit UTF-8 diagnostic
output (child environment copied from the caller plus encoding controls) and
decode captured bytes/text consistently. Do not rely on the parent process's
`-X utf8`. Handle undecodable diagnostics visibly without discarding a failing
return code; never use replacement decoding for authoritative data. Cover both
normal and `--update` subprocess paths. Do not use `--update` on real artifacts
to prove this task; mocked builders and temporary fixtures suffice.

**Verification:** `python -m pytest tests/test_verify_artifacts.py tests/test_provenance.py -q`
and `python scripts/verify_artifacts.py` under Windows default and inherited UTF-8.
Retain raw-dependent skips; missing sources must never become a fabricated PASS.

### T5 — Canonicalize dictionary bytes and repair observed Windows boundaries

**Initial owned paths:** `scripts/build_data_dictionary.py`,
`tests/test_data_dictionary.py`, `tests/test_static_pages.py`,
`data/data_dictionary.json`, `docs/DATA_DICTIONARY.md`.

Define dictionary artifact byte metadata as bytes of the current working-file
text decoded strictly as UTF-8, normalized CRLF/CR to LF, and encoded as UTF-8.
Do not read Git blobs: edited inputs must affect the output before commit. Do not
parse/reserialize JSON to count bytes, since that changes formatting semantics.
Use explicit UTF-8 for all builder source/artifact/template reads and deterministic
UTF-8/LF writes, compatible with Python 3.10–3.12. Replace `/tmp` test filenames
with pytest `tmp_path`, encode fixture files explicitly, and stabilize parent/
child diagnostic encoding. Test non-ASCII text, LF/CRLF equivalents, current
uncommitted input changes, and invalid UTF-8 failure. Regenerate both committed
dictionary outputs using the builder only; explain any changed byte counts.

**Additional exact ownership, narrow encoding fixes only:** `tests/test_api.py`,
`tests/test_freshness.py`, `tests/test_lineage.py`, `tests/test_llm_config.py`,
`tests/test_replies.py`, `tests/test_site_gate.py`, `tests/test_supply_chain.py`,
`tests/test_workflow_readiness.py`, and `tests/test_wow.py`. The saved reproduction
`../execution-default-windows-tests.txt` identifies 17 failures in these files
plus the dictionary failure (18 failed, 1,151 passed, 31 skipped). Add explicit
UTF-8 at the documented fixture/config/source reads while preserving assertions.
Split dictionary work and these mechanical test-boundary fixes into separate
commits if helpful; they are one acceptance group. The known
`test_static_pages.py` subprocess decoding warning must be repaired at the
child/parent boundary, not ignored. Further unlisted files require a new trace
and root coordination before extending ownership. Do not
blanket-rewrite all `read_text` calls, change assertions to accept mojibake, add
global sitecustomize/conftest encoding overrides, suppress thread warnings, or
declare the default Windows mode unsupported. A non-encoding failure or broader
runtime change returns to Astra.

**Verification:** focused dictionary and static-page tests, then the full locked
suite twice on Windows: default environment and inherited `PYTHONUTF8=1`.
Temporarily set/restore environment values without printing secrets. Run
`ruff check .`, `uv lock --check`, and `python scripts/check_static_js.py`.
Use the existing Linux CI matrix after the branch is pushed for Linux evidence;
do not infer Linux success from Windows runs. No CI configuration change is
necessary unless a demonstrated blocker is returned to the planner.

### T6 — Produce reviewed freshness dispositions without speculative ingestion

**Root/research owner paths:** `docs/evidence/source-refresh.json` and
`docs/SOURCE_REFRESH_REVIEW.md`. Download raw candidates outside authoritative
`static/`, `data/`, and freshness-vintage files. This task changes no served data.

For `tea_snapshot`, `tea_staar_district`, `bond_elections`,
`brb_debt_outstanding`, `census_tiger`, `usac_erate`, and `usac_entities`, record
actual URL, retrieval time, exact product identity, schema/period, publisher
metadata, content hash or relevant-row comparison, and disposition. TIGER's
signal is 2026 versus served 2025. TEA year regexes may find statewide PDFs;
BRB/USAC timestamps may churn without compatible row changes. Retain BLS as
unverifiable unless evidence resolves it; F-33/NPEFS FY2025 and accountability
2026 were unpublished at audit time and require a new publisher check before
changing that status. Redact any incidental private/contact data from evidence.

Use dispositions `compatible_refresh_required`, `unchanged_content`,
`different_product_or_false_positive`, `not_published`, or `unresolved`, each
with evidence. A compatible refresh requires a separate source-specific task
with ingestion/build dependencies, independent numerical/source checks, and
reviewed artifact diffs before any served-vintage change. Root may commission
that next bounded refinement after this triage; do not silently expand Terra's
current edit list. Retrieval/check dates and served data vintage are distinct.

**Verification:** review the evidence against the seven original signals and
source register; parse JSON and verify every entry has identity, date, disposition,
evidence, and follow-up. No manufactured automation test can prove a publisher
product matches; inspected source/schema/content evidence is required.

## Acceptance matrix for independent verification

| ID | Objective PASS condition |
|---|---|
| A-DB-01 | Dedicated harness runs against an explicitly selected actual PostgreSQL major (18.3 available for development), rejects unavailable/wrong-major setup, uses only its isolated loopback cluster, and proves cleanup on success and injected failure. |
| A-DB-02 | Both 12- and 30-column starting states become the declared 30-column contract; original column order/types, summary OID/owner/options/grants, and dependent matview OID/definition/indexes/grants are preserved. |
| A-DB-03 | Dallas FY2025 is exactly 23746.63 spending/student and 13529.52 revenue/student at two decimals; each sample and synthetic positive case matches independent Decimal arithmetic; zero/negative/NULL enrollment yields NULL, never zero or division error. |
| A-DB-04 | Second application has no semantic/data/ACL change. An injected failure rolls back view and matview contents fully. Post-commit recovery retains 30 fields and identities, restores documented prior formulas, and allows successful repair reapplication. |
| A-DB-05 | All five public projections retain equivalent row coverage and SELECT-only effective access for both API roles; no base reads/writes are enabled; NLP retains only its two finance reads and existing restrictions. PR #78 is reconciled without a production write or merge. |
| A-DB-06 | The read-only verifier detects wrong columns/types, privileges, and arithmetic; it reports enrollment exceptions and deferred anomaly defects distinctly. Its SQL transaction cannot mutate data and logs contain no DSN/password. |
| A-SCOPE-01 | Summary reconciliation/recovery never uses DROP; no migration uses CASCADE. Only the separately guarded T3b transaction may replace the anomaly matview. No startup migration or unrelated application changes occur, and target anomaly claims stay blocked until actual correction. |
| A-ANOM-01 | T3b's supported PG17 guard proves its exclusive lock, requires the stated maintenance condition, and rejects snapshot drift or unexpected relation/rowtype/array dependencies before DROP; any tentative owner action rolls back on rejection. Successful replacement retains column/consumer contract, owner/options/comments, effective public/NLP ACLs, and both index definitions, while explicitly recording expected new matview/index OIDs. |
| A-ANOM-02 | All revenue/spend threshold and enrollment-delta fixtures match independent arithmetic; NULL/zero cases are safe; original per-student/enrollment flags preserve their definitions. Reapplication against a freshly inspected correct state is an idempotent no-op, preserving OIDs/data/metadata. |
| A-ANOM-03 | Each injected in-transaction failure restores the old object/data/ACLs/index OIDs. Bounded two-connection tests prove reader contention, tool serialization, wait-time drift rejection, and late-dependency rollback. Post-commit guarded recovery restores old semantics/metadata with explicitly new OIDs and supports repair reapplication. |
| A-PG17-01 | The full summary, grants, anomaly, and recovery harness passes on actual PostgreSQL 17 before production SQL. Until then PostgreSQL 17 execution remains UNVERIFIED, irrespective of PostgreSQL 18 results. |
| A-ART-01 | Both separator styles and known dependency cascades produce UNVERIFIED; real builder errors and byte drift still fail; zero verified inputs produces the explicit zero-check result in both Windows encoding modes. |
| A-ENC-01 | Dictionary generation produces identical UTF-8/LF output and canonical byte metadata for equivalent LF/CRLF input; changed working files change results; invalid UTF-8 is a visible error. Generated outputs have no manual edits. |
| A-ENC-02 | Full Windows default and inherited-UTF8 test runs have no failures or encoding-related thread warnings; remaining source-dependent skips are enumerated. Focused regressions, Ruff, lock check, and JS parse pass. |
| A-CI-01 | Linux CI evidence at the exact implementation revision passes the supported Python matrix; absent/pending CI is UNVERIFIED, never assumed from local tests. |
| A-SOURCE-01 | Seven signals plus BLS/unpublished-product statuses have evidence-backed dispositions; no served vintage/artifact changes occur from metadata alone. Unresolved findings block only affected freshness claims and do not halt independent prototype/host work. |

Record one PASS/FAIL/UNVERIFIED line per ID, command/environment, exact revision,
and evidence location in `docs/evidence/data-trust-verification.md` (root/verifier
ownership). Terra reports implementation evidence; fresh Luna independently
checks it and does not repair. These acceptance IDs supersede vague A-package
completion language but do not authorize deployment or close deferred anomaly,
freshness, real-participant, or real-ChatGPT gates.
